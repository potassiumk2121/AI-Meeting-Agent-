import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _email(value: str) -> str:
    cleaned = value.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
        raise ValueError("Enter a valid email address")
    return cleaned


EmailAddress = Annotated[str, AfterValidator(_email)]


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailAddress
    name: str

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginIn(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=200)


class RegisterIn(BaseModel):
    email: EmailAddress
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class PublicSettings(BaseModel):
    company_name: str
    company_tagline: str
    brand_color: str


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    platform: Literal["teams", "google_meet"]
    join_url: str | None = None
    organizer_email: EmailAddress | None = None


class MeetingOut(BaseModel):
    id: uuid.UUID
    title: str
    platform: str
    status: str
    sentiment: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    join_url: str | None
    organizer_email: str | None = None
    participants: list[str]
    report_ready: bool
    report_stale: bool
    report_filename: str | None = None
    error_message: str | None = None
    duration_minutes: int | None = None


class SegmentOut(BaseModel):
    id: uuid.UUID
    speaker_name: str
    timestamp_label: str
    original_text: str
    original_language: str
    english_text: str
    started_at: datetime
    source: str


class ChatOut(BaseModel):
    id: uuid.UUID
    sender_name: str
    original_text: str
    english_text: str
    timestamp_label: str
    sent_at: datetime


class ActionOut(BaseModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    assignee_name: str
    description: str
    status: str
    due_label: str | None
    created_at: datetime


class DecisionOut(BaseModel):
    id: uuid.UUID
    text: str


class RiskOut(BaseModel):
    id: uuid.UUID
    text: str


class SummaryOut(BaseModel):
    executive_summary: str
    detailed_summary: str
    manager_summary: str
    next_steps: list[str]
    sentiment: str
    model_name: str


class EmailOut(BaseModel):
    recipients: list[str]
    status: str
    error: str | None
    sent_at: datetime | None


class ParticipantOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None


class MeetingDetail(BaseModel):
    meeting: MeetingOut
    participants: list[ParticipantOut]
    segments: list[SegmentOut]
    chat: list[ChatOut]
    actions: list[ActionOut]
    decisions: list[DecisionOut]
    risks: list[RiskOut]
    summary: SummaryOut | None
    email: EmailOut | None


class IngestOut(BaseModel):
    duplicate: bool = False
    segment: SegmentOut | None = None
    actions: list[ActionOut] = []
    sentiment: str | None = None
    chat: ChatOut | None = None


class JoinOut(BaseModel):
    status: str
    websocket_path: str
    pulled_segments: int
    warning: str | None = None


class SyncOut(BaseModel):
    added: int
    warning: str | None = None


class EmailIn(BaseModel):
    recipients: list[EmailAddress] = []


class SendReportIn(BaseModel):
    recipient: EmailAddress
    meeting_id: uuid.UUID


class SendReportOut(BaseModel):
    status: str
    recipient: str
    filename: str


class ActionUpdate(BaseModel):
    status: Literal["open", "done"]


class TaskOut(BaseModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    meeting_title: str
    assignee_name: str
    description: str
    status: str
    due_label: str | None
    created_at: datetime


class DecisionRow(BaseModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    meeting_title: str
    text: str
    created_at: datetime


class RiskRow(BaseModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    meeting_title: str
    text: str
    created_at: datetime


class PersonOut(BaseModel):
    name: str
    email: str | None
    meetings: int
    last_seen: datetime | None


class DashboardOut(BaseModel):
    meetings: int
    live_meetings: int
    open_tasks: int
    decisions: int
    participants: int
    minutes_this_week: int = 0
    sentiment: dict[str, int] = Field(default_factory=dict)
    follow_ups: list[str] = Field(default_factory=list)
    recent_meetings: list[MeetingOut]
    open_task_preview: list[TaskOut]


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=8, ge=1, le=25)


class SearchHit(BaseModel):
    meeting_id: uuid.UUID
    meeting_title: str
    snippet: str
    score: float


class AskIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    meeting_id: uuid.UUID | None = None


class AskQuote(BaseModel):
    meeting_id: uuid.UUID
    meeting_title: str
    speaker: str
    timestamp: str
    original: str
    english: str


class AskOut(BaseModel):
    answer: str
    summary: str
    quotes: list[AskQuote]


class SpeakerStat(BaseModel):
    name: str
    lines: int
    share: float


class PeriodReport(BaseModel):
    label: str
    start: datetime
    end: datetime
    meetings: int
    minutes: int
    decisions: int
    open_actions: int
    sentiment: dict[str, int]
    speakers: list[SpeakerStat]
    highlights: list[str]


class FollowUpOut(BaseModel):
    meeting_id: uuid.UUID
    meeting_title: str
    assignee_name: str
    description: str
    due_label: str | None
    reminder: str


class CalendarItem(BaseModel):
    title: str
    start: datetime
    end: datetime
    join_url: str | None
    organizer: str | None


class CalendarOut(BaseModel):
    configured: bool
    detail: str
    events: list[CalendarItem]


class ScanOut(BaseModel):
    started: int
    closed: int
    detail: str
