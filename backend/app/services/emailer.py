import asyncio
import logging
from pathlib import Path
from xml.sax.saxutils import escape

import resend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import AppError
from app.models import EmailDelivery, Meeting, MeetingSummary
from app.timeutil import utcnow

logger = logging.getLogger(__name__)


def render_email_html(company: str, title: str, executive_summary: str) -> str:
    return (
        f"<p>{escape(company)} meeting report: <strong>{escape(title)}</strong></p>"
        f"<p>{escape(executive_summary)}</p>"
        "<p>The PDF is attached. It includes the transcript, English translation, "
        "decisions, risks, and action items.</p>"
    )


def _send_with_resend(api_key: str, sender: str, recipient: str, subject: str, html: str, filename: str, pdf: bytes) -> str:
    resend.api_key = api_key
    result = resend.Emails.send(
        {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "html": html,
            "attachments": [
                {
                    "filename": filename,
                    "content": list(pdf),
                    "content_type": "application/pdf",
                }
            ],
        }
    )
    if isinstance(result, dict):
        return str(result.get("id") or "")
    return str(getattr(result, "id", "") or "")


async def send_meeting_report(session: AsyncSession, meeting_id, recipient: str) -> dict:
    from app.services.pipeline import finalize

    meeting = await session.get(Meeting, meeting_id)
    if not meeting:
        raise AppError("Meeting not found.", 404)
    needs_pdf = (
        meeting.status != "completed"
        or not meeting.report_path
        or not Path(meeting.report_path).exists()
    )
    if needs_pdf:
        await finalize(session, meeting_id)
        meeting = await session.get(Meeting, meeting_id)
    if not meeting or not meeting.report_path or not Path(meeting.report_path).exists():
        raise AppError("The PDF could not be generated.", 500)

    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        raise AppError("Set RESEND_API_KEY and EMAIL_FROM before sending the report.", 400)

    pdf = Path(meeting.report_path).read_bytes()
    summary = (
        await session.execute(select(MeetingSummary).where(MeetingSummary.meeting_id == meeting.id))
    ).scalar_one_or_none()
    executive = summary.executive_summary if summary else ""
    filename = meeting.report_filename or "meeting.pdf"
    subject = f"{settings.company_name} meeting report: {meeting.title}"
    html = render_email_html(settings.company_name, meeting.title, executive)
    try:
        await asyncio.to_thread(
            _send_with_resend,
            settings.resend_api_key,
            settings.email_from,
            recipient,
            subject,
            html,
            filename,
            pdf,
        )
    except AppError:
        raise
    except Exception as exc:
        logger.exception("resend send failed")
        message = getattr(exc, "message", None) or "Resend could not send the report."
        await _record(session, meeting, recipient, "failed", str(message)[:300])
        raise AppError(str(message)[:300], 502) from exc

    await _record(session, meeting, recipient, "sent", None)
    return {"status": "sent", "recipient": recipient, "filename": filename}


async def _record(
    session: AsyncSession,
    meeting: Meeting,
    recipient: str,
    status: str,
    error: str | None,
) -> None:
    session.add(
        EmailDelivery(
            meeting_id=meeting.id,
            recipients=[recipient],
            status=status,
            error=error,
            sent_at=utcnow() if status == "sent" else None,
        )
    )
    await session.commit()
