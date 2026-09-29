import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote
import httpx

from app.config import get_settings
from app.errors import AppError
from app.services.vtt import parse_vtt
from app.timeutil import as_utc, format_stamp, utcnow

logger = logging.getLogger(__name__)
_tokens: dict[str, tuple[str, float]] = {}


@dataclass
class PulledLine:
    speaker: str
    text: str
    timestamp_label: str | None = None
    language: str | None = None


@dataclass
class PullResult:
    external_id: str | None
    lines: list[PulledLine]
    warning: str | None = None


async def graph_token() -> str:
    settings = get_settings()
    if not settings.graph_configured:
        raise AppError(
            "Microsoft Graph is not configured. Set AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET.",
            400,
        )
    cached = _tokens.get("graph")
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    url = f"https://login.microsoftonline.com/{settings.azure_tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": settings.azure_client_id,
        "client_secret": settings.azure_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, data=payload)
    if response.status_code >= 400:
        logger.warning("graph token failed with status %s", response.status_code)
        raise AppError("Microsoft Graph rejected the app credentials.", 502)
    body = response.json()
    token = body["access_token"]
    _tokens["graph"] = (token, time.time() + int(body.get("expires_in", 3600)))
    return token


def _stamp_from_offset(started_at, offset_ms: int) -> str:
    if started_at is not None:
        moment = as_utc(started_at) + timedelta(milliseconds=offset_ms)
        return format_stamp(moment)
    total = offset_ms // 1000
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


async def pull_for_meeting(meeting) -> PullResult:
    if meeting.platform == "teams":
        return await _pull_teams(meeting)
    if meeting.platform == "google_meet":
        return await _pull_google(meeting)
    return PullResult(None, [], "This platform has no transcript connector.")


async def ensure_transcript_subscription(meeting) -> str | None:
    settings = get_settings()
    if meeting.platform != "teams" or not settings.webhook_url or not meeting.external_id:
        return None
    organizer = meeting.organizer_email or settings.graph_sender
    if not organizer or not settings.graph_configured:
        return None
    token = await graph_token()
    expiry = (utcnow() + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "changeType": "created",
        "notificationUrl": settings.webhook_url,
        "resource": f"users/{organizer}/onlineMeetings/{meeting.external_id}/transcripts",
        "expirationDateTime": expiry,
    }
    if settings.webhook_secret:
        body["clientState"] = settings.webhook_secret
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://graph.microsoft.com/v1.0/subscriptions",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
    if response.status_code >= 400:
        logger.warning("graph subscription failed with status %s", response.status_code)
        return None
    return response.json().get("id")


async def _graph_get(url: str, *, accept: str = "application/json", params: dict | None = None) -> httpx.Response:
    token = await graph_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": accept}
    async with httpx.AsyncClient(timeout=45) as client:
        return await client.get(url, headers=headers, params=params)


async def _pull_teams(meeting) -> PullResult:
    settings = get_settings()
    if not settings.graph_configured:
        return PullResult(
            meeting.external_id,
            [],
            "Live session is open. Add Microsoft Graph credentials to pull Teams transcripts.",
        )
    organizer = meeting.organizer_email or settings.graph_sender
    if not organizer:
        return PullResult(
            meeting.external_id,
            [],
            "Live session is open. Set the organizer email or GRAPH_SENDER to pull the Teams transcript.",
        )
    external_id = meeting.external_id
    try:
        if not external_id and meeting.join_url:
            safe = meeting.join_url.replace("'", "''")
            response = await _graph_get(
                f"https://graph.microsoft.com/v1.0/users/{quote(organizer)}/onlineMeetings",
                params={"$filter": f"JoinWebUrl eq '{safe}'"},
            )
            if response.status_code >= 400:
                return PullResult(
                    None,
                    [],
                    "The official Teams transcript is not available for this link. Microphone notes still work.",
                )
            values = response.json().get("value") or []
            if not values:
                return PullResult(
                    None,
                    [],
                    "No Teams meeting matched that join link. Microphone notes still work.",
                )
            external_id = values[0].get("id")
        if not external_id:
            return PullResult(None, [], "Live session is open. Paste a join link to pull the Teams transcript.")
        listed = await _graph_get(
            f"https://graph.microsoft.com/v1.0/users/{quote(organizer)}/onlineMeetings/{external_id}/transcripts"
        )
        if listed.status_code >= 400:
            return PullResult(external_id, [], "Live session is open. Graph could not list transcripts yet.")
        transcripts = listed.json().get("value") or []
        if not transcripts:
            return PullResult(external_id, [], "Live session is open. Teams has not published a transcript yet.")
        transcript_id = transcripts[-1].get("id")
        content = await _graph_get(
            f"https://graph.microsoft.com/v1.0/users/{quote(organizer)}/onlineMeetings/{external_id}/transcripts/{transcript_id}/content",
            accept="text/vtt",
        )
        if content.status_code >= 400:
            return PullResult(external_id, [], "Live session is open. The Teams transcript could not be downloaded.")
        lines = [
            PulledLine(
                speaker=cue["speaker"],
                text=cue["text"],
                timestamp_label=_stamp_from_offset(meeting.started_at, cue["offset_ms"]),
                language=None,
            )
            for cue in parse_vtt(content.text)
        ]
        return PullResult(external_id, lines, None)
    except AppError as exc:
        return PullResult(external_id, [], exc.message)
    except Exception:
        logger.exception("teams transcript pull failed")
        return PullResult(external_id, [], "Live session is open. Teams transcript pull failed.")


def _meet_code(url: str | None) -> str | None:
    if not url:
        return None
    import re

    match = re.search(r"meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})", url)
    return match.group(1) if match else None


def _google_token() -> str:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import service_account

    settings = get_settings()
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_credentials_file,
        scopes=["https://www.googleapis.com/auth/meetings.space.readonly"],
    )
    if settings.google_delegated_user:
        credentials = credentials.with_subject(settings.google_delegated_user)
    credentials.refresh(GoogleRequest())
    return credentials.token


async def _pull_google(meeting) -> PullResult:
    import asyncio
    from datetime import datetime

    settings = get_settings()
    if not settings.google_configured:
        return PullResult(
            meeting.external_id,
            [],
            "Live session is open. Add a Google service account to pull Meet transcripts.",
        )
    try:
        token = await asyncio.to_thread(_google_token)
    except Exception:
        logger.exception("google auth failed")
        return PullResult(meeting.external_id, [], "Google credentials could not be loaded. Live ingest is still open.")

    headers = {"Authorization": f"Bearer {token}"}
    params = {}
    code = _meet_code(meeting.join_url)
    if code:
        params["filter"] = f'space.meeting_code="{code}"'
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            listed = await client.get(
                "https://meet.googleapis.com/v2/conferenceRecords",
                headers=headers,
                params=params or None,
            )
            if listed.status_code >= 400:
                return PullResult(None, [], "Google Meet could not list conference records. Live ingest is still open.")
            records = listed.json().get("conferenceRecords") or []
            if not records:
                return PullResult(None, [], "No Google Meet conference record was found yet. Live ingest is still open.")
            record_name = records[0]["name"]
            people = await client.get(f"https://meet.googleapis.com/v2/{record_name}/participants", headers=headers)
            names = {}
            if people.status_code < 400:
                for person in people.json().get("participants") or []:
                    names[person.get("name")] = _person_name(person)
            transcripts = await client.get(f"https://meet.googleapis.com/v2/{record_name}/transcripts", headers=headers)
            if transcripts.status_code >= 400:
                return PullResult(record_name, [], "Live session is open. Meet transcripts are not available yet.")
            docs = transcripts.json().get("transcripts") or []
            if not docs:
                return PullResult(record_name, [], "Live session is open. Meet has not published a transcript yet.")
            entries = await client.get(
                f"https://meet.googleapis.com/v2/{docs[-1]['name']}/entries",
                headers=headers,
            )
            if entries.status_code >= 400:
                return PullResult(record_name, [], "Live session is open. Meet transcript entries could not be read.")
            lines: list[PulledLine] = []
            for entry in entries.json().get("transcriptEntries") or []:
                text = (entry.get("text") or "").strip()
                if not text:
                    continue
                started = entry.get("startTime")
                label = None
                if started:
                    try:
                        label = format_stamp(datetime.fromisoformat(started.replace("Z", "+00:00")))
                    except Exception:
                        label = None
                lines.append(
                    PulledLine(
                        speaker=names.get(entry.get("participant"), "Participant"),
                        text=text,
                        timestamp_label=label,
                        language=(entry.get("languageCode") or "en").split("-")[0],
                    )
                )
            return PullResult(record_name, lines, None)
    except Exception:
        logger.exception("google meet pull failed")
        return PullResult(meeting.external_id, [], "Live session is open. Google Meet transcript pull failed.")


def _graph_time(value: dict | None):
    from datetime import datetime, timezone

    if not value or not value.get("dateTime"):
        return None
    raw = str(value["dateTime"]).replace("Z", "")
    parsed = datetime.fromisoformat(raw[:26])
    return parsed.replace(tzinfo=timezone.utc)


async def list_calendar_events(start, end) -> list[dict]:
    settings = get_settings()
    if not settings.graph_configured or not settings.graph_sender:
        raise AppError("Set Azure app credentials and GRAPH_SENDER to read the Outlook calendar.", 400)
    url = f"https://graph.microsoft.com/v1.0/users/{quote(settings.graph_sender)}/calendarView"
    token = await graph_token()
    headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'}
    params = {
        "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "$select": "subject,start,end,isOnlineMeeting,onlineMeeting,organizer",
        "$top": "50",
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(url, headers=headers, params=params)
    if response.status_code >= 400:
        logger.warning("graph calendarView failed with status %s", response.status_code)
        raise AppError("Outlook calendar could not be read. Grant Calendars.Read to the Graph app.", 502)
    events = []
    for item in response.json().get("value") or []:
        online = item.get("onlineMeeting") or {}
        join_url = online.get("joinUrl") or online.get("joinWebUrl")
        organizer = ((item.get("organizer") or {}).get("emailAddress") or {}).get("address")
        started = _graph_time(item.get("start"))
        ended = _graph_time(item.get("end"))
        if not started or not ended:
            continue
        events.append(
            {
                "title": (item.get("subject") or "Teams meeting")[:200],
                "start": started,
                "end": ended,
                "join_url": join_url,
                "organizer": organizer,
                "online": bool(item.get("isOnlineMeeting") or join_url),
            }
        )
    return events


def _person_name(person: dict) -> str:
    for key in ("signedinUser", "anonymousUser", "phoneUser"):
        block = person.get(key) or {}
        if isinstance(block, dict):
            name = block.get("displayName") or block.get("name")
            if name:
                return str(name)
    return "Participant"
