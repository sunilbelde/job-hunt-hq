from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_SIGNED_URL_TTL_SECONDS = 604800
DEFAULT_OUTPUT_DIR = Path.home() / "Library" / "Application Support" / "job-hunt-hq"


class Settings(BaseSettings):
    """Environment configuration, validated when the app is created."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1)
    link_signing_secret: SecretStr = Field(min_length=32)
    public_base_url: str = Field(min_length=1)
    output_dir: Path = DEFAULT_OUTPUT_DIR
    output_retention_days: int = Field(default=30, gt=0)
    signed_url_ttl_seconds: int = Field(
        default=MAX_SIGNED_URL_TTL_SECONDS, gt=0, le=MAX_SIGNED_URL_TTL_SECONDS
    )
    anthropic_api_key: SecretStr | None = None

    @field_validator("public_base_url")
    @classmethod
    def _absolute_http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("must be an absolute http or https URL")
        if parts.query or parts.fragment:
            raise ValueError("must not contain a query or fragment")
        return value.rstrip("/")

    @field_validator("output_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()

    @model_validator(mode="after")
    def _retention_covers_ttl(self) -> "Settings":
        if self.output_retention_days * 86400 < self.signed_url_ttl_seconds:
            raise ValueError(
                "OUTPUT_RETENTION_DAYS must cover SIGNED_URL_TTL_SECONDS "
                "(files would be deleted while links to them are still valid)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
