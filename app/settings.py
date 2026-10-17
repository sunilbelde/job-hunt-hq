from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_SIGNED_URL_TTL_SECONDS = 604800


class Settings(BaseSettings):
    """Environment configuration, validated when the app is created."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: SecretStr = Field(min_length=1)
    r2_account_id: str = Field(min_length=1)
    r2_access_key_id: SecretStr = Field(min_length=1)
    r2_secret_access_key: SecretStr = Field(min_length=1)
    r2_bucket: str = Field(min_length=1)
    signed_url_ttl_seconds: int = Field(
        default=MAX_SIGNED_URL_TTL_SECONDS, gt=0, le=MAX_SIGNED_URL_TTL_SECONDS
    )
    anthropic_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
