import pytest
from fastapi.testclient import TestClient

from app.generation import GeneratedFile
from app.main import create_app
from app.settings import Settings
from app.storage import StorageError

API_KEY = "test-api-key"
SIGNING_SECRET = "x" * 32
BASE_URL = "https://mac-mini.tail1234.ts.net"
VALID_JOB = {"company": "Acme", "role": "Engineer", "full_job_description": "Build things"}
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
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.uploads: list[tuple[bytes, str, str]] = []
        self.signed: list[tuple[str, int]] = []

    def upload(self, content, content_type, extension):
        if self.fail:
            raise StorageError("write failed: OSError: [Errno 28] No space left on device: /secret/out/outputs")
        self.uploads.append((content, content_type, extension))
        return f"outputs/2026-01-01/fake.{extension}"

    def presigned_url(self, key, ttl_seconds):
        self.signed.append((key, ttl_seconds))
        return f"{BASE_URL}/files/{key}?ttl={ttl_seconds}"

    def verify_link(self, key, expires, sig):
        return False

    def path_for(self, key):
        raise ValueError("invalid key")

    def cleanup(self, max_age_seconds):
        return 0


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        api_key=API_KEY,
        link_signing_secret=SIGNING_SECRET,
        public_base_url=BASE_URL,
        output_dir=tmp_path / "out",
        signed_url_ttl_seconds=3600,
    )


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
        lambda job, *, job_id=None: GeneratedFile(FAKE_PDF, "application/pdf", "pdf"),
    )
