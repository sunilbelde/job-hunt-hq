import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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

    def save_resume(self, company, application_id, content):
        if self.fail:
            raise StorageError("write failed: OSError: [Errno 28] No space left on device: /secret/out/Acme")
        self.saved.append((company, application_id, content))
        return Path("/fake/out") / company / str(application_id) / "SUNIL BELDE.pdf"


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
