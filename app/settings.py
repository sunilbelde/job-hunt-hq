from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OUTPUT_DIR = Path.home() / "Library" / "Application Support" / "job-hunt-hq"


class Settings(BaseSettings):
    """Environment configuration, validated when the app is created."""

    # extra="ignore" also keeps retired variables (LINK_SIGNING_SECRET, PUBLIC_BASE_URL,
    # SIGNED_URL_TTL_SECONDS, OUTPUT_RETENTION_DAYS) in an old .env from failing startup.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1)
    output_dir: Path = DEFAULT_OUTPUT_DIR
    anthropic_api_key: SecretStr | None = None

    @field_validator("output_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()


@lru_cache
def get_settings() -> Settings:
    return Settings()
