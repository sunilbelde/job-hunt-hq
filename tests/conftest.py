from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.generation import GeneratedFile
from app.main import create_app
from app.settings import Settings
from app.storage import StorageError

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


@pytest.fixture
def client(settings, storage):
    return TestClient(create_app(settings, storage))


FAKE_PDF = b"%PDF-1.5 fake resume"


@pytest.fixture(autouse=True)
def fake_generate(monkeypatch):
    """Keep API tests independent of tectonic; rendering has its own tests."""
    monkeypatch.setattr(
        "app.main.generate_output",
        lambda application: GeneratedFile(FAKE_PDF, "application/pdf", "pdf"),
    )
