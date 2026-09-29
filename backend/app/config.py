from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://meeting:meeting@localhost:5433/meeting_intel"
    jwt_secret: str = "dev-only-change-me-use-a-long-random-secret"
    jwt_exp_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    allow_registration: bool = False

    admin_email: str = "admin@rigora.local"
    admin_password: str = "ChangeMe!2026"
    admin_name: str = "RIGORA Admin"

    company_name: str = "Development Monitors"
    company_tagline: str = "AI Meeting Intelligence"
    brand_color: str = "#102033"
    default_timezone: str = "Asia/Kolkata"

    @field_validator("brand_color")
    @classmethod
    def brand_color_or_default(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) == 7 and text.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in text[1:]):
            return text
        return "#102033"

    ai_provider: str = "openai"
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_transcribe_model: str = "whisper-1"
    openai_embed_model: str = "text-embedding-3-small"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    speech_provider: str = "openai"
    azure_speech_key: str = ""
    azure_speech_region: str = ""

    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    graph_sender: str = ""
    resend_api_key: str = ""
    email_from: str = ""
    email_default_recipients: str = ""
    auto_email: bool = False

    webhook_url: str = ""
    webhook_secret: str = ""

    google_credentials_file: str = ""
    google_delegated_user: str = ""

    reports_dir: str = "data/reports"
    calendar_poll_seconds: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def default_recipient_list(self) -> list[str]:
        return [item.strip() for item in self.email_default_recipients.split(",") if item.strip()]

    @property
    def graph_configured(self) -> bool:
        return bool(self.azure_tenant_id and self.azure_client_id and self.azure_client_secret)

    @property
    def google_configured(self) -> bool:
        return bool(self.google_credentials_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
