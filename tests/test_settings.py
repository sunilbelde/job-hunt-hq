from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import DEFAULT_OUTPUT_DIR, Settings

API_KEY = "k" * 32

OPTIONAL = [
    "OUTPUT_DIR",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "TAILORING_MODEL",
    "TAILORING_TIMEOUT_SECONDS",
    "TAILORING_MAX_BUDGET_USD",
    "CLAUDE_BIN",
    "API_DOCS_ENABLED",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
]
# Settings from the signed-link era: an old .env may still carry them.
RETIRED = ["LINK_SIGNING_SECRET", "PUBLIC_BASE_URL", "SIGNED_URL_TTL_SECONDS", "OUTPUT_RETENTION_DAYS"]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("API_KEY", API_KEY)
    for name in OPTIONAL + RETIRED:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_loads_with_only_api_key(env):
    s = Settings(_env_file=None)
    assert s.api_key.get_secret_value() == API_KEY
    assert s.output_dir == DEFAULT_OUTPUT_DIR
    assert s.anthropic_api_key is None


def test_missing_api_key_names_it(env):
    env.delenv("API_KEY")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "api_key" in str(exc.value)


def test_empty_api_key_rejected(env):
    env.setenv("API_KEY", "")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "api_key" in str(exc.value)


def test_output_dir_expands_home(env):
    env.setenv("OUTPUT_DIR", "~/outputs")
    assert Settings(_env_file=None).output_dir == Path.home() / "outputs"


def test_retired_variables_ignored_even_when_invalid(env):
    env.setenv("LINK_SIGNING_SECRET", "short")
    env.setenv("PUBLIC_BASE_URL", "not a url")
    env.setenv("SIGNED_URL_TTL_SECONDS", "999999")
    env.setenv("OUTPUT_RETENTION_DAYS", "-1")
    s = Settings(_env_file=None)
    assert not any(hasattr(s, name.lower()) for name in RETIRED)


def test_retired_variables_in_env_file_ignored(env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"API_KEY={API_KEY}\nLINK_SIGNING_SECRET=short\nSIGNED_URL_TTL_SECONDS=999999\n"
        "PUBLIC_BASE_URL=https://mac-mini.tail1234.ts.net\nOUTPUT_RETENTION_DAYS=30\n"
    )
    env.delenv("API_KEY")
    assert Settings(_env_file=env_file).api_key.get_secret_value() == API_KEY


def test_secret_values_not_in_error(env):
    env.setenv("OUTPUT_DIR", "")
    env.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    env.delenv("API_KEY")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "sk-secret-value" not in str(exc.value)


def test_api_docs_disabled_by_default(env):
    assert Settings(_env_file=None).api_docs_enabled is False


def test_api_docs_enabled_from_env_file(env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_DOCS_ENABLED=true\n")
    assert Settings(_env_file=env_file).api_docs_enabled is True


def test_process_env_overrides_env_file_for_api_docs(env, tmp_path):
    # The launchd job relies on this to keep docs off whatever .env says.
    env_file = tmp_path / ".env"
    env_file.write_text("API_DOCS_ENABLED=true\n")
    env.setenv("API_DOCS_ENABLED", "false")
    assert Settings(_env_file=env_file).api_docs_enabled is False


def test_invalid_api_docs_value_names_it(env):
    env.setenv("API_DOCS_ENABLED", "maybe")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "api_docs_enabled" in str(exc.value)


# --- resume tailoring ---

def test_tailoring_defaults(env):
    s = Settings(_env_file=None)
    assert s.claude_code_oauth_token is None
    assert (s.tailoring_model, s.tailoring_timeout_seconds, s.tailoring_max_budget_usd, s.claude_bin) == (
        "claude-opus-5-5", 420, 3.0, "claude")


@pytest.mark.parametrize("value", ["30", "481", "abc"])
def test_invalid_tailoring_timeout_names_it(env, value):
    env.setenv("TAILORING_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "tailoring_timeout_seconds" in str(exc.value)


def test_invalid_budget_names_it(env):
    env.setenv("TAILORING_MAX_BUDGET_USD", "0")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "tailoring_max_budget_usd" in str(exc.value)


def test_subscription_token_never_in_errors(env):
    env.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-secret-token-value")
    env.setenv("TAILORING_TIMEOUT_SECONDS", "abc")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "sk-ant-oat01-secret-token-value" not in str(exc.value)


def test_blank_credentials_mean_none(env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CLAUDE_CODE_OAUTH_TOKEN=\nANTHROPIC_API_KEY=   \n")
    s = Settings(_env_file=env_file)
    assert s.claude_code_oauth_token is None and s.anthropic_api_key is None


def test_env_example_lists_the_tailoring_settings():
    example = (Path(__file__).resolve().parent.parent / ".env.example").read_text()
    names = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line and not line.startswith("#")}
    assert {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "TAILORING_MODEL", "TAILORING_TIMEOUT_SECONDS",
            "TAILORING_MAX_BUDGET_USD", "CLAUDE_BIN"} <= names
    assert "reserved" not in example
