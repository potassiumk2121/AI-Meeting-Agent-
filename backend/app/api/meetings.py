import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.errors import AppError
from app.models import Meeting
from app.schemas import EmailIn, IngestOut, JoinOut, MeetingCreate, MeetingDetail, MeetingOut, SpeakerRename, SyncOut
from app.services.emailer import send_meeting_report
from app.services.pipeline import (
    finalize,
    get_meeting_detail,
    ingest_audio,
    join_meeting,
    list_meetings,
    rename_speaker,
    sync_meeting,
)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
MAX_AUDIO = 25 * 1024 * 1024


@router.get("", response_model=list[MeetingOut])
async def get_meetings(
    status: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
) -> list[MeetingOut]:
    return await list_meetings(session, status, limit)


@router.post("", response_model=MeetingDetail)
async def create_meeting(
    body: MeetingCreate,
    session: AsyncSession = Depends(get_db),
) -> MeetingDetail:
    meeting = Meeting(
        title=body.title.strip(),
        platform=body.platform,
        join_url=(body.join_url or "").strip() or None,
        organizer_email=str(body.organizer_email) if body.organizer_email else None,
        status="scheduled",
    )
    session.add(meeting)
    await session.commit()
    return await get_meeting_detail(session, meeting.id)


@router.get("/{meeting_id}", response_model=MeetingDetail)
async def read_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> MeetingDetail:
    return await get_meeting_detail(session, meeting_id)


@router.delete("/{meeting_id}", status_code=204)
async def delete_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    meeting = await session.get(Meeting, meeting_id)
    if not meeting:
        raise AppError("Meeting not found.", 404)
    await session.delete(meeting)
    await session.commit()


@router.post("/{meeting_id}/join", response_model=JoinOut)
async def join(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> JoinOut:
    return await join_meeting(session, meeting_id)


@router.post("/{meeting_id}/sync", response_model=SyncOut)
async def sync(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> SyncOut:
    return await sync_meeting(session, meeting_id)


@router.post("/{meeting_id}/finalize", response_model=MeetingDetail)
async def end_meeting(
    meeting_id: uuid.UUID,
    email: bool = False,
    session: AsyncSession = Depends(get_db),
) -> MeetingDetail:
    detail = await finalize(session, meeting_id)
    settings = get_settings()
    if email or settings.auto_email:
        for recipient in settings.default_recipient_list:
            try:
                await send_meeting_report(session, meeting_id, recipient)
            except AppError:
                if email:
                    raise
        detail = await get_meeting_detail(session, meeting_id)
    return detail


@router.post("/{meeting_id}/audio", response_model=IngestOut)
async def upload_audio(
    meeting_id: uuid.UUID,
    file: UploadFile = File(...),
    speaker: str = Form(""),
    language: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
) -> IngestOut:
    audio = await file.read()
    if not audio:
        raise AppError("The audio file was empty.", 400)
    if len(audio) > MAX_AUDIO:
        raise AppError("Audio clips must be 25 MB or smaller.", 413)
    return await ingest_audio(
        session,
        meeting_id,
        audio=audio,
        filename=file.filename or "audio.webm",
        content_type=file.content_type or "application/octet-stream",
        speaker=speaker,
        language=language,
    )


@router.patch("/{meeting_id}/speakers", response_model=MeetingDetail)
async def rename_meeting_speaker(
    meeting_id: uuid.UUID,
    body: SpeakerRename,
    session: AsyncSession = Depends(get_db),
) -> MeetingDetail:
    return await rename_speaker(session, meeting_id, body.from_name, body.to_name)


@router.get("/{meeting_id}/report.pdf")
async def download_report(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    meeting = await session.get(Meeting, meeting_id)
    if not meeting or not meeting.report_path:
        raise AppError("The PDF is not ready yet.", 404)
    from pathlib import Path

    if not Path(meeting.report_path).exists():
        raise AppError("The PDF is not ready yet.", 404)
    return FileResponse(
        meeting.report_path,
        media_type="application/pdf",
        filename=meeting.report_filename or "meeting.pdf",
    )


@router.post("/{meeting_id}/email", response_model=MeetingDetail)
async def email_report(
    meeting_id: uuid.UUID,
    body: EmailIn,
    session: AsyncSession = Depends(get_db),
) -> MeetingDetail:
    recipients = [str(item) for item in body.recipients] or get_settings().default_recipient_list
    if not recipients:
        raise AppError("Add at least one recipient.", 400)
    for recipient in recipients:
        await send_meeting_report(session, meeting_id, recipient)
    return await get_meeting_detail(session, meeting_id)
