import json
import logging
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.log_filters import RedactQueryString
from app.main import create_app
from app.rendering import RenderError
from app.storage import COVER_LETTER_FILE_NAME, RESUME_FILE_NAME, LocalStorage
from app.tailoring import Match, RunStats, TailoringError
from tests.conftest import API_KEY, FAKE_PDF, FakeStorage, fake_output

HEADERS = {"X-API-Key": API_KEY}
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
UNKNOWN = str(uuid.uuid4())  # well formed, but names no row


@pytest.mark.parametrize("path", ["/healthz", "/health"])
def test_health_open_and_no_storage_call(client, storage, path):
    r = client.get(path)
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert storage.saved == []


def test_access_log_query_string_redacted():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("100.64.0.1:5000", "GET", "/application/1?token=abc", "1.1", 200), None,
    )
    assert RedactQueryString().filter(record)
    assert "token=" not in record.getMessage() and "/application/1" in record.getMessage()


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
    assert isinstance(body["application_id"], str) and UUID4.match(body["application_id"])
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
    def legacy_ids(self):
        return {}

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
    assert '"resume_request"' not in caplog.text
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
    assert_error(patch_application(client, UNKNOWN, {"status": "applied"}, {}), 401)
    r = client.patch("/application/1", content=b"{not json", headers={"Content-Type": "application/json"})
    assert_error(r, 401)


@pytest.mark.parametrize("application_id", [
    UNKNOWN, "999999", "1", "abc", "0", "-1", "1.0", "99999999999999999999",
    UNKNOWN.replace("-", ""), "{" + UNKNOWN + "}", "urn:uuid:" + UNKNOWN, UNKNOWN + "0",
])
def test_patch_unknown_id_404(client, settings, application_id):
    message = assert_error(patch_application(client, application_id, {"status": "applied"}), 404)
    assert message == "Application not found"
    assert stored_rows(settings) == []


def test_patch_unknown_id_with_bad_body_404(client):
    r = client.patch(f"/application/{UNKNOWN}", content=b"{not json",
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
    lambda c: patch_application(c, UNKNOWN, {"status": "applied"}),
    lambda c: patch_application(c, UNKNOWN, {"status": "ghosted"}),
    lambda c: delete_application(c, UNKNOWN),
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
    assert_error(delete_application(client, UNKNOWN, headers), 401)
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
    assert r.status_code == 201 and r.json()["application_id"] != application_id
    assert stored_row(settings, r.json()["application_id"])["status"] == "verified"


def test_delete_ignores_body(client, settings):
    application_id = recorded(client)
    r = client.request("DELETE", f"/application/{application_id}", content=b"{not json",
                       headers={**HEADERS, "Content-Type": "application/json"})
    assert r.status_code == 200 and stored_rows(settings) == []


@pytest.mark.parametrize("application_id", ["abc", "1", "0", "-1"])
def test_delete_unparseable_id_404(client, settings, application_id):
    recorded(client)
    assert assert_error(delete_application(client, application_id), 404) == "Application not found"
    assert len(stored_rows(settings)) == 1


def test_upper_case_path_id_accepted(client, settings):
    application_id = recorded(client)
    r = patch_application(client, application_id.upper(), {"status": "applied"})
    assert r.status_code == 200 and r.json()["application_id"] == application_id
    r = delete_application(client, application_id.upper())
    assert r.json() == {"ok": True, "application_id": application_id}
    assert stored_rows(settings) == []


def test_malformed_path_id_not_logged(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    delete_application(client, "not-a-uuid")
    (line,) = application_log_lines(caplog)
    assert line["method"] == "DELETE" and line["status"] == 404 and "application_id" not in line
    assert "not-a-uuid" not in caplog.text


def test_patch_and_delete_logging(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    application_id = recorded(client)
    caplog.clear()
    patch_application(client, application_id, {"status": "applied", "salary": "payload-value"})
    patch_application(client, application_id, {"status": "applied"}, {"X-API-Key": "wrong-key-value"})
    patch_application(client, UNKNOWN, {"status": "applied"})
    patch_application(client, application_id, {"status": "ghosted"})
    delete_application(client, application_id)
    delete_application(client, application_id)
    lines = application_log_lines(caplog)
    assert [(l["method"], l["status"]) for l in lines] == [
        ("PATCH", 200), ("PATCH", 401), ("PATCH", 404), ("PATCH", 422), ("DELETE", 200), ("DELETE", 404)]
    assert [l.get("application_id") for l in lines] == [
        application_id, None, UNKNOWN, application_id, application_id, application_id]
    assert all("duplicate" not in l and "duration_ms" in l for l in lines)
    assert '"resume_request"' not in caplog.text
    text = caplog.text
    for value in ("applied", "ghosted", "payload-value", "wrong-key-value", API_KEY):
        assert value not in text


def test_post_log_line_carries_method(client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    post_application(client, VALID_APPLICATION)
    (line,) = application_log_lines(caplog)
    assert line["method"] == "POST" and line["status"] == 201 and line["duplicate"] is False


# --- POST /resume ---

def post_resume(client, body, headers=HEADERS):
    return client.post("/resume", json=body, headers=headers)


def resume_log_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records
            if r.name == "app.requests" and '"resume_request"' in r.getMessage()]


def new_application(client, n=1, **overrides):
    """Record a distinct application (its own job_link) and return its ID."""
    body = {**link_variant(f"{GH_LINK}{n}"), **overrides}
    return recorded(client, body)


@pytest.fixture
def local_client(settings):
    return TestClient(create_app(settings, LocalStorage(settings.output_dir)))


def output_files(settings):
    return sorted(p for p in settings.output_dir.rglob("*") if p.is_file() and p.suffix == ".pdf")


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_resume_auth_rejected(client, storage, headers):
    application_id = new_application(client)
    assert_error(post_resume(client, {"application_id": application_id}, headers), 401)
    assert_error(post_resume(client, {"application_id": UNKNOWN}, headers), 401)  # unknown ID not leaked
    r = client.post("/resume", content=b"{not json", headers={**headers, "Content-Type": "application/json"})
    assert_error(r, 401)
    assert storage.saved == []


@pytest.mark.parametrize("content", [b"{not json", b"[1, 2]", b'"text"', b"42", b"null"])
def test_resume_bad_body_422(client, storage, content):
    r = client.post("/resume", content=content, headers={**HEADERS, "Content-Type": "application/json"})
    assert_error(r, 422)
    assert storage.saved == []


@pytest.mark.parametrize("body", [{}, {"application_id": 7}, {"application_id": 7.5}, {"application_id": True},
                                  {"application_id": None}, {"application_id": {"id": UNKNOWN}}])
def test_resume_non_string_id_422(client, storage, body):
    message = assert_error(post_resume(client, body), 422)
    assert "application_id" in message
    assert storage.saved == []


def test_resume_422_does_not_echo_value(client):
    r = post_resume(client, {"application_id": ["secret-ish-value"]})
    assert_error(r, 422)
    assert "secret-ish-value" not in r.text


@pytest.mark.parametrize("application_id", [UNKNOWN, "7", "0", "", "not-a-uuid", UNKNOWN.replace("-", "")])
def test_resume_unknown_id_404(local_client, settings, application_id):
    new_application(local_client)
    r = post_resume(local_client, {"application_id": application_id})
    assert assert_error(r, 404) == "Application not found"
    assert output_files(settings) == []
    assert not [p for p in settings.output_dir.iterdir() if p.is_dir()]


def test_resume_deleted_application_404(client, storage):
    application_id = new_application(client)
    delete_application(client, application_id)
    assert_error(post_resume(client, {"application_id": application_id}), 404)
    assert storage.saved == []


def test_resume_success_saves_file(local_client, settings):
    application_id = new_application(local_client)
    r = post_resume(local_client, {"application_id": application_id})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"ok", "application_id", "saved_path", "cover_letter_path", "match"}
    assert body["match"] == {"status": "no_job_description", "threshold": 70, "base_score": None, "tailored_score": None,
                             "added_terms": []}
    assert body["ok"] is True and body["application_id"] == application_id
    expected = settings.output_dir.resolve() / "Acme Corp" / str(application_id) / RESUME_FILE_NAME
    assert body["saved_path"] == str(expected)
    assert expected.is_absolute() and expected.read_bytes() == FAKE_PDF
    assert body["cover_letter_path"] == str(expected.parent / COVER_LETTER_FILE_NAME)


def test_resume_cover_letter_path_is_a_placeholder(local_client, settings):
    application_id = new_application(local_client)
    first = post_resume(local_client, {"application_id": application_id}).json()
    cover_letter = settings.output_dir.resolve() / "Acme Corp" / str(application_id) / COVER_LETTER_FILE_NAME
    assert first["cover_letter_path"] == str(cover_letter)
    assert str(cover_letter.parent) == str(Path(first["saved_path"]).parent)
    assert not cover_letter.exists()
    assert output_files(settings) == [cover_letter.parent / RESUME_FILE_NAME]
    cover_letter.write_bytes(b"%PDF-written-elsewhere")
    second = post_resume(local_client, {"application_id": application_id}).json()
    assert second["cover_letter_path"] == first["cover_letter_path"]
    assert cover_letter.read_bytes() == b"%PDF-written-elsewhere"


def test_resume_regenerate_replaces_file(local_client, settings, monkeypatch):
    application_id = new_application(local_client)
    first = post_resume(local_client, {"application_id": application_id}).json()["saved_path"]
    monkeypatch.setattr("app.main.generate_output", lambda application, settings: fake_output(b"%PDF-second"))
    r = post_resume(local_client, {"application_id": application_id})
    assert r.status_code == 201 and r.json()["saved_path"] == first
    assert output_files(settings) == [settings.output_dir.resolve() / "Acme Corp" / str(application_id) / RESUME_FILE_NAME]
    assert output_files(settings)[0].read_bytes() == b"%PDF-second"


def test_resume_upper_case_id(client, storage):
    application_id = new_application(client)
    r = post_resume(client, {"application_id": application_id.upper()})
    assert r.status_code == 201 and r.json()["application_id"] == application_id
    assert storage.saved == [("Acme Corp", application_id, FAKE_PDF)]


def test_resume_ignores_extra_fields(client, storage):
    application_id = new_application(client)
    body = {"application_id": application_id, "company": "Other Co", "full_job_description": "x"}
    assert post_resume(client, body).status_code == 201
    assert storage.saved == [("Acme Corp", application_id, FAKE_PDF)]


def test_resume_uses_updated_row(client, storage, monkeypatch):
    seen = []

    def capture(application, settings):
        seen.append(application)
        return fake_output()
    monkeypatch.setattr("app.main.generate_output", capture)
    application_id = new_application(client)
    patch_application(client, application_id, {"role": "Staff Engineer", "company": "Acme Inc"})
    assert post_resume(client, {"application_id": application_id}).status_code == 201
    assert seen[0].role == "Staff Engineer" and seen[0].id == application_id
    assert storage.saved[0][0] == "Acme Inc"


def test_resume_company_rename_leaves_old_folder(local_client, settings):
    application_id = new_application(local_client, company="Acme")
    old = post_resume(local_client, {"application_id": application_id}).json()["saved_path"]
    patch_application(local_client, application_id, {"company": "Acme Inc"})
    new = post_resume(local_client, {"application_id": application_id}).json()["saved_path"]
    assert old != new
    assert old.endswith(f"/Acme/{application_id}/{RESUME_FILE_NAME}")
    assert new.endswith(f"/Acme Inc/{application_id}/{RESUME_FILE_NAME}")
    assert len(output_files(settings)) == 2


def test_resume_without_job_description(client):
    body = {k: v for k, v in link_variant(f"{GH_LINK}9").items() if k != "full_job_description"}
    application_id = recorded(client, body)
    assert post_resume(client, {"application_id": application_id}).status_code == 201


def test_resume_leaves_application_unchanged(client, settings):
    application_id = new_application(client)
    before = stored_row(settings, application_id)
    assert post_resume(client, {"application_id": application_id}).status_code == 201
    assert stored_row(settings, application_id) == before
    assert before["status"] == "verified" and before["updated_at"] is None


@pytest.mark.parametrize("status", ["rejected", "withdrawn"])
def test_resume_for_closed_application(client, status):
    application_id = new_application(client)
    patch_application(client, application_id, {"status": status})
    assert post_resume(client, {"application_id": application_id}).status_code == 201


class FailingReads:
    def legacy_ids(self):
        return {}

    def get(self, application_id):
        raise ApplicationStoreError("OperationalError: disk I/O error: /secret/out/applications.sqlite3")


def test_resume_store_failure_503(settings, storage, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    client = TestClient(create_app(settings, storage, FailingReads()))
    r = post_resume(client, {"application_id": UNKNOWN})
    message = assert_error(r, 503)
    assert "/secret" not in r.text and "OperationalError" not in r.text and "disk" not in message
    assert "application_store_error" in caplog.text
    assert storage.saved == []


def _failing_render(application, settings):
    raise RenderError("tectonic exited with 1: /srv/data/BASE.tex:2 ! LaTeX Error")


def test_resume_render_failure_500_keeps_earlier_resume(local_client, settings, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    application_id = new_application(local_client)
    saved = post_resume(local_client, {"application_id": application_id}).json()["saved_path"]
    monkeypatch.setattr("app.main.generate_output", _failing_render)
    r = post_resume(local_client, {"application_id": application_id})
    assert r.json() == {"ok": False, "message": "Resume generation failed"} and r.status_code == 500
    assert "LaTeX" not in r.text and "/srv" not in r.text and "tectonic" not in r.text
    assert output_files(settings) == [settings.output_dir.resolve() / "Acme Corp" / str(application_id) / RESUME_FILE_NAME]
    assert open(saved, "rb").read() == FAKE_PDF
    errors = [json.loads(r.getMessage()) for r in caplog.records if '"render_error"' in r.getMessage()]
    assert errors[0]["application_id"] == application_id and "LaTeX Error" in errors[0]["error"]


def test_resume_storage_failure_502(settings, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    client = TestClient(create_app(settings, FakeStorage(fail=True)))
    application_id = new_application(client)
    r = post_resume(client, {"application_id": application_id})
    assert_error(r, 502)
    assert "/secret/out" not in r.text and "No space left" not in r.text and "OSError" not in r.text
    errors = [json.loads(r.getMessage()) for r in caplog.records if '"storage_error"' in r.getMessage()]
    assert errors[0]["application_id"] == application_id and "No space left" in errors[0]["error"]
    (line,) = resume_log_lines(caplog)
    assert line["status"] == 502


def test_resume_one_log_line_per_request(local_client, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    application_id = new_application(local_client, why_it_fits="payload-value")
    caplog.clear()
    post_resume(local_client, {"application_id": application_id, "note": "body-value"})
    post_resume(local_client, {"application_id": application_id}, {"X-API-Key": "wrong-key-value"})
    post_resume(local_client, {"application_id": 7})
    post_resume(local_client, {"application_id": UNKNOWN.upper()})
    post_resume(local_client, {"application_id": "not-a-uuid"})
    lines = resume_log_lines(caplog)
    assert [l["status"] for l in lines] == [201, 401, 422, 404, 404]
    assert [l.get("application_id") for l in lines] == [application_id, None, None, UNKNOWN, None]
    assert all({"event", "status", "duration_ms"} <= set(l) <= {"event", "status", "duration_ms", "application_id", "match_status"}
               for l in lines)
    assert '"application_request"' not in caplog.text and '"job_request"' not in caplog.text
    for value in ("payload-value", "body-value", "wrong-key-value", API_KEY, "Acme Corp", RESUME_FILE_NAME,
                  COVER_LETTER_FILE_NAME, "not-a-uuid"):
        assert value not in caplog.text


def test_resume_health_responds_during_slow_render(settings, storage, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(application, settings):
        started.set()
        release.wait(timeout=10)
        return fake_output(b"%PDF-slow")

    monkeypatch.setattr("app.main.generate_output", slow)
    client = TestClient(create_app(settings, storage))
    application_id = new_application(client)
    result = {}
    worker = threading.Thread(
        target=lambda: result.update(r=post_resume(client, {"application_id": application_id}))
    )
    worker.start()
    try:
        assert started.wait(timeout=5)
        assert client.get("/health").status_code == 200  # not blocked by the in-flight render
        assert "r" not in result
    finally:
        release.set()
        worker.join(timeout=10)
    assert result["r"].status_code == 201


# --- tailoring outcomes ---

@pytest.mark.parametrize("match", [Match("no_job_description"), Match("base_meets_threshold", 82), Match("tailored", 58, 77),
                                   Match("tailored", 49, 73, added_terms=("testing", "TypeScript"))])
def test_resume_reports_how_it_was_chosen(client, monkeypatch, match):
    monkeypatch.setattr("app.main.generate_output", lambda application, settings: fake_output(match=match))
    application_id = new_application(client)
    body = post_resume(client, {"application_id": application_id}).json()
    assert body["match"] == {"status": match.status, "threshold": 70, "base_score": match.base_score,
                             "tailored_score": match.tailored_score, "added_terms": list(match.added_terms)}


def _failing_tailoring(application, settings):
    raise TailoringError("verify", "check_failed", failed_checks=["unknown_skill", "one_page"], run=RunStats(9, 0.43219))


def test_resume_tailoring_failure_500_keeps_earlier_resume(local_client, settings, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    application_id = new_application(local_client)
    saved = post_resume(local_client, {"application_id": application_id}).json()["saved_path"]
    monkeypatch.setattr("app.main.generate_output", _failing_tailoring)
    r = post_resume(local_client, {"application_id": application_id})
    assert r.status_code == 500 and r.json() == {"ok": False, "message": "Resume generation failed"}
    assert open(saved, "rb").read() == FAKE_PDF
    assert output_files(settings) == [Path(saved)]
    (error,) = [json.loads(rec.getMessage()) for rec in caplog.records if '"tailoring_error"' in rec.getMessage()]
    assert error == {"event": "tailoring_error", "application_id": application_id, "stage": "verify",
                     "reason": "check_failed", "failed_checks": ["unknown_skill", "one_page"]}
    line = resume_log_lines(caplog)[-1]
    assert (line["status"], line["claude_turns"], line["claude_cost_usd"]) == (500, 9, 0.4322)


def test_resume_without_claude_credential_500(settings, storage, monkeypatch, caplog):
    from app.generation import generate_output
    caplog.set_level(logging.INFO, logger="app.requests")
    monkeypatch.setattr("app.main.generate_output", generate_output)
    unconfigured = settings.model_copy(update={"anthropic_api_key": None, "claude_code_oauth_token": None})
    client = TestClient(create_app(unconfigured, storage))
    application_id = new_application(client, full_job_description=" ".join(["Python"] * 60))
    r = post_resume(client, {"application_id": application_id})
    assert r.status_code == 500 and r.json() == {"ok": False, "message": "Resume generation failed"}
    assert storage.saved == []
    (error,) = [json.loads(rec.getMessage()) for rec in caplog.records if '"tailoring_error"' in rec.getMessage()]
    assert (error["stage"], error["reason"]) == ("claude", "not_configured")


def test_resume_log_has_match_details_and_no_text(local_client, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    monkeypatch.setattr("app.main.generate_output", lambda application, settings: fake_output(
        match=Match("tailored", 58, 77, added_terms=("Airflow",)),
        run=RunStats(14, 1.234567, ("claude-opus-5-5",), terms_approved=1, terms_rejected=2)))
    application_id = new_application(local_client, full_job_description="A posting about Kafka streaming platforms.")
    caplog.clear()
    post_resume(local_client, {"application_id": application_id})
    (line,) = resume_log_lines(caplog)
    assert {k: v for k, v in line.items() if k != "duration_ms"} == {
        "event": "resume_request", "status": 201, "application_id": application_id, "match_status": "tailored",
        "base_score": 58, "tailored_score": 77, "claude_turns": 14, "claude_cost_usd": 1.2346,
        "terms_approved": 1, "terms_rejected": 2}
    for text in ("Kafka", "Airflow", "Acme Corp", RESUME_FILE_NAME, "claude-opus-5-5"):
        assert text not in caplog.text


def test_legacy_paths_gone(client, storage, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    r = client.post("/jobs", json={"company": "Acme", "role": "Eng", "full_job_description": "x"}, headers=HEADERS)
    assert r.status_code == 404
    for path in ["/files/outputs/2026-01-01/x.pdf", "/files/x?expires=9999999999&sig=" + "0" * 64]:
        assert client.get(path).status_code == 404
    assert storage.saved == []
    assert resume_log_lines(caplog) == []


# --- integer-ID stores ---

def integer_id_store(path):
    """A store as written before UUIDs, holding application 1 for Acme Corp."""
    from app.applications import FIELDS
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_link_key TEXT NOT NULL UNIQUE, "
            f"job_link TEXT NOT NULL, {', '.join(f'{n} TEXT' for n in FIELDS)}, created_at TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'verified', updated_at TEXT)"
        )
        conn.execute(
            "INSERT INTO applications (id, job_link_key, job_link, company, role, posting_source_type, "
            "verification_method, official_apply_url, created_at, status) VALUES (1, ?, ?, 'Acme Corp', 'Engineer', "
            "'employer_site', 'employer_site', '', '2026-10-01T00:00:00Z', 'applied')",
            (GH_LINK, GH_LINK),
        )
    path.chmod(0o600)


def test_startup_migrates_ids_and_resume_folders(settings):
    integer_id_store(settings.output_dir / "applications.sqlite3")
    old = settings.output_dir / "Acme Corp" / "1" / RESUME_FILE_NAME
    old.parent.mkdir(parents=True)
    old.write_bytes(b"%PDF-old")
    client = TestClient(create_app(settings, LocalStorage(settings.output_dir)))

    (row,) = stored_rows(settings)
    new_id = row["id"]
    assert UUID4.match(new_id) and row["status"] == "applied"
    assert not old.parent.exists()
    assert (settings.output_dir / "Acme Corp" / new_id / RESUME_FILE_NAME).read_bytes() == b"%PDF-old"

    assert_error(patch_application(client, "1", {"status": "offer"}), 404)
    assert_error(post_resume(client, {"application_id": 1}), 422)
    r = post_resume(client, {"application_id": new_id})
    assert r.status_code == 201 and r.json()["saved_path"].endswith(f"/Acme Corp/{new_id}/{RESUME_FILE_NAME}")
    assert post_application(client, VALID_APPLICATION).json()["application_id"] == new_id
