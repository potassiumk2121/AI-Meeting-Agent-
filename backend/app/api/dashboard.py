import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models import ActionItem, Decision, Meeting, Participant, Risk
from app.schemas import ActionUpdate, DashboardOut, DecisionRow, PersonOut, RiskRow, TaskOut
from app.services.pipeline import _meeting_out
from app.services.reports import follow_ups, period_report
from app.timeutil import utcnow

router = APIRouter(prefix="/api", tags=["dashboard"])


def _task(row: ActionItem, title: str) -> TaskOut:
    return TaskOut(
        id=row.id,
        meeting_id=row.meeting_id,
        meeting_title=title,
        assignee_name=row.assignee_name,
        description=row.description,
        status=row.status,
        due_label=row.due_label,
        created_at=row.created_at,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    session: AsyncSession = Depends(get_db),
) -> DashboardOut:
    meetings = (await session.execute(select(func.count()).select_from(Meeting))).scalar_one()
    live = (
        await session.execute(select(func.count()).select_from(Meeting).where(Meeting.status == "live"))
    ).scalar_one()
    open_tasks = (
        await session.execute(select(func.count()).select_from(ActionItem).where(ActionItem.status == "open"))
    ).scalar_one()
    decisions = (await session.execute(select(func.count()).select_from(Decision))).scalar_one()
    participants = (
        await session.execute(select(func.count(func.distinct(Participant.name))))
    ).scalar_one()
    recent_rows = (
        await session.execute(
            select(Meeting).options(selectinload(Meeting.participants)).order_by(Meeting.created_at.desc()).limit(8)
        )
    ).scalars().all()
    preview_rows = (
        await session.execute(
            select(ActionItem, Meeting.title)
            .join(Meeting, Meeting.id == ActionItem.meeting_id)
            .where(ActionItem.status == "open")
            .order_by(ActionItem.created_at.desc())
            .limit(5)
        )
    ).all()
    week = await period_report(session, "week")
    reminders = await follow_ups(session)
    return DashboardOut(
        meetings=meetings,
        live_meetings=live,
        open_tasks=open_tasks,
        decisions=decisions,
        participants=participants,
        minutes_this_week=week["minutes"],
        sentiment=week["sentiment"],
        follow_ups=[item["reminder"] for item in reminders[:5]],
        recent_meetings=[_meeting_out(row, [person.name for person in row.participants]) for row in recent_rows],
        open_task_preview=[_task(item, title) for item, title in preview_rows],
    )


@router.get("/tasks", response_model=list[TaskOut])
async def tasks(
    status: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[TaskOut]:
    stmt = (
        select(ActionItem, Meeting.title)
        .join(Meeting, Meeting.id == ActionItem.meeting_id)
        .order_by(ActionItem.created_at.desc())
        .limit(200)
    )
    if status:
        stmt = stmt.where(ActionItem.status == status)
    rows = (await session.execute(stmt)).all()
    return [_task(item, title) for item, title in rows]


@router.patch("/action-items/{item_id}", response_model=TaskOut)
async def update_action(
    item_id: uuid.UUID,
    body: ActionUpdate,
    session: AsyncSession = Depends(get_db),
) -> TaskOut:
    from app.errors import AppError

    row = await session.get(ActionItem, item_id)
    if not row:
        raise AppError("Action item not found.", 404)
    meeting = await session.get(Meeting, row.meeting_id)
    row.status = body.status
    row.updated_at = utcnow()
    await session.commit()
    return _task(row, meeting.title if meeting else "")


@router.delete("/action-items/{item_id}", status_code=204)
async def delete_action(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    from app.errors import AppError

    row = await session.get(ActionItem, item_id)
    if not row:
        raise AppError("Action item not found.", 404)
    await session.delete(row)
    await session.commit()


@router.get("/decisions", response_model=list[DecisionRow])
async def decisions(
    session: AsyncSession = Depends(get_db),
) -> list[DecisionRow]:
    rows = (
        await session.execute(
            select(Decision, Meeting.title)
            .join(Meeting, Meeting.id == Decision.meeting_id)
            .order_by(Decision.created_at.desc())
            .limit(200)
        )
    ).all()
    return [
        DecisionRow(id=item.id, meeting_id=item.meeting_id, meeting_title=title, text=item.text, created_at=item.created_at)
        for item, title in rows
    ]


@router.get("/risks", response_model=list[RiskRow])
async def risks(
    session: AsyncSession = Depends(get_db),
) -> list[RiskRow]:
    rows = (
        await session.execute(
            select(Risk, Meeting.title)
            .join(Meeting, Meeting.id == Risk.meeting_id)
            .order_by(Risk.created_at.desc())
            .limit(200)
        )
    ).all()
    return [
        RiskRow(id=item.id, meeting_id=item.meeting_id, meeting_title=title, text=item.text, created_at=item.created_at)
        for item, title in rows
    ]


@router.get("/participants", response_model=list[PersonOut])
async def participants(
    session: AsyncSession = Depends(get_db),
) -> list[PersonOut]:
    rows = (
        await session.execute(
            select(
                Participant.name,
                func.max(Participant.email),
                func.count(func.distinct(Participant.meeting_id)),
                func.max(Participant.created_at),
            )
            .group_by(Participant.name)
            .order_by(func.max(Participant.created_at).desc())
        )
    ).all()
    return [
        PersonOut(name=name, email=email, meetings=count, last_seen=seen)
        for name, email, count, seen in rows
    ]
