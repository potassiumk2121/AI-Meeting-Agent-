import logging
import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Meeting, MeetingSummary, Participant, TranscriptSegment
from app.services.llm import complete_json, llm_configured

logger = logging.getLogger(__name__)

_STOP = {
    "what",
    "did",
    "say",
    "said",
    "about",
    "the",
    "a",
    "an",
    "to",
    "of",
    "in",
    "on",
    "for",
    "and",
    "was",
    "were",
    "is",
    "meeting",
    "who",
    "when",
    "where",
    "why",
    "how",
}


def _words(query: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]{1,}", query)


def _like(word: str) -> str:
    cleaned = word.replace("\\", "").replace("%", "").replace("_", "")
    return f"%{cleaned}%"


async def ask_meetings(session: AsyncSession, query: str, meeting_id=None, limit: int = 8) -> dict:
    names = (
        await session.execute(select(Participant.name).distinct())
    ).scalars().all()
    if meeting_id:
        names = (
            await session.execute(select(Participant.name).where(Participant.meeting_id == meeting_id).distinct())
        ).scalars().all()
    query_words = {word.casefold() for word in _words(query)}
    speakers = [name for name in names if name and name.casefold() in query_words]
    keywords = [word for word in _words(query) if word.casefold() not in _STOP and word.casefold() not in {name.casefold() for name in speakers}]

    stmt = select(TranscriptSegment, Meeting).join(Meeting, Meeting.id == TranscriptSegment.meeting_id)
    if meeting_id:
        stmt = stmt.where(TranscriptSegment.meeting_id == meeting_id)
    if speakers:
        stmt = stmt.where(or_(*[TranscriptSegment.speaker_name.ilike(name) for name in speakers]))
    if keywords:
        stmt = stmt.where(
            or_(
                *[
                    or_(
                        TranscriptSegment.english_text.ilike(_like(word), escape="\\"),
                        TranscriptSegment.original_text.ilike(_like(word), escape="\\"),
                    )
                    for word in keywords
                ]
            )
        )
    rows = (await session.execute(stmt.order_by(TranscriptSegment.started_at.asc()).limit(limit))).all()
    quotes = [
        {
            "meeting_id": meeting.id,
            "meeting_title": meeting.title,
            "speaker": segment.speaker_name,
            "timestamp": segment.timestamp_label,
            "original": segment.original_text,
            "english": segment.english_text,
        }
        for segment, meeting in rows
    ]
    meeting_ids = list({quote["meeting_id"] for quote in quotes})
    summaries: list[str] = []
    if meeting_ids:
        summary_rows = (
            await session.execute(select(MeetingSummary).where(MeetingSummary.meeting_id.in_(meeting_ids)))
        ).scalars().all()
        summaries = [row.executive_summary for row in summary_rows if row.executive_summary]
    answer, summary = await _compose(query, quotes, summaries)
    return {"answer": answer, "summary": summary, "quotes": quotes}


async def _compose(query: str, quotes: list[dict], summaries: list[str]) -> tuple[str, str]:
    summary = "\n\n".join(summaries)[:2000]
    if not quotes and not summary:
        return "Nothing in the stored meetings matches that question.", ""
    if llm_configured() and quotes:
        packed = "\n".join(
            f"{item['speaker']} at {item['timestamp']}: original={item['original']} | english={item['english']}"
            for item in quotes
        )
        try:
            data = await complete_json(
                "Answer using only these transcript lines and summaries. "
                'Return JSON {"answer":"...","summary":"..."}. '
                "Name the speaker and timestamp. Do not invent lines.",
                f"Question: {query}\n\nLines:\n{packed}\n\nSummaries:\n{summary}",
            )
            answer = str(data.get("answer") or "").strip()
            brief = str(data.get("summary") or "").strip() or summary
            if answer:
                return answer, brief
        except Exception:
            logger.exception("ask model failed")
    if quotes:
        lines = [f"{item['speaker']} ({item['timestamp']}): {item['english']}" for item in quotes]
        return "\n".join(lines), summary
    return summary, summary
