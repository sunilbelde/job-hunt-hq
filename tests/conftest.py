import pytest
from fastapi.testclient import TestClient

from app.generation import GeneratedFile
from app.main import create_app
from app.settings import Settings
from app.storage import StorageError

API_KEY = "test-api-key"
VALID_JOB = {"company": "Acme", "role": "Engineer", "full_job_description": "Build things"}


class FakeStorage:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.uploads: list[tuple[bytes, str, str]] = []
        self.signed: list[tuple[str, int]] = []

    def upload(self, content, content_type, extension):
        if self.fail:
            raise StorageError("upload failed: EndpointConnectionError: secret-host.example")
        self.uploads.append((content, content_type, extension))
        return f"outputs/2026-01-01/fake.{extension}"

    def presigned_url(self, key, ttl_seconds):
        self.signed.append((key, ttl_seconds))
        return f"https://signed.example/{key}?ttl={ttl_seconds}"


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        api_key=API_KEY,
        r2_account_id="acct",
        r2_access_key_id="akid",
        r2_secret_access_key="secret",
        r2_bucket="bucket",
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
