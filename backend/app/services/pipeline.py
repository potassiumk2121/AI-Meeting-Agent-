import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.errors import AppError
from app.hub import hub
from app.models import (
    ActionItem,
    ChatMessage,
    Decision,
    EmailDelivery,
    Meeting,
    MeetingSummary,
    Participant,
    Risk,
    TranscriptSegment,
)
from app.schemas import (
    ActionOut,
    ChatOut,
    DecisionOut,
    EmailOut,
    IngestOut,
    JoinOut,
    MeetingDetail,
    MeetingOut,
    ParticipantOut,
    RiskOut,
    SegmentOut,
    SummaryOut,
    SyncOut,
)
from app.services.connectors import ensure_transcript_subscription, pull_for_meeting
from app.services.extract import actions_from_utterance, classify_sentiment
from app.services.pdf_report import ReportData, build_pdf
from app.services.rag import reindex
from app.services.speech import transcribe
from app.services.summarize import analyze
from app.services.translate import to_english
from app.timeutil import file_date, format_date, format_stamp, utcnow

logger = logging.getLogger(__name__)


def _duration_minutes(meeting: Meeting) -> int | None:
    if meeting.started_at is None:
        return None
    end = meeting.ended_at or utcnow()
    return max(0, int((end - meeting.started_at).total_seconds() // 60))


def _meeting_out(meeting: Meeting, names: list[str]) -> MeetingOut:
    return MeetingOut(
        id=meeting.id,
        title=meeting.title,
        platform=meeting.platform,
        status=meeting.status,
        sentiment=meeting.sentiment,
        started_at=meeting.started_at,
        ended_at=meeting.ended_at,
        created_at=meeting.created_at,
        join_url=meeting.join_url,
        organizer_email=meeting.organizer_email,
        participants=names,
        report_ready=bool(meeting.report_path),
        report_stale=bool(meeting.report_stale),
        report_filename=meeting.report_filename,
        error_message=meeting.error_message,
        duration_minutes=_duration_minutes(meeting),
    )


def _segment_out(row: TranscriptSegment) -> SegmentOut:
    return SegmentOut(
        id=row.id,
        speaker_name=row.speaker_name,
        timestamp_label=row.timestamp_label,
        original_text=row.original_text,
        original_language=row.original_language,
        english_text=row.english_text,
        started_at=row.started_at,
        source=row.source,
    )


def _chat_out(row: ChatMessage) -> ChatOut:
    return ChatOut(
        id=row.id,
        sender_name=row.sender_name,
        original_text=row.original_text,
        english_text=row.english_text,
        timestamp_label=row.timestamp_label,
        sent_at=row.sent_at,
    )


def _action_out(row: ActionItem) -> ActionOut:
    return ActionOut(
        id=row.id,
        meeting_id=row.meeting_id,
        assignee_name=row.assignee_name,
        description=row.description,
        status=row.status,
        due_label=row.due_label,
        created_at=row.created_at,
    )


async def _get_meeting(session: AsyncSession, meeting_id: uuid.UUID) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if not meeting:
        raise AppError("Meeting not found.", 404)
    return meeting


async def _names(session: AsyncSession, meeting_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(Participant.name)
        .where(Participant.meeting_id == meeting_id)
        .order_by(Participant.created_at)
    )
    return list(rows.scalars())


async def list_meetings(session: AsyncSession, status: str | None, limit: int) -> list[MeetingOut]:
    stmt = select(Meeting).options(selectinload(Meeting.participants)).order_by(Meeting.created_at.desc())
    if status:
        stmt = stmt.where(Meeting.status == status)
    stmt = stmt.limit(min(limit, 200))
    meetings = (await session.execute(stmt)).scalars().all()
    return [_meeting_out(meeting, [person.name for person in meeting.participants]) for meeting in meetings]


async def get_meeting_detail(session: AsyncSession, meeting_id: uuid.UUID) -> MeetingDetail:
    meeting = await _get_meeting(session, meeting_id)
    participants = (
        await session.execute(
            select(Participant).where(Participant.meeting_id == meeting_id).order_by(Participant.created_at)
        )
    ).scalars().all()
    segments = (
        await session.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.sequence)
        )
    ).scalars().all()
    chat = (
        await session.execute(
            select(ChatMessage).where(ChatMessage.meeting_id == meeting_id).order_by(ChatMessage.sent_at)
        )
    ).scalars().all()
    actions = (
        await session.execute(
            select(ActionItem).where(ActionItem.meeting_id == meeting_id).order_by(ActionItem.created_at)
        )
    ).scalars().all()
    decisions = (
        await session.execute(select(Decision).where(Decision.meeting_id == meeting_id).order_by(Decision.created_at))
    ).scalars().all()
    risks = (
        await session.execute(select(Risk).where(Risk.meeting_id == meeting_id).order_by(Risk.created_at))
    ).scalars().all()
    summary = (
        await session.execute(select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id))
    ).scalar_one_or_none()
    email = (
        await session.execute(
            select(EmailDelivery)
            .where(EmailDelivery.meeting_id == meeting_id)
            .order_by(EmailDelivery.created_at.desc())
        )
    ).scalars().first()
    return MeetingDetail(
        meeting=_meeting_out(meeting, [person.name for person in participants]),
        participants=[ParticipantOut(id=person.id, name=person.name, email=person.email) for person in participants],
        segments=[_segment_out(row) for row in segments],
        chat=[_chat_out(row) for row in chat],
        actions=[_action_out(row) for row in actions],
        decisions=[DecisionOut(id=row.id, text=row.text) for row in decisions],
        risks=[RiskOut(id=row.id, text=row.text) for row in risks],
        summary=(
            SummaryOut(
                executive_summary=summary.executive_summary,
                detailed_summary=summary.detailed_summary,
                manager_summary=summary.manager_summary,
                next_steps=list(summary.next_steps or []),
                sentiment=summary.sentiment,
                model_name=summary.model_name,
            )
            if summary
            else None
        ),
        email=(
            EmailOut(
                recipients=list(email.recipients or []),
                status=email.status,
                error=email.error,
                sent_at=email.sent_at,
            )
            if email
            else None
        ),
    )


async def _participant(session: AsyncSession, meeting_id: uuid.UUID, name: str) -> Participant:
    cleaned = name.strip()[:200] or "Speaker"
    existing = (
        await session.execute(
            select(Participant).where(Participant.meeting_id == meeting_id, Participant.name == cleaned)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = Participant(meeting_id=meeting_id, name=cleaned)
    session.add(row)
    await session.flush()
    return row


async def _open_for_ingest(meeting: Meeting) -> None:
    if meeting.status == "processing":
        raise AppError("This meeting is being processed.", 409)
    if meeting.status == "failed":
        raise AppError("This meeting failed processing. Start a new meeting.", 409)
    if meeting.status == "scheduled":
        meeting.status = "live"
        meeting.started_at = meeting.started_at or utcnow()
    elif meeting.status == "completed":
        meeting.report_stale = True


async def _refresh_sentiment(session: AsyncSession, meeting: Meeting) -> None:
    rows = await session.execute(
        select(TranscriptSegment.english_text).where(TranscriptSegment.meeting_id == meeting.id)
    )
    blob = " ".join(text for text in rows.scalars() if text)
    meeting.sentiment = classify_sentiment(blob) if blob else meeting.sentiment


async def _action_exists(session: AsyncSession, meeting_id: uuid.UUID, assignee: str, task: str) -> bool:
    row = await session.execute(
        select(ActionItem.id).where(
            ActionItem.meeting_id == meeting_id,
            func.lower(ActionItem.assignee_name) == assignee.casefold(),
            func.lower(ActionItem.description) == task.casefold(),
        )
    )
    return row.first() is not None


async def ingest_utterance(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    *,
    speaker: str,
    text: str,
    language: str | None,
    timestamp_label: str | None,
    source: str,
    dedupe: bool = False,
) -> IngestOut:
    meeting = await _get_meeting(session, meeting_id)
    await _open_for_ingest(meeting)
    speaker = speaker.strip()[:200] or "Speaker"
    text = text.strip()[:8000]
    if not text:
        raise AppError("Empty transcript line.", 400)
    label = (timestamp_label or format_stamp(utcnow())).strip()[:32]
    if dedupe:
        existing = await session.execute(
            select(TranscriptSegment.id).where(
                TranscriptSegment.meeting_id == meeting_id,
                TranscriptSegment.speaker_name == speaker,
                TranscriptSegment.original_text == text,
                TranscriptSegment.timestamp_label == label,
            )
        )
        if existing.first():
            return IngestOut(duplicate=True, sentiment=meeting.sentiment)

    english, detected = await to_english(text, language)
    person = await _participant(session, meeting_id, speaker)
    sequence = (
        await session.execute(
            select(func.coalesce(func.max(TranscriptSegment.sequence), 0)).where(
                TranscriptSegment.meeting_id == meeting_id
            )
        )
    ).scalar_one() + 1
    segment = TranscriptSegment(
        meeting_id=meeting_id,
        participant_id=person.id,
        speaker_name=speaker,
        sequence=sequence,
        timestamp_label=label,
        original_text=text,
        original_language=detected,
        english_text=english,
        source=source,
    )
    session.add(segment)
    await session.flush()

    created: list[ActionItem] = []
    for action in actions_from_utterance(speaker, english):
        if await _action_exists(session, meeting_id, action.assignee, action.task):
            continue
        row = ActionItem(
            meeting_id=meeting_id,
            assignee_name=action.assignee,
            description=action.task,
            due_label=action.due_label,
            source_segment_id=segment.id,
            status="open",
        )
        session.add(row)
        created.append(row)
    await session.flush()
    await _refresh_sentiment(session, meeting)
    await session.commit()

    result = IngestOut(
        segment=_segment_out(segment),
        actions=[_action_out(row) for row in created],
        sentiment=meeting.sentiment,
    )
    await hub.broadcast(
        str(meeting_id),
        {
            "type": "segment",
            "segment": result.segment.model_dump(mode="json"),
            "actions": [item.model_dump(mode="json") for item in result.actions],
            "sentiment": result.sentiment,
        },
    )
    return result


async def ingest_chat(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    *,
    sender: str,
    text: str,
    language: str | None,
    timestamp_label: str | None,
) -> IngestOut:
    meeting = await _get_meeting(session, meeting_id)
    await _open_for_ingest(meeting)
    sender = sender.strip()[:200] or "Participant"
    text = text.strip()[:4000]
    if not text:
        raise AppError("Empty chat message.", 400)
    english, _detected = await to_english(text, language)
    await _participant(session, meeting_id, sender)
    row = ChatMessage(
        meeting_id=meeting_id,
        sender_name=sender,
        original_text=text,
        english_text=english,
        timestamp_label=(timestamp_label or format_stamp(utcnow())).strip()[:32],
    )
    session.add(row)
    await session.commit()
    result = IngestOut(chat=_chat_out(row), sentiment=meeting.sentiment)
    await hub.broadcast(
        str(meeting_id),
        {"type": "chat", "chat": result.chat.model_dump(mode="json"), "sentiment": meeting.sentiment},
    )
    return result


async def ingest_audio(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    *,
    audio: bytes,
    filename: str,
    content_type: str,
    speaker: str,
    language: str | None,
) -> IngestOut:
    text, detected = await transcribe(audio, filename, content_type, language)
    if not text:
        raise AppError("No speech detected in that audio clip.", 422)
    return await ingest_utterance(
        session,
        meeting_id,
        speaker=speaker,
        text=text,
        language=detected or language,
        timestamp_label=None,
        source="audio",
    )


async def join_meeting(session: AsyncSession, meeting_id: uuid.UUID) -> JoinOut:
    meeting = await _get_meeting(session, meeting_id)
    if meeting.status == "processing":
        raise AppError("This meeting is being processed.", 409)
    if meeting.status in {"completed", "failed"}:
        raise AppError("This meeting is already closed. Create a new one.", 409)
    meeting.status = "live"
    meeting.started_at = meeting.started_at or utcnow()
    await session.commit()

    pulled = 0
    warning = None
    try:
        result = await pull_for_meeting(meeting)
        warning = result.warning
        if result.external_id:
            meeting.external_id = result.external_id
        for line in result.lines:
            saved = await ingest_utterance(
                session,
                meeting_id,
                speaker=line.speaker,
                text=line.text,
                language=line.language,
                timestamp_label=line.timestamp_label,
                source=meeting.platform,
                dedupe=True,
            )
            if saved.segment:
                pulled += 1
        subscription = await ensure_transcript_subscription(meeting)
        if subscription:
            meeting.subscription_id = subscription
        await session.commit()
    except AppError as exc:
        warning = exc.message
    except Exception:
        logger.exception("join connector failed")
        warning = "Live session is open. The meeting connector could not pull a transcript."
    return JoinOut(
        status="live",
        websocket_path=f"/api/meetings/{meeting.id}/live",
        pulled_segments=pulled,
        warning=warning,
    )


async def sync_meeting(session: AsyncSession, meeting_id: uuid.UUID) -> SyncOut:
    meeting = await _get_meeting(session, meeting_id)
    if meeting.status == "processing":
        raise AppError("This meeting is being processed.", 409)
    result = await pull_for_meeting(meeting)
    if result.external_id:
        meeting.external_id = result.external_id
        await session.commit()
    added = 0
    for line in result.lines:
        saved = await ingest_utterance(
            session,
            meeting_id,
            speaker=line.speaker,
            text=line.text,
            language=line.language,
            timestamp_label=line.timestamp_label,
            source=meeting.platform,
            dedupe=True,
        )
        if saved.segment:
            added += 1
    return SyncOut(added=added, warning=result.warning)


async def sync_by_external_id(session: AsyncSession, external_id: str) -> None:
    rows = await session.execute(select(Meeting).where(Meeting.external_id == external_id))
    for meeting in rows.scalars().all():
        if meeting.status == "processing":
            continue
        await sync_meeting(session, meeting.id)


def _report_filename(meeting: Meeting) -> str:
    if meeting.report_filename:
        return meeting.report_filename
    moment = meeting.started_at or meeting.created_at
    base = f"meeting_{file_date(moment)}.pdf"
    folder = Path(get_settings().reports_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / base).exists():
        return base
    return f"meeting_{file_date(moment)}_{str(meeting.id)[:8]}.pdf"


def _platform_label(platform: str) -> str:
    return "Google Meet" if platform == "google_meet" else "Microsoft Teams"


def _when_label(meeting: Meeting) -> str:
    start = meeting.started_at or meeting.created_at
    label = f"{format_date(start)} · {format_stamp(start)}"
    if meeting.ended_at:
        label += f" – {format_stamp(meeting.ended_at)}"
    return label


async def finalize(session: AsyncSession, meeting_id: uuid.UUID) -> MeetingDetail:
    meeting = await _get_meeting(session, meeting_id)
    segments = (
        await session.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.sequence)
        )
    ).scalars().all()
    if not segments:
        raise AppError("This meeting has no transcript yet.", 400)
    chat = (
        await session.execute(
            select(ChatMessage).where(ChatMessage.meeting_id == meeting_id).order_by(ChatMessage.sent_at)
        )
    ).scalars().all()
    meeting.status = "processing"
    meeting.error_message = None
    await session.commit()
    try:
        turns = [
            {
                "speaker": row.speaker_name,
                "text": row.english_text or row.original_text,
                "timestamp": row.timestamp_label,
            }
            for row in segments
        ]
        draft = await analyze(turns, meeting.title)
        await session.execute(delete(Decision).where(Decision.meeting_id == meeting_id))
        await session.execute(delete(Risk).where(Risk.meeting_id == meeting_id))
        await session.execute(delete(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id))
        for text in draft.decisions:
            session.add(Decision(meeting_id=meeting_id, text=text))
        for text in draft.risks:
            session.add(Risk(meeting_id=meeting_id, text=text))
        session.add(
            MeetingSummary(
                meeting_id=meeting_id,
                executive_summary=draft.executive_summary,
                detailed_summary=draft.detailed_summary,
                manager_summary=draft.manager_summary,
                next_steps=draft.next_steps,
                sentiment=draft.sentiment,
                model_name=draft.model_name,
            )
        )
        for action in draft.action_items:
            if await _action_exists(session, meeting_id, action.assignee, action.task):
                continue
            session.add(
                ActionItem(
                    meeting_id=meeting_id,
                    assignee_name=action.assignee,
                    description=action.task,
                    due_label=action.due_label,
                    status="open",
                )
            )
        meeting.sentiment = draft.sentiment
        meeting.ended_at = meeting.ended_at or utcnow()
        meeting.report_stale = False
        meeting.error_message = None
        await session.flush()
        participants = await _names(session, meeting_id)
        actions = (
            await session.execute(select(ActionItem).where(ActionItem.meeting_id == meeting_id).order_by(ActionItem.created_at))
        ).scalars().all()
        await reindex(
            session,
            meeting,
            [
                "\n".join(
                    [
                        f"Speaker: {row.speaker_name}",
                        f"Original: {row.original_text}",
                        f"Translated: {row.english_text}",
                        f"Timestamp: {row.timestamp_label}",
                    ]
                )
                for row in segments
            ],
            draft.executive_summary,
            decisions=list(draft.decisions),
            actions=[f"{row.assignee_name}: {row.description}" for row in actions],
        )
        filename = _report_filename(meeting)
        path = Path(get_settings().reports_dir) / filename
        build_pdf(
            ReportData(
                title=meeting.title,
                when_label=_when_label(meeting),
                platform=_platform_label(meeting.platform),
                participants=participants,
                sentiment=draft.sentiment,
                executive_summary=draft.executive_summary,
                detailed_summary=draft.detailed_summary,
                manager_summary=draft.manager_summary,
                decisions=draft.decisions,
                risks=draft.risks,
                next_steps=draft.next_steps,
                action_items=[(row.assignee_name, row.description, row.status) for row in actions],
                segments=[
                    (row.timestamp_label, row.speaker_name, row.original_text, row.english_text) for row in segments
                ],
                chat=[(row.timestamp_label, row.sender_name, row.english_text) for row in chat],
            ),
            path,
        )
        meeting.report_path = str(path)
        meeting.report_filename = filename
        meeting.status = "completed"
        await session.commit()
    except Exception as exc:
        logger.exception("finalize failed")
        await session.rollback()
        failed = await session.get(Meeting, meeting_id)
        message = exc.message if isinstance(exc, AppError) else "Report generation failed."
        if failed:
            failed.status = "failed"
            failed.error_message = message[:500]
            await session.commit()
        if isinstance(exc, AppError):
            raise
        raise AppError(message, 500) from exc
    detail = await get_meeting_detail(session, meeting_id)
    await hub.broadcast(str(meeting_id), {"type": "completed", "meeting_id": str(meeting_id)})
    return detail
