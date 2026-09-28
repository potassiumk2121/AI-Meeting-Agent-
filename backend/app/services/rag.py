import logging

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import EmbeddingChunk, Meeting
from app.services.llm import embed_texts

logger = logging.getLogger(__name__)


def chunk_text(text: str, size: int = 1200) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    chunks: list[str] = []
    buffer: list[str] = []
    count = 0
    for word in cleaned.split():
        buffer.append(word)
        count += len(word) + 1
        if count >= size:
            chunks.append(" ".join(buffer))
            buffer = []
            count = 0
    if buffer:
        chunks.append(" ".join(buffer))
    return chunks


def _snippet(content: str, query: str) -> str:
    haystack = content.lower()
    needle = query.lower().split()[0] if query.strip() else ""
    index = haystack.find(needle) if needle else 0
    if index < 0:
        index = 0
    start = max(0, index - 80)
    clipped = content[start : start + 240].strip()
    if start > 0:
        clipped = "…" + clipped
    if start + 240 < len(content):
        clipped += "…"
    return clipped


async def reindex(
    session: AsyncSession,
    meeting: Meeting,
    turns: list[str],
    summary: str,
    decisions: list[str] | None = None,
    actions: list[str] | None = None,
) -> None:
    await session.execute(delete(EmbeddingChunk).where(EmbeddingChunk.meeting_id == meeting.id))
    pieces: list[tuple[str, str]] = []
    if summary.strip():
        pieces.append(("summary", f"{meeting.title}\n{summary}"))
    pieces.extend(("transcript", chunk) for chunk in chunk_text("\n".join(turns)))
    for text in decisions or []:
        cleaned = text.strip()
        if cleaned:
            pieces.append(("decision", f"{meeting.title}\nDecision: {cleaned}"))
    for text in actions or []:
        cleaned = text.strip()
        if cleaned:
            pieces.append(("action", f"{meeting.title}\nAction: {cleaned}"))
    if not pieces:
        return
    vectors: list[list[float] | None] = [None] * len(pieces)
    if get_settings().openai_api_key:
        try:
            vectors = await embed_texts([text for _, text in pieces])
        except Exception:
            logger.exception("embedding failed; full-text search will still work")
            vectors = [None] * len(pieces)
    for (kind, content), vector in zip(pieces, vectors):
        session.add(
            EmbeddingChunk(
                meeting_id=meeting.id,
                content=content,
                kind=kind,
                embedding=vector,
            )
        )


async def search_meetings(session: AsyncSession, query: str, limit: int) -> list[dict]:
    query = query.strip()
    if get_settings().openai_api_key:
        try:
            vector = (await embed_texts([query]))[0]
            distance = EmbeddingChunk.embedding.cosine_distance(vector)
            stmt = (
                select(EmbeddingChunk, Meeting, distance.label("distance"))
                .join(Meeting, Meeting.id == EmbeddingChunk.meeting_id)
                .where(EmbeddingChunk.embedding.is_not(None))
                .order_by(distance)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            if rows:
                return [
                    {
                        "meeting_id": meeting.id,
                        "meeting_title": meeting.title,
                        "snippet": _snippet(chunk.content, query),
                        "score": round(1 - float(dist), 4),
                    }
                    for chunk, meeting, dist in rows
                ]
        except Exception:
            logger.exception("vector search failed; falling back to full text")
    return await _keyword_search(session, query, limit)


async def _keyword_search(session: AsyncSession, query: str, limit: int) -> list[dict]:
    document = func.to_tsvector("english", EmbeddingChunk.content)
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank(document, tsquery)
    stmt = (
        select(EmbeddingChunk, Meeting, rank.label("rank"))
        .join(Meeting, Meeting.id == EmbeddingChunk.meeting_id)
        .where(document.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    if rows:
        return [
            {
                "meeting_id": meeting.id,
                "meeting_title": meeting.title,
                "snippet": _snippet(chunk.content, query),
                "score": round(float(score), 4),
            }
            for chunk, meeting, score in rows
        ]
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = (
        select(EmbeddingChunk, Meeting)
        .join(Meeting, Meeting.id == EmbeddingChunk.meeting_id)
        .where(EmbeddingChunk.content.ilike(f"%{escaped}%", escape="\\"))
        .limit(limit)
    )
    fuzzy = (await session.execute(like)).all()
    return [
        {
            "meeting_id": meeting.id,
            "meeting_title": meeting.title,
            "snippet": _snippet(chunk.content, query),
            "score": 0.1,
        }
        for chunk, meeting in fuzzy
    ]
