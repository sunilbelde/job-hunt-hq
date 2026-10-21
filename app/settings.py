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
    # Claude credentials for resume tailoring. With both set, Claude runs get only the API key.
    anthropic_api_key: SecretStr | None = None
    claude_code_oauth_token: SecretStr | None = None  # from `claude setup-token`; uses the owner's Claude plan
    tailoring_model: str = Field(default="claude-opus-5-5", min_length=1)
    tailoring_timeout_seconds: int = Field(default=420, ge=60, le=480)
    tailoring_max_budget_usd: float = Field(default=3.0, gt=0)
    claude_bin: str = Field(default="claude", min_length=1)
    # Serves /docs, /redoc and /openapi.json. Local development only: the launchd job pins it off.
    api_docs_enabled: bool = False

    @field_validator("output_dir")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("anthropic_api_key", "claude_code_oauth_token", mode="before")
    @classmethod
    def _blank_is_unset(cls, value):
        # .env.example ships `ANTHROPIC_API_KEY=`; an empty credential means none.
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
