import json
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.rendering import RenderError
from tests.conftest import API_KEY, BASE_URL, VALID_JOB, FakeStorage

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
    assert body["url"].startswith(f"{BASE_URL}/files/")
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
    assert "/secret/out" not in r.text and "No space left" not in r.text and "OSError" not in r.text


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
    assert "No space left on device" in caplog.text
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


# --- Signed downloads (real LocalStorage on tmp_path) ---

from urllib.parse import parse_qs, urlsplit  # noqa: E402

from app.log_filters import RedactQueryString  # noqa: E402
from app.storage import LinkSigner, LocalStorage  # noqa: E402
from tests.conftest import FAKE_PDF, SIGNING_SECRET  # noqa: E402


@pytest.fixture
def local_storage(settings):
    return LocalStorage(settings.output_dir, LinkSigner(SIGNING_SECRET, BASE_URL))


@pytest.fixture
def local_client(settings, local_storage):
    return TestClient(create_app(settings, local_storage))


def _create(local_client):
    r = local_client.post("/jobs", json=VALID_JOB, headers=HEADERS)
    assert r.status_code == 201
    body = r.json()
    parts = urlsplit(body["url"])
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    return body, parts.path, query


def test_download_round_trip(local_client):
    body, path, query = _create(local_client)
    r = local_client.get(path, params=query)
    assert r.status_code == 200
    assert r.content == FAKE_PDF
    assert r.headers["content-type"] == "application/pdf"
    assert path == f"/files/{body['key']}"


def test_download_without_api_key_header_needed(local_client):
    _, path, query = _create(local_client)
    assert local_client.get(path, params=query, headers={}).status_code == 200


def test_download_missing_signature_403(local_client):
    _, path, _ = _create(local_client)
    assert local_client.get(path).status_code == 403


def test_download_tampered_signature_403(local_client):
    _, path, query = _create(local_client)
    query["sig"] = "0" * 64
    r = local_client.get(path, params=query)
    assert r.status_code == 403 and FAKE_PDF not in r.content


def test_download_expired_403(local_client, monkeypatch):
    _, path, query = _create(local_client)
    monkeypatch.setattr("app.storage.time.time", lambda: int(query["expires"]) + 1)
    assert local_client.get(path, params=query).status_code == 403


def test_download_traversal_403_without_filesystem_access(local_client, local_storage, monkeypatch):
    calls = []
    monkeypatch.setattr(local_storage, "path_for", lambda key: calls.append(key))
    for path in ["/files/../../etc/passwd", "/files/outputs/..%2F..%2Fetc%2Fpasswd", "/files/outputs/x.pdf"]:
        r = local_client.get(path, params={"expires": "9999999999", "sig": "0" * 64})
        assert r.status_code in (403, 404)
        assert r.status_code == 403 or not path.startswith("/files/outputs")
    assert calls == []


def test_download_deleted_file_404(local_client, settings):
    body, path, query = _create(local_client)
    (settings.output_dir / body["key"]).unlink()
    assert local_client.get(path, params=query).status_code == 404


def test_download_not_logged_as_job_request(local_client, caplog):
    _, path, query = _create(local_client)
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    local_client.get(path, params=query)
    service_logs = " ".join(
        r.getMessage() for r in caplog.records if r.name.startswith(("app", "uvicorn"))
    )
    assert '"job_request"' not in service_logs
    assert query["sig"] not in service_logs


def test_access_log_query_string_redacted():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("100.64.0.1:5000", "GET", "/files/outputs/d/k.pdf?expires=1&sig=abc", "1.1", 200), None,
    )
    assert RedactQueryString().filter(record)
    assert "sig=" not in record.getMessage() and "/files/outputs/d/k.pdf" in record.getMessage()


# --- Retention cleanup on startup ---

def test_startup_cleanup_removes_expired_files(settings, local_storage):
    import os
    old = settings.output_dir / local_storage.upload(b"old", "application/pdf", "pdf")
    recent = settings.output_dir / local_storage.upload(b"new", "application/pdf", "pdf")
    t = time.time() - 31 * 86400
    os.utime(old, (t, t))
    with TestClient(create_app(settings, local_storage)) as client:
        assert client.get("/health").status_code == 200
    assert not old.exists() and recent.exists()


def test_startup_cleanup_failure_does_not_stop_service(settings, storage, monkeypatch, caplog):
    monkeypatch.setattr(storage, "cleanup", lambda max_age: (_ for _ in ()).throw(OSError("disk gone")))
    with TestClient(create_app(settings, storage)) as client:
        assert client.get("/healthz").status_code == 200
    assert "cleanup_error" in caplog.text


# --- POST /application (real ApplicationStore in tmp_path) ---

import sqlite3  # noqa: E402

from app.applications import ApplicationStoreError  # noqa: E402
from tests.conftest import GH_LINK, VALID_APPLICATION  # noqa: E402


def post_application(client, body, headers=HEADERS):
    return client.post("/application", json=body, headers=headers)


def link_variant(link):
    return {**VALID_APPLICATION, "job_link": link, "official_apply_url": link}


def stored_rows(settings):
    with sqlite3.connect(settings.output_dir / "applications.sqlite3") as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM applications ORDER BY id")]


def assert_error(r, status):
    assert r.status_code == status
    body = r.json()
    assert set(body) == {"ok", "message"} and body["ok"] is False and body["message"]
    return body["message"]


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_application_auth_rejected(client, settings, headers):
    assert_error(post_application(client, VALID_APPLICATION, headers), 401)
    assert stored_rows(settings) == []


def test_application_auth_checked_before_body(client):
    r = client.post("/application", content=b"{not json", headers={"Content-Type": "application/json"})
    assert_error(r, 401)


def test_application_invalid_json(client, settings):
    r = client.post("/application", content=b"{not json", headers={**HEADERS, "Content-Type": "application/json"})
    assert_error(r, 422)
    assert stored_rows(settings) == []


@pytest.mark.parametrize("body", ["[1, 2]", '"text"', "42", "null"])
def test_application_non_object_body(client, settings, body):
    r = client.post("/application", content=body, headers={**HEADERS, "Content-Type": "application/json"})
    assert_error(r, 422)
    assert stored_rows(settings) == []


@pytest.mark.parametrize("change,field", [
    ({"job_link": ""}, "job_link"),
    ({"job_link": None}, "job_link"),
    ({"company": None}, "company"),
    ({"salary": 100}, "salary"),
    ({"posting_source_type": "linkedin"}, "posting_source_type"),
    ({"verification_method": "Official_Apply_Match"}, "verification_method"),
    ({"verification_method": "employer_site"}, "verification_method"),
    ({"official_apply_url": GH_LINK + "/"}, "official_apply_url"),
    ({"official_apply_url": ""}, "official_apply_url"),
    ({"posting_source_type": "employer_site", "verification_method": "employer_site"}, "official_apply_url"),
])
def test_application_field_rules_422(client, settings, change, field):
    message = assert_error(post_application(client, {**VALID_APPLICATION, **change}), 422)
    assert field in message
    assert stored_rows(settings) == []


def test_application_missing_job_link_422(client):
    body = {k: v for k, v in VALID_APPLICATION.items() if k != "job_link"}
    assert "job_link" in assert_error(post_application(client, body), 422)


def test_application_message_never_echoes_values(client):
    r = post_application(client, {**VALID_APPLICATION, "posting_source_type": "secret-ish-value", "salary": 98765})
    message = assert_error(r, 422)
    assert "posting_source_type" in message
    assert "secret-ish-value" not in r.text and "98765" not in r.text


def test_application_created_then_duplicate(client, settings):
    first = post_application(client, VALID_APPLICATION)
    assert first.status_code == 201
    body = first.json()
    assert set(body) == {"ok", "application_id"} and body["ok"] is True
    assert isinstance(body["application_id"], int) and body["application_id"] > 0
    second = post_application(client, {**VALID_APPLICATION, "salary": "$1"})
    assert second.status_code == 200 and second.json() == body
    rows = stored_rows(settings)
    assert len(rows) == 1 and rows[0]["salary"] == VALID_APPLICATION["salary"]


def test_application_employer_site_accepted(client, settings):
    body = {**VALID_APPLICATION, "job_link": "https://www.acme.com/careers/1",
            "posting_source_type": "employer_site", "verification_method": "employer_site",
            "official_apply_url": ""}
    assert post_application(client, body).status_code == 201
    assert stored_rows(settings)[0]["official_apply_url"] == ""


def test_application_required_only_accepted(client):
    body = {k: VALID_APPLICATION[k] for k in (
        "company", "role", "job_link", "posting_source_type", "verification_method", "official_apply_url")}
    assert post_application(client, {**body, "found": True}).status_code == 201


def test_application_decorated_links_share_id(client, settings):
    base = "https://job-boards.greenhouse.io/acme/jobs/123"
    links = [base, base + "/", base + "?gh_src=x&utm_source=y", "HTTPS://Job-Boards.Greenhouse.io/acme/jobs/123#apply"]
    ids = {post_application(client, link_variant(link)).json()["application_id"] for link in links}
    assert len(ids) == 1
    rows = stored_rows(settings)
    assert len(rows) == 1 and rows[0]["job_link"] == base


def test_application_job_id_in_query_distinct(client):
    a = post_application(client, link_variant("https://www.acme.com/careers?gh_jid=111"))
    b = post_application(client, link_variant("https://www.acme.com/careers?gh_jid=222"))
    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["application_id"] != b.json()["application_id"]


class FailingApplications:
    def record(self, fields):
        raise ApplicationStoreError("OperationalError: disk I/O error: /secret/out/applications.sqlite3")


def test_application_store_failure_503(settings, storage, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    client = TestClient(create_app(settings, storage, FailingApplications()))
    r = post_application(client, VALID_APPLICATION)
    message = assert_error(r, 503)
    assert "/secret" not in r.text and "OperationalError" not in r.text and "disk" not in message
    assert "application_store_error" in caplog.text and "disk I/O error" in caplog.text


def test_application_store_created_at_startup(settings, storage):
    create_app(settings, storage)
    assert (settings.output_dir / "applications.sqlite3").is_file()


# --- POST /application logging ---

def application_log_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records
            if r.name == "app.requests" and '"application_request"' in r.getMessage()]


def test_application_one_log_line_per_request(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    post_application(client, {**VALID_APPLICATION, "why_it_fits": "payload-value"})
    post_application(client, VALID_APPLICATION)
    post_application(client, VALID_APPLICATION, {"X-API-Key": "wrong-key-value"})
    post_application(client, {**VALID_APPLICATION, "company": ""})
    lines = application_log_lines(caplog)
    assert [l["status"] for l in lines] == [201, 200, 401, 422]
    assert all({"status", "duration_ms"} <= set(l) and "job_id" not in l for l in lines)
    assert lines[0]["duplicate"] is False and lines[1]["duplicate"] is True
    assert lines[0]["application_id"] == lines[1]["application_id"]
    assert "application_id" not in lines[2] and "application_id" not in lines[3]
    assert '"job_request"' not in caplog.text
    text = caplog.text
    assert "payload-value" not in text and "wrong-key-value" not in text and API_KEY not in text
    assert GH_LINK not in text and "Acme Corp" not in text


# --- PATCH / DELETE /application/{application_id} ---

def patch_application(client, application_id, body, headers=HEADERS):
    return client.patch(f"/application/{application_id}", json=body, headers=headers)


def delete_application(client, application_id, headers=HEADERS):
    return client.delete(f"/application/{application_id}", headers=headers)


def recorded(client, body=VALID_APPLICATION):
    return post_application(client, body).json()["application_id"]


def stored_row(settings, application_id):
    return next(r for r in stored_rows(settings) if r["id"] == application_id)


class FailingStore(FailingApplications):
    def update(self, application_id, changes):
        self.record(changes)

    def delete(self, application_id):
        self.record({})

    def exists(self, application_id):
        self.record({})


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_patch_auth_rejected(client, settings, headers):
    application_id = recorded(client)
    assert_error(patch_application(client, application_id, {"status": "applied"}, headers), 401)
    assert stored_row(settings, application_id)["status"] == "verified"


def test_patch_auth_checked_before_id_and_body(client):
    assert_error(patch_application(client, 999999, {"status": "applied"}, {}), 401)
    r = client.patch("/application/1", content=b"{not json", headers={"Content-Type": "application/json"})
    assert_error(r, 401)


@pytest.mark.parametrize("application_id", ["999999", "abc", "0", "-1", "1.0", "99999999999999999999"])
def test_patch_unknown_id_404(client, settings, application_id):
    message = assert_error(patch_application(client, application_id, {"status": "applied"}), 404)
    assert message == "Application not found"
    assert stored_rows(settings) == []


def test_patch_unknown_id_with_bad_body_404(client):
    r = client.patch("/application/999999", content=b"{not json",
                     headers={**HEADERS, "Content-Type": "application/json"})
    assert_error(r, 404)


@pytest.mark.parametrize("content", [b"{not json", b"[1, 2]", b'"text"', b"42", b"null"])
def test_patch_bad_body_422(client, settings, content):
    application_id = recorded(client)
    before = stored_row(settings, application_id)
    r = client.patch(f"/application/{application_id}", content=content,
                     headers={**HEADERS, "Content-Type": "application/json"})
    assert_error(r, 422)
    assert stored_row(settings, application_id) == before


@pytest.mark.parametrize("body,field", [
    ({"status": "ghosted"}, "status"),
    ({"status": "Applied"}, "status"),
    ({"status": None}, "status"),
    ({"company": ""}, "company"),
    ({"role": None}, "role"),
    ({"salary": 5}, "salary"),
    ({"job_link": "https://example.com/jobs/2", "status": "applied"}, "job_link"),
    ({"verification_method": "official_apply_match"}, "verification_method"),
    ({}, "no updatable fields"),
    ({"found": True}, "no updatable fields"),
])
def test_patch_field_rules_422(client, settings, body, field):
    application_id = recorded(client)
    before = stored_row(settings, application_id)
    assert field in assert_error(patch_application(client, application_id, body), 422)
    assert stored_row(settings, application_id) == before


def test_patch_does_not_echo_values(client):
    application_id = recorded(client)
    r = patch_application(client, application_id, {"status": "secret-ish-value", "job_link": "secret-link"})
    assert "secret-ish-value" not in r.text and "secret-link" not in r.text


def test_patch_status_only(client, settings):
    application_id = recorded(client)
    before = stored_row(settings, application_id)
    r = patch_application(client, application_id, {"status": "applied", "found": True})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "application_id": application_id, "status": "applied"}
    after = stored_row(settings, application_id)
    assert after["status"] == "applied" and after["updated_at"]
    assert {k: v for k, v in after.items() if k not in ("status", "updated_at")} == {
        k: v for k, v in before.items() if k not in ("status", "updated_at")}


def test_patch_fields_keep_status_and_null_clears(client, settings):
    application_id = recorded(client)
    patch_application(client, application_id, {"status": "applied"})
    r = patch_application(client, application_id, {"salary": "$150k", "sponsorship": None})
    assert r.json() == {"ok": True, "application_id": application_id, "status": "applied"}
    row = stored_row(settings, application_id)
    assert row["salary"] == "$150k" and row["sponsorship"] is None


def test_patch_same_status_again(client):
    application_id = recorded(client)
    assert patch_application(client, application_id, {"status": "verified"}).status_code == 200


def test_duplicate_post_keeps_updated_status(client, settings):
    application_id = recorded(client)
    patch_application(client, application_id, {"status": "interviewing"})
    r = post_application(client, VALID_APPLICATION)
    assert r.status_code == 200 and r.json() == {"ok": True, "application_id": application_id}
    assert stored_row(settings, application_id)["status"] == "interviewing"


@pytest.mark.parametrize("call", [
    lambda c: patch_application(c, 1, {"status": "applied"}),
    lambda c: patch_application(c, 1, {"status": "ghosted"}),
    lambda c: delete_application(c, 1),
])
def test_patch_and_delete_store_failure_503(settings, storage, caplog, call):
    caplog.set_level(logging.INFO, logger="app.requests")
    client = TestClient(create_app(settings, storage, FailingStore()))
    r = call(client)
    message = assert_error(r, 503)
    assert "/secret" not in r.text and "OperationalError" not in r.text and "disk" not in message
    assert "application_store_error" in caplog.text


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_delete_auth_rejected(client, settings, headers):
    application_id = recorded(client)
    assert_error(delete_application(client, application_id, headers), 401)
    assert_error(delete_application(client, 999999, headers), 401)
    assert len(stored_rows(settings)) == 1


def test_delete_then_gone(client, settings):
    application_id = recorded(client)
    r = delete_application(client, application_id)
    assert r.status_code == 200 and r.json() == {"ok": True, "application_id": application_id}
    assert stored_rows(settings) == []
    assert_error(delete_application(client, application_id), 404)
    assert_error(patch_application(client, application_id, {"status": "applied"}), 404)


def test_re_record_after_delete(client, settings):
    application_id = recorded(client)
    delete_application(client, application_id)
    r = post_application(client, VALID_APPLICATION)
    assert r.status_code == 201 and r.json()["application_id"] > application_id
    assert stored_row(settings, r.json()["application_id"])["status"] == "verified"


def test_delete_ignores_body(client, settings):
    application_id = recorded(client)
    r = client.request("DELETE", f"/application/{application_id}", content=b"{not json",
                       headers={**HEADERS, "Content-Type": "application/json"})
    assert r.status_code == 200 and stored_rows(settings) == []


@pytest.mark.parametrize("application_id", ["abc", "0", "-1"])
def test_delete_unparseable_id_404(client, application_id):
    assert assert_error(delete_application(client, application_id), 404) == "Application not found"


def test_patch_and_delete_logging(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    application_id = recorded(client)
    caplog.clear()
    patch_application(client, application_id, {"status": "applied", "salary": "payload-value"})
    patch_application(client, application_id, {"status": "applied"}, {"X-API-Key": "wrong-key-value"})
    patch_application(client, 999999, {"status": "applied"})
    patch_application(client, application_id, {"status": "ghosted"})
    delete_application(client, application_id)
    delete_application(client, application_id)
    lines = application_log_lines(caplog)
    assert [(l["method"], l["status"]) for l in lines] == [
        ("PATCH", 200), ("PATCH", 401), ("PATCH", 404), ("PATCH", 422), ("DELETE", 200), ("DELETE", 404)]
    assert [l.get("application_id") for l in lines] == [
        application_id, None, 999999, application_id, application_id, application_id]
    assert all("duplicate" not in l and "duration_ms" in l for l in lines)
    assert '"job_request"' not in caplog.text
    text = caplog.text
    for value in ("applied", "ghosted", "payload-value", "wrong-key-value", API_KEY):
        assert value not in text


def test_post_log_line_carries_method(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    post_application(client, VALID_APPLICATION)
    (line,) = application_log_lines(caplog)
    assert line["method"] == "POST" and line["status"] == 201 and line["duplicate"] is False
