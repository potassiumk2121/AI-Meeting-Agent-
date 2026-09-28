from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas import AskIn, AskOut, SearchHit, SearchIn
from app.services.ask import ask_meetings
from app.services.rag import search_meetings

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=list[SearchHit])
async def search(
    body: SearchIn,
    session: AsyncSession = Depends(get_db),
) -> list[SearchHit]:
    hits = await search_meetings(session, body.query, body.limit)
    return [SearchHit(**hit) for hit in hits]


@router.post("/ask", response_model=AskOut)
async def ask(body: AskIn, session: AsyncSession = Depends(get_db)) -> AskOut:
    result = await ask_meetings(session, body.query, body.meeting_id)
    return AskOut(**result)
