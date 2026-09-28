from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def in_local(value: datetime) -> datetime:
    zone = ZoneInfo(get_settings().default_timezone)
    return as_utc(value).astimezone(zone)


def format_stamp(value: datetime) -> str:
    return in_local(value).strftime("%I:%M %p").lstrip("0")


def format_date(value: datetime) -> str:
    return in_local(value).strftime("%d %b %Y")


def file_date(value: datetime) -> str:
    return in_local(value).strftime("%Y_%m_%d")
