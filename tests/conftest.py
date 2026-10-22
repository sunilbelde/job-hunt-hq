import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cover_letter import LetterResult
from app.generation import GeneratedFile
from app.main import create_app
from app.settings import Settings
from app.storage import StorageError
from app.tailoring import Match, RunStats

# The tailor-resume skill's scripts are standalone modules, not a package; tests import them by name.
SKILL_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "tailor-resume"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

API_KEY = "test-api-key"
# The client's example POST /application body.
GH_LINK = "https://job-boards.greenhouse.io/acme/jobs/1234567"
VALID_APPLICATION = {
    "company": "Acme Corp",
    "role": "Senior Software Engineer, Applied AI",
    "location": "San Francisco, CA (Hybrid)",
    "work_type": "Hybrid",
    "salary": "$220,000 - $300,000",
    "date_posted": "2026-10-15",
    "sponsorship": "No explicit mention of sponsorship",
    "why_it_fits": "GenAI role building agent pipelines",
    "job_link": GH_LINK,
    "company_careers_url": "https://www.acme.com/careers/open-roles",
    "official_employer_domain": "acme.com",
    "posting_source_type": "recruiting_platform",
    "verification_method": "official_apply_match",
    "official_apply_url": GH_LINK,
    "full_job_description": "Full text of the posting...",
}


class FakeStorage:
    """Records what would be saved; writes nothing."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.saved: list[tuple[str, int, bytes]] = []
        self.letters: list[tuple[str, int, bytes]] = []

    def save_resume(self, company, application_id, content):
        if self.fail:
            raise StorageError("write failed: OSError: [Errno 28] No space left on device: /secret/out/Acme")
        self.saved.append((company, application_id, content))
        return Path("/fake/out") / company / str(application_id) / "SUNIL BELDE.pdf"

    def save_cover_letter(self, company, application_id, content):
        if self.fail:
            raise StorageError("write failed: OSError: [Errno 28] No space left on device: /secret/out/Acme")
        self.letters.append((company, application_id, content))
        return Path("/fake/out") / company / str(application_id) / "SUNIL BELDE - Cover Letter.pdf"


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, api_key=API_KEY, output_dir=tmp_path / "out")


@pytest.fixture
def storage():
    return FakeStorage()


# Every API test runs with docs off and on: serving docs must not change API behavior.
@pytest.fixture(params=[False, True], ids=["docs-off", "docs-on"])
def client(request, settings, storage):
    return TestClient(create_app(settings.model_copy(update={"api_docs_enabled": request.param}), storage))


@pytest.fixture
def docs_client(settings, storage):
    return TestClient(create_app(settings.model_copy(update={"api_docs_enabled": True}), storage))


FAKE_PDF = b"%PDF-1.5 fake resume"


def fake_output(content: bytes = FAKE_PDF, match: Match = Match("no_job_description"), run: RunStats | None = None):
    return GeneratedFile(content, "application/pdf", "pdf", match=match, run=run)


@pytest.fixture(autouse=True)
def fake_generate(monkeypatch):
    """Keep API tests independent of tectonic and Claude; generation and tailoring have their own tests."""
    monkeypatch.setattr("app.main.generate_output", lambda application, settings: fake_output())


FAKE_LETTER_PDF = b"%PDF-1.5 fake cover letter"
FAKE_LETTER_TEXT = "Dear Acme Corp Hiring Team,\n\nA paragraph.\n\nSincerely,\nSunil Belde\n"
# A posting long enough for a cover letter (50 words or more).
LONG_POSTING = " ".join(["We build retrieval systems for enterprise customers in Python."] * 8)


def fake_letter(text: str = FAKE_LETTER_TEXT, pdf: bytes = FAKE_LETTER_PDF, run: RunStats | None = None) -> LetterResult:
    return LetterResult(pdf, text, run or RunStats(turns=7, cost_usd=0.41234, models=("claude-opus-5-5",)))


@pytest.fixture(autouse=True)
def fake_write_letter(monkeypatch):
    """Keep API tests independent of tectonic and Claude; app/cover_letter.py has its own tests."""
    monkeypatch.setattr("app.main.write_cover_letter", lambda application, settings: fake_letter())
