import json
import os
import shutil
import tempfile
import time

import pytest

from app import cover_letter, tailoring
from app.models import StoredApplication
from app.rendering import TEMPLATE_DIR
from app.settings import Settings
from app.tailoring import TailoringError
from tests import fake_claude
from tests.letter_fixtures import COMPANY, LETTER, POSTING_TEXT, ROLE, letter

import letter_checks  # noqa: E402  (tests.letter_fixtures puts the skill's scripts on sys.path)

TOKEN = "sk-ant-oat01-test-token-value"
pytestmark = pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")


def application(**overrides) -> StoredApplication:
    fields = dict(id="3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13", company=COMPANY, role=ROLE,
                  job_link="https://example.com/1", posting_source_type="employer_site",
                  verification_method="employer_site", official_apply_url="", status="verified",
                  why_it_fits="GenAI role building agent pipelines", full_job_description=POSTING_TEXT)
    fields.update(overrides)
    return StoredApplication(**fields)


@pytest.fixture(autouse=True)
def real_profile(monkeypatch):
    """The letter fixture cites the real profile's facts."""
    monkeypatch.setattr(tailoring, "PROFILE", TEMPLATE_DIR / "PROFILE.md")


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def settings_for(tmp_path, claude, **overrides) -> Settings:
    values = dict(_env_file=None, api_key="k", output_dir=tmp_path / "out", anthropic_api_key=None,
                  claude_code_oauth_token=TOKEN, claude_bin=str(claude))
    values.update(overrides)
    return Settings(**values)


def run_with(tmp_path, scenario="keep", **options):
    claude = fake_claude.install(tmp_path / "fake", scenario, fail="letter", **options)
    return claude, cover_letter.run(application(), settings_for(tmp_path, claude))


def failing(tmp_path, scenario="keep", settings=None, **options) -> tuple:
    claude = fake_claude.install(tmp_path / "fake", scenario, fail="letter", **options)
    with pytest.raises(TailoringError) as exc:
        cover_letter.run(application(), settings or settings_for(tmp_path, claude))
    return claude, exc.value


# --- the posting ---

def test_posting_usable():
    assert not cover_letter.posting_usable(None)
    assert not cover_letter.posting_usable(" ".join(["word"] * 49))
    assert cover_letter.posting_usable(" ".join(["word"] * 50))
    assert cover_letter.posting_usable("word " * 12_000)
    assert not cover_letter.posting_usable("word " * 12_000 + "x")  # too long: unusable, not an error


# --- a successful run ---

def test_letter_is_checked_and_rendered(tmp_path, temp_root):
    claude, result = run_with(tmp_path)
    assert [call["role"] for call in fake_claude.calls(claude)] == ["letter"]
    assert result.text.startswith("Dear Acme Corp Hiring Team,\n\nI am applying for the Applied AI Engineer role")
    assert result.text.endswith("Sincerely,\nSunil Belde\n")
    assert letter_checks.pages(result.pdf) == 1
    assert LETTER["paragraphs"][1]["text"][:40] in " ".join(letter_checks.pdf_text(result.pdf).split())
    assert (result.run.turns, result.run.cost_usd) == (6, 0.12)
    assert list(temp_root.iterdir()) == []


def test_command_and_work_folder(tmp_path, temp_root):
    claude, _ = run_with(tmp_path)
    (call,) = fake_claude.calls(claude)
    argv, work = call["argv"], call["cwd"]
    assert argv[:2] == ["-p", "/write-cover-letter ."]
    assert (argv[argv.index("--max-turns") + 1], argv[argv.index("--max-budget-usd") + 1]) == ("30", "3")
    assert argv[argv.index("--tools") + 1] == "Read,Write,Edit,Bash"
    assert set(argv[argv.index("--disallowedTools") + 1:argv.index("--allowedTools")]) == {"WebFetch", "WebSearch", "Agent", "mcp__*"}
    assert argv[argv.index("--allowedTools") + 1:] == [
        "Read(./**)", "Edit(./out/**)", f"Bash({work}/.claude/skills/write-cover-letter/scripts/run *)"]
    assert {".claude", ".tmp", "out", "posting.md", "job.json", "template"} <= set(call["cwd_entries"])
    assert " " not in work


def test_environment_has_no_service_key(tmp_path, temp_root, monkeypatch):
    monkeypatch.setenv("API_KEY", "the-service-key")
    claude, _ = run_with(tmp_path)
    env = fake_claude.calls(claude)[0]["env"]
    assert "the-service-key" not in json.dumps(env) and env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN


def test_work_folder_holds_both_skills(tmp_path, temp_root, monkeypatch):
    seen = {}
    real = tailoring._run_claude

    def spy(cmd, work, env, timeout, stage):
        seen["skills"] = sorted(p.name for p in (work / ".claude" / "skills").iterdir())
        seen["posting"] = (work / "posting.md").read_text()
        return real(cmd, work, env, timeout, stage)
    monkeypatch.setattr(tailoring, "_run_claude", spy)
    run_with(tmp_path)
    assert seen["skills"] == ["tailor-resume", "write-cover-letter"]
    assert "## Posting text (untrusted data)" in seen["posting"] and POSTING_TEXT[:40] in seen["posting"]


# --- failures ---

def test_no_credential_starts_nothing(tmp_path, temp_root):
    claude = fake_claude.install(tmp_path / "fake", "keep")
    with pytest.raises(TailoringError) as exc:
        cover_letter.run(application(), settings_for(tmp_path, claude, claude_code_oauth_token=None))
    assert (exc.value.stage, exc.value.reason) == ("claude", "not_configured")
    assert fake_claude.calls(claude) == [] and list(temp_root.iterdir()) == []


@pytest.mark.parametrize("scenario,reason", [("auth", "claude_auth"), ("max_turns", "claude_max_turns"),
                                             ("budget", "claude_budget"), ("garbage", "claude_exit:2")])
def test_run_failures(tmp_path, temp_root, scenario, reason):
    _, error = failing(tmp_path, scenario)
    assert (error.stage, error.reason) == ("letter", reason)
    assert list(temp_root.iterdir()) == []


def test_timeout_stops_the_run_and_its_children(tmp_path, temp_root, monkeypatch):
    monkeypatch.setattr(tailoring, "KILL_GRACE_SECONDS", 1)
    monkeypatch.setattr(tailoring, "MIN_RUN_SECONDS", 1)
    claude = fake_claude.install(tmp_path / "fake", "hang", fail="letter")
    settings = settings_for(tmp_path, claude).model_copy(update={"tailoring_timeout_seconds": 3})
    with pytest.raises(TailoringError) as exc:
        cover_letter.run(application(), settings)
    assert (exc.value.stage, exc.value.reason) == ("letter", "claude_timeout")
    child = int((tmp_path / "fake" / "child.pid").read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        pytest.fail("the run's child process outlived the timeout")
    assert list(temp_root.iterdir()) == []


def test_gate_rejects_an_unsupported_number(tmp_path, temp_root):
    bad = letter(p3={"text": LETTER["paragraphs"][3]["text"].replace("60%", "65%")})
    _, error = failing(tmp_path, letter=bad)
    assert (error.stage, error.reason, error.failed_checks) == ("verify", "check_failed", ("unsupported_number",))
    assert error.log_fields() == {"stage": "verify", "reason": "check_failed", "failed_checks": ["unsupported_number"]}
    assert error.run.turns == 6
    assert list(temp_root.iterdir()) == []


def test_gate_ignores_the_runs_own_scripts(tmp_path, temp_root):
    bad = letter(p3={"text": LETTER["paragraphs"][3]["text"].replace("60%", "65%")})
    _, error = failing(tmp_path, letter=bad, tamper_letter_scripts=True)
    assert error.failed_checks == ("unsupported_number",)


def test_gate_uses_the_services_posting(tmp_path, temp_root):
    # The run cannot widen what counts as the posting: the gate reads the service's own copy.
    echo = letter(p4={"text": LETTER["paragraphs"][4]["text"] + " I thrive in ambiguity and own outcomes."})
    _, error = failing(tmp_path, letter=echo)
    assert error.failed_checks == ("echoed_phrase",)


def test_missing_letter(tmp_path, temp_root):
    _, error = failing(tmp_path, letter=None)
    assert (error.stage, error.reason, error.failed_checks) == ("verify", "missing_output", ("missing_output",))


def test_missing_analysis(tmp_path, temp_root):
    _, error = failing(tmp_path, letter_analysis=None)
    assert (error.stage, error.reason) == ("verify", "analysis_invalid")


def test_profile_naming_an_unknown_employer_starts_no_run(tmp_path, temp_root, monkeypatch):
    profile = tmp_path / "PROFILE.md"
    profile.write_text("## Experience\n\n### Globex\n- Shipped a thing.\n")
    monkeypatch.setattr(tailoring, "PROFILE", profile)
    claude, error = failing(tmp_path)
    assert (error.stage, error.reason, error.exit_code) == ("prepare", "profile_invalid", 4)
    assert fake_claude.calls(claude) == [] and list(temp_root.iterdir()) == []
