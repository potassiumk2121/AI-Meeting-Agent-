from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas import SendReportIn, SendReportOut
from app.services.emailer import send_meeting_report

router = APIRouter(prefix="/api/email", tags=["email"])


@router.post("/send-report", response_model=SendReportOut)
async def send_report(body: SendReportIn, session: AsyncSession = Depends(get_db)) -> SendReportOut:
    result = await send_meeting_report(session, body.meeting_id, str(body.recipient))
    return SendReportOut(**result)
