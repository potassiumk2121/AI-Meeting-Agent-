from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ActionItem, Decision, Meeting, MeetingSummary, TranscriptSegment
from app.timeutil import utcnow


def _zone() -> ZoneInfo:
    try:
        return ZoneInfo(get_settings().default_timezone)
    except Exception:
        return ZoneInfo("UTC")


def period_bounds(kind: str) -> tuple[datetime, datetime, str]:
    now = datetime.now(_zone())
    if kind == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = start.strftime("%B %Y")
    else:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        label = f"Week of {start.strftime('%d %b %Y')}"
    return start, now, label


def _minutes(meeting: Meeting) -> int:
    if meeting.started_at is None:
        return 0
    end = meeting.ended_at or utcnow()
    return max(0, int((end - meeting.started_at).total_seconds() // 60))


async def _meetings_since(session: AsyncSession, start: datetime) -> list[Meeting]:
    when = func.coalesce(Meeting.started_at, Meeting.created_at)
    rows = (
        await session.execute(select(Meeting).where(when >= start).order_by(when.desc()))
    ).scalars().all()
    return list(rows)


async def speaker_stats(session: AsyncSession, meeting_id=None) -> list[dict]:
    stmt = select(TranscriptSegment.speaker_name, func.count()).group_by(TranscriptSegment.speaker_name)
    if meeting_id:
        stmt = stmt.where(TranscriptSegment.meeting_id == meeting_id)
    rows = (await session.execute(stmt.order_by(func.count().desc()))).all()
    total = sum(count for _, count in rows) or 1
    return [{"name": name, "lines": count, "share": round(count / total, 3)} for name, count in rows]


async def period_report(session: AsyncSession, kind: str) -> dict:
    start, end, label = period_bounds(kind)
    meetings = await _meetings_since(session, start)
    ids = [meeting.id for meeting in meetings]
    sentiment: dict[str, int] = {}
    for meeting in meetings:
        key = meeting.sentiment or "unknown"
        sentiment[key] = sentiment.get(key, 0) + 1
    decisions = 0
    open_actions = 0
    highlights: list[str] = []
    speakers: list[dict] = []
    if ids:
        decisions = (
            await session.execute(select(func.count()).select_from(Decision).where(Decision.meeting_id.in_(ids)))
        ).scalar_one()
        open_actions = (
            await session.execute(
                select(func.count()).select_from(ActionItem).where(
                    ActionItem.meeting_id.in_(ids),
                    ActionItem.status == "open",
                )
            )
        ).scalar_one()
        summary_rows = (
            await session.execute(
                select(Meeting.title, MeetingSummary.executive_summary)
                .join(MeetingSummary, MeetingSummary.meeting_id == Meeting.id)
                .where(Meeting.id.in_(ids))
                .limit(8)
            )
        ).all()
        highlights = [f"{title}: {text}" for title, text in summary_rows if text]
        line_rows = (
            await session.execute(
                select(TranscriptSegment.speaker_name, func.count())
                .where(TranscriptSegment.meeting_id.in_(ids))
                .group_by(TranscriptSegment.speaker_name)
                .order_by(func.count().desc())
            )
        ).all()
        total = sum(count for _, count in line_rows) or 1
        speakers = [{"name": name, "lines": count, "share": round(count / total, 3)} for name, count in line_rows[:8]]
    return {
        "label": label,
        "start": start,
        "end": end,
        "meetings": len(meetings),
        "minutes": sum(_minutes(meeting) for meeting in meetings),
        "decisions": decisions,
        "open_actions": open_actions,
        "sentiment": sentiment,
        "speakers": speakers,
        "highlights": highlights,
    }


async def follow_ups(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            select(ActionItem, Meeting.title)
            .join(Meeting, Meeting.id == ActionItem.meeting_id)
            .where(ActionItem.status == "open")
            .order_by(ActionItem.created_at.desc())
            .limit(50)
        )
    ).all()
    result = []
    for item, title in rows:
        due = f" due {item.due_label}" if item.due_label else ""
        result.append(
            {
                "meeting_id": item.meeting_id,
                "meeting_title": title,
                "assignee_name": item.assignee_name,
                "description": item.description,
                "due_label": item.due_label,
                "reminder": f"Remind {item.assignee_name} to {item.description}{due}. From {title}.",
            }
        )
    return result
