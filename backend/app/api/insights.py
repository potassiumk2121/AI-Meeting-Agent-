from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.errors import AppError
from app.schemas import CalendarItem, CalendarOut, FollowUpOut, PeriodReport, ScanOut, SpeakerStat
from app.services.connectors import list_calendar_events
from app.services.reports import follow_ups, period_report, speaker_stats
from app.services.watch import scan_calendar
from app.timeutil import utcnow

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/reports/weekly", response_model=PeriodReport)
async def weekly(session: AsyncSession = Depends(get_db)) -> PeriodReport:
    return PeriodReport(**await period_report(session, "week"))


@router.get("/reports/monthly", response_model=PeriodReport)
async def monthly(session: AsyncSession = Depends(get_db)) -> PeriodReport:
    return PeriodReport(**await period_report(session, "month"))


@router.get("/reports/follow-ups", response_model=list[FollowUpOut])
async def reminders(session: AsyncSession = Depends(get_db)) -> list[FollowUpOut]:
    return [FollowUpOut(**row) for row in await follow_ups(session)]


@router.get("/insights/speakers", response_model=list[SpeakerStat])
async def speakers(meeting_id: str | None = None, session: AsyncSession = Depends(get_db)) -> list[SpeakerStat]:
    import uuid

    parsed = None
    if meeting_id:
        try:
            parsed = uuid.UUID(meeting_id)
        except ValueError as exc:
            raise AppError("Meeting id is not valid.", 400) from exc
    return [SpeakerStat(**row) for row in await speaker_stats(session, parsed)]


@router.get("/calendar/upcoming", response_model=CalendarOut)
async def upcoming() -> CalendarOut:
    settings = get_settings()
    if not settings.graph_configured or not settings.graph_sender:
        return CalendarOut(
            configured=False,
            detail="Set Azure app credentials and GRAPH_SENDER, then grant Calendars.Read.",
            events=[],
        )
    now = utcnow()
    try:
        events = await list_calendar_events(now, now + timedelta(days=7))
    except AppError as exc:
        return CalendarOut(configured=True, detail=exc.message, events=[])
    return CalendarOut(
        configured=True,
        detail="Upcoming Outlook events.",
        events=[
            CalendarItem(
                title=item["title"],
                start=item["start"],
                end=item["end"],
                join_url=item["join_url"],
                organizer=item["organizer"],
            )
            for item in events
        ],
    )


@router.post("/calendar/scan", response_model=ScanOut)
async def scan(session: AsyncSession = Depends(get_db)) -> ScanOut:
    return ScanOut(**await scan_calendar(session))
