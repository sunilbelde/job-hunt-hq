import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rendering import RenderError
from tests.conftest import API_KEY, VALID_JOB, FakeStorage

HEADERS = {"X-API-Key": API_KEY}


@pytest.mark.parametrize("path", ["/healthz", "/health"])
def test_health_open_and_no_storage_call(client, storage, path):
    r = client.get(path)
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert storage.uploads == [] and storage.signed == []


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_auth_rejected(client, storage, headers):
    r = client.post("/jobs", json=VALID_JOB, headers=headers)
    assert r.status_code == 401
    assert storage.uploads == []


def test_auth_checked_before_body(client, storage):
    r = client.post("/jobs", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 401
    assert storage.uploads == []


def test_invalid_json(client, storage):
    r = client.post(
        "/jobs", content=b"{not json", headers={**HEADERS, "Content-Type": "application/json"}
    )
    assert 400 <= r.status_code < 500
    assert storage.uploads == []


@pytest.mark.parametrize("body", ["[1, 2]", '"text"', "42", "null"])
def test_non_object_body(client, storage, body):
    r = client.post("/jobs", content=body, headers={**HEADERS, "Content-Type": "application/json"})
    assert 400 <= r.status_code < 500
    assert storage.uploads == []


def test_success_shape(client, storage):
    r = client.post("/jobs", json=VALID_JOB, headers=HEADERS)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"job_id", "url", "expires_at", "key"}
    assert body["key"].startswith("outputs/") and body["key"].endswith(".pdf")
    assert body["url"].startswith("https://signed.example/")
    assert body["expires_at"].endswith("Z")
    content, content_type, ext = storage.uploads[0]
    assert (content_type, ext) == ("application/pdf", "pdf")
    assert content.startswith(b"%PDF")
    assert storage.signed == [(body["key"], 3600)]


def test_minimal_posting_accepted(client):
    assert client.post("/jobs", json=VALID_JOB, headers=HEADERS).status_code == 201


@pytest.mark.parametrize("body", [
    {},
    {"company": "Acme", "role": "Engineer"},
    {**VALID_JOB, "company": ""},
    {**VALID_JOB, "salary": 100},
    {**VALID_JOB, "company": None},
])
def test_invalid_posting_422_and_nothing_stored(client, storage, body):
    r = client.post("/jobs", json=body, headers=HEADERS)
    assert r.status_code == 422
    assert storage.uploads == []


def test_422_does_not_echo_values(client):
    r = client.post("/jobs", json={**VALID_JOB, "salary": 12345, "role": ""}, headers=HEADERS)
    assert r.status_code == 422
    assert "12345" not in r.text and "Build things" not in r.text


def test_free_form_optional_values_accepted(client):
    body = {**VALID_JOB, "salary": "$1", "date_posted": "yesterday", "job_link": "not a url"}
    assert client.post("/jobs", json=body, headers=HEADERS).status_code == 201


def test_storage_failure_returns_generic_502(settings):
    client = TestClient(create_app(settings, FakeStorage(fail=True)))
    r = client.post("/jobs", json=VALID_JOB, headers=HEADERS)
    assert r.status_code == 502
    assert "secret-host" not in r.text and "EndpointConnectionError" not in r.text


def test_one_log_line_per_request_without_secrets(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    client.post("/jobs", json={**VALID_JOB, "why_it_fits": "payload-value"}, headers=HEADERS)
    client.post("/jobs", json=VALID_JOB, headers={"X-API-Key": "wrong-key-value"})
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "app.requests"]
    assert [l["status"] for l in lines] == [201, 401]
    assert all({"job_id", "status", "duration_ms"} <= set(l) for l in lines)
    text = caplog.text
    assert "payload-value" not in text and "wrong-key-value" not in text and API_KEY not in text


def test_storage_failure_logged_server_side(settings, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    client = TestClient(create_app(settings, FakeStorage(fail=True)))
    client.post("/jobs", json=VALID_JOB, headers=HEADERS)
    assert "secret-host.example" in caplog.text
    request_lines = [r for r in caplog.records if '"job_request"' in r.getMessage()]
    assert len(request_lines) == 1 and '"status": 502' in request_lines[0].getMessage()


def _failing_render(job, *, job_id=None):
    raise RenderError("tectonic exited with 1: /srv/data/BASE.tex:2 ! LaTeX Error")


def test_render_failure_returns_generic_500(settings, storage, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    monkeypatch.setattr("app.main.generate_output", _failing_render)
    client = TestClient(create_app(settings, storage))
    r = client.post("/jobs", json=VALID_JOB, headers=HEADERS)
    assert r.status_code == 500
    assert r.json() == {"detail": "Resume generation failed"}
    assert "LaTeX" not in r.text and "/srv" not in r.text and "tectonic" not in r.text
    assert storage.uploads == []
    assert "LaTeX Error" in caplog.text  # details are logged server-side
    lines = [json.loads(r.getMessage()) for r in caplog.records if '"job_request"' in r.getMessage()]
    assert len(lines) == 1 and lines[0]["status"] == 500 and lines[0]["job_id"]
    errors = [json.loads(r.getMessage()) for r in caplog.records if '"render_error"' in r.getMessage()]
    assert errors[0]["job_id"] == lines[0]["job_id"]


def test_health_responds_during_slow_render(settings, storage, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(job, *, job_id=None):
        started.set()
        release.wait(timeout=10)
        from app.generation import GeneratedFile
        return GeneratedFile(b"%PDF-slow", "application/pdf", "pdf")

    monkeypatch.setattr("app.main.generate_output", slow)
    client = TestClient(create_app(settings, storage))
    result = {}
    worker = threading.Thread(
        target=lambda: result.update(r=client.post("/jobs", json=VALID_JOB, headers=HEADERS))
    )
    worker.start()
    try:
        assert started.wait(timeout=5)
        assert client.get("/health").status_code == 200  # not blocked by the in-flight render
        assert "r" not in result  # the render is still running
    finally:
        release.set()
        worker.join(timeout=10)
    assert result["r"].status_code == 201
