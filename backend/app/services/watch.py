import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import AppError
from app.models import Meeting
from app.services.connectors import list_calendar_events
from app.timeutil import utcnow

logger = logging.getLogger(__name__)


async def scan_calendar(session: AsyncSession) -> dict:
    settings = get_settings()
    if not settings.graph_configured or not settings.graph_sender:
        return {
            "started": 0,
            "closed": 0,
            "detail": "Set Azure app credentials and GRAPH_SENDER to detect Teams meetings on the calendar.",
        }
    now = utcnow()
    try:
        events = await list_calendar_events(now - timedelta(hours=2), now + timedelta(hours=6))
    except AppError as exc:
        return {"started": 0, "closed": 0, "detail": exc.message}
    started = 0
    closed = 0
    for event in events:
        if not event["online"] or not event["join_url"]:
            continue
        meeting = (
            await session.execute(select(Meeting).where(Meeting.join_url == event["join_url"]).limit(1))
        ).scalar_one_or_none()
        if event["start"] <= now < event["end"]:
            if meeting is None:
                meeting = Meeting(
                    title=event["title"],
                    platform="teams",
                    join_url=event["join_url"],
                    organizer_email=event.get("organizer"),
                    status="scheduled",
                )
                session.add(meeting)
                await session.commit()
                await session.refresh(meeting)
            if meeting.status == "scheduled":
                from app.services.pipeline import join_meeting

                await join_meeting(session, meeting.id)
                started += 1
        elif now >= event["end"] and meeting and meeting.status == "live":
            from app.services.emailer import send_meeting_report
            from app.services.pipeline import finalize

            try:
                await finalize(session, meeting.id)
            except AppError as exc:
                logger.info("meeting stayed open: %s", exc.message)
                continue
            closed += 1
            recipients = list(settings.default_recipient_list)
            if meeting.organizer_email and meeting.organizer_email not in recipients:
                recipients.append(meeting.organizer_email)
            for recipient in recipients:
                try:
                    await send_meeting_report(session, meeting.id, recipient)
                except AppError:
                    logger.warning("report email failed for %s", recipient)
    detail = "Calendar scan finished."
    if closed and not settings.default_recipient_list:
        detail = "Closed meetings were summarized. Set EMAIL_DEFAULT_RECIPIENTS to email the manager automatically."
    return {"started": started, "closed": closed, "detail": detail}
