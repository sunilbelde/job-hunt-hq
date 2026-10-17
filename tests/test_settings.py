import pytest
from pydantic import ValidationError

from app.settings import Settings

REQUIRED = {
    "API_KEY": "k",
    "R2_ACCOUNT_ID": "a",
    "R2_ACCESS_KEY_ID": "id",
    "R2_SECRET_ACCESS_KEY": "s",
    "R2_BUCKET": "b",
}


@pytest.fixture
def env(monkeypatch):
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SIGNED_URL_TTL_SECONDS", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return monkeypatch


def test_loads_with_defaults(env):
    s = Settings(_env_file=None)
    assert s.signed_url_ttl_seconds == 604800
    assert s.anthropic_api_key is None


def test_missing_required_variable_names_it(env):
    env.delenv("R2_BUCKET")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "r2_bucket" in str(exc.value)


def test_empty_required_variable_rejected(env):
    env.setenv("API_KEY", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_ttl_over_max_rejected(env):
    env.setenv("SIGNED_URL_TTL_SECONDS", "604801")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-5"])
def test_ttl_non_positive_rejected(env, value):
    env.setenv("SIGNED_URL_TTL_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_values_not_in_error(env):
    env.setenv("SIGNED_URL_TTL_SECONDS", "999999")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "R2_SECRET" not in str(exc.value) and "secret-value" not in str(exc.value)
