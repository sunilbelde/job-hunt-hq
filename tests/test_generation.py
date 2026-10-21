from unittest.mock import patch

import pytest

from app.generation import generate_output
from app.models import StoredApplication
from app.settings import Settings
from app.tailoring import Match, RunStats, TailoringError, TailoringResult

SETTINGS = Settings(_env_file=None, api_key="k", output_dir="/tmp/job-hunt-hq-unused")
POSTING = " ".join(["word"] * 60)


def application(posting=POSTING) -> StoredApplication:
    return StoredApplication(
        id="3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13", company="Acme", role="Engineer", job_link="https://example.com/1",
        posting_source_type="employer_site", verification_method="employer_site",
        official_apply_url="", status="verified", full_job_description=posting,
    )


def generate(app, result=None, error=None):
    with patch("app.generation.render_pdf", return_value=b"%PDF-base") as render, \
         patch("app.generation.tailoring.run", return_value=result, side_effect=error) as run:
        return generate_output(app, SETTINGS), render, run


@pytest.mark.parametrize("posting", [None, "", "too short to score"])
def test_unusable_posting_gets_the_base_resume_unscored(posting):
    out, render, run = generate(application(posting))
    render.assert_called_once_with()
    run.assert_not_called()
    assert (out.content, out.content_type, out.extension) == (b"%PDF-base", "application/pdf", "pdf")
    assert (out.match, out.run) == (Match("no_job_description"), None)


def test_strong_match_saves_the_base_resume():
    app = application()
    out, render, run = generate(app, TailoringResult(Match("base_meets_threshold", 82), None, RunStats(5, 0.1)))
    run.assert_called_once_with(app, SETTINGS)
    render.assert_called_once_with()
    assert (out.content, out.match, out.run.turns) == (b"%PDF-base", Match("base_meets_threshold", 82), 5)


def test_weak_match_saves_the_tailored_pdf():
    out, render, _ = generate(application(), TailoringResult(Match("tailored", 58, 77), b"%PDF-tailored", RunStats(12, 0.9)))
    render.assert_not_called()
    assert (out.content, out.match) == (b"%PDF-tailored", Match("tailored", 58, 77))


def test_tailoring_errors_propagate():
    with pytest.raises(TailoringError) as exc:
        generate(application(), error=TailoringError("claude", "claude_auth"))
    assert exc.value.reason == "claude_auth"


def test_oversized_posting_fails_before_any_run():
    with pytest.raises(TailoringError) as exc:
        generate(application("word " * 13_000))
    assert exc.value.reason == "posting_too_long"
