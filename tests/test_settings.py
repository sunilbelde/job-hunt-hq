from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import DEFAULT_OUTPUT_DIR, Settings

SIGNING_SECRET = "s" * 32

REQUIRED = {
    "API_KEY": "k",
    "LINK_SIGNING_SECRET": SIGNING_SECRET,
    "PUBLIC_BASE_URL": "https://mac-mini.tail1234.ts.net",
}
OPTIONAL = [
    "OUTPUT_DIR",
    "OUTPUT_RETENTION_DAYS",
    "SIGNED_URL_TTL_SECONDS",
    "ANTHROPIC_API_KEY",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
]


@pytest.fixture
def env(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    for name in OPTIONAL:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_loads_with_defaults_and_no_cloud_variables(env):
    s = Settings(_env_file=None)
    assert s.signed_url_ttl_seconds == 604800
    assert s.output_retention_days == 30
    assert s.output_dir == DEFAULT_OUTPUT_DIR
    assert s.anthropic_api_key is None


def test_missing_required_variable_names_it(env):
    env.delenv("LINK_SIGNING_SECRET")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "link_signing_secret" in str(exc.value)


def test_empty_required_variable_rejected(env):
    env.setenv("API_KEY", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_short_signing_secret_rejected_without_echo(env):
    env.setenv("LINK_SIGNING_SECRET", "short-secret-val")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "link_signing_secret" in str(exc.value)
    assert "short-secret-val" not in str(exc.value)


@pytest.mark.parametrize("value", ["mac-mini:8080", "/files", "ftp://host", "https://host/?a=1", "https://host/#x"])
def test_bad_public_base_url_rejected(env, value):
    env.setenv("PUBLIC_BASE_URL", value)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "public_base_url" in str(exc.value)


def test_public_base_url_trailing_slash_stripped(env):
    env.setenv("PUBLIC_BASE_URL", "https://mac-mini.tail1234.ts.net/")
    assert Settings(_env_file=None).public_base_url == "https://mac-mini.tail1234.ts.net"


def test_output_dir_expands_home(env):
    env.setenv("OUTPUT_DIR", "~/outputs")
    assert Settings(_env_file=None).output_dir == Path.home() / "outputs"


def test_ttl_over_max_rejected(env):
    env.setenv("SIGNED_URL_TTL_SECONDS", "604801")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-5"])
def test_ttl_non_positive_rejected(env, value):
    env.setenv("SIGNED_URL_TTL_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_retention_non_positive_rejected(env, value):
    env.setenv("OUTPUT_RETENTION_DAYS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_retention_shorter_than_ttl_names_both(env):
    env.setenv("OUTPUT_RETENTION_DAYS", "3")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "OUTPUT_RETENTION_DAYS" in str(exc.value) and "SIGNED_URL_TTL_SECONDS" in str(exc.value)


def test_retention_with_short_ttl_accepted(env):
    env.setenv("OUTPUT_RETENTION_DAYS", "1")
    env.setenv("SIGNED_URL_TTL_SECONDS", "86400")
    assert Settings(_env_file=None).output_retention_days == 1


def test_secret_values_not_in_error(env):
    env.setenv("SIGNED_URL_TTL_SECONDS", "999999")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert SIGNING_SECRET not in str(exc.value)
