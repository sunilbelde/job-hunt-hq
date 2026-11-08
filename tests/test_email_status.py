import json
import logging
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.applications import ApplicationStoreError
from app.main import create_app
from app.models import EMAIL_STATUS_EXAMPLE, EmailStatusRequest
from tests.conftest import API_KEY, VALID_APPLICATION

HEADERS = {"X-API-Key": API_KEY}
PATH = "/application/email-status"
OTHER_LINK = "https://job-boards.greenhouse.io/acme/jobs/7654321"


def record(client, **overrides):
    body = {**VALID_APPLICATION, **overrides}
    if "job_link" in overrides:
        body["official_apply_url"] = overrides["job_link"]
    r = client.post("/application", json=body, headers=HEADERS)
    assert r.status_code == 201
    return r.json()["application_id"]


def email(client, body, headers=HEADERS):
    return client.post(PATH, json=body, headers=headers)


def rows(settings):
    with closing(sqlite3.connect(settings.output_dir / "applications.sqlite3")) as conn:
        conn.row_factory = sqlite3.Row
        return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM applications")}


def set_status(settings, application_id, status):
    with closing(sqlite3.connect(settings.output_dir / "applications.sqlite3")) as conn, conn:
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, application_id))


def body(status="Rejected", company="Acme Corp", role="Senior Software Engineer, Applied AI", **extra):
    return {"company": company, "role": role, "status": status, **extra}


# --- Request model ---

def test_example_validates():
    assert EmailStatusRequest.model_validate(EMAIL_STATUS_EXAMPLE).status == "Rejected"


@pytest.mark.parametrize(("sent", "parsed"), [("rejected", "Rejected"), (" RESPONSE ", "Response"),
                                              ("applied", "Applied")])
def test_status_case_and_spacing_ignored(sent, parsed):
    assert EmailStatusRequest.model_validate(body(sent)).status == parsed


@pytest.mark.parametrize("field", ["company", "role"])
@pytest.mark.parametrize("value", ["", "   ", None, 5])
def test_blank_or_wrong_type_name_refused(field, value):
    with pytest.raises(ValidationError) as exc:
        EmailStatusRequest.model_validate({**body(), field: value})
    assert field in str(exc.value)


# --- Authentication ---

@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_key_required(client, settings, headers):
    application_id = record(client)
    r = email(client, body(), headers)
    assert r.status_code == 401 and r.json()["ok"] is False and r.json()["message"]
    assert rows(settings)[application_id]["status"] == "verified"


def test_wrong_key_with_malformed_body_is_401(client):
    r = client.post(PATH, content=b"not json", headers={"X-API-Key": "wrong", "Content-Type": "application/json"})
    assert r.status_code == 401


def test_no_match_hidden_without_key(client):
    assert email(client, body(company="Nobody"), {}).status_code == 401


# --- Body validation ---

def test_email_workflow_summary_accepted(client, settings):
    application_id = record(client)
    r = email(client, body("Rejected", received_at="Nov 7, 2026 9:21 PM", note="Thanks, but no.", extra=True))
    assert r.status_code == 200
    assert rows(settings)[application_id]["status"] == "rejected"


@pytest.mark.parametrize("value", ["Interview", "Offer", "secret-ish-value", None, 3])
def test_unknown_email_status_refused(client, settings, value):
    application_id = record(client)
    r = email(client, body(value))
    assert r.status_code == 422 and "status" in r.json()["message"]
    if isinstance(value, str):
        assert value not in r.text
    assert rows(settings)[application_id]["status"] == "verified"


@pytest.mark.parametrize("field", ["company", "role"])
@pytest.mark.parametrize("value", ["", None, 7, "drop"])
def test_missing_company_or_role_refused(client, field, value):
    sent = body()
    if value == "drop":
        del sent[field]
    else:
        sent[field] = value
    r = email(client, sent)
    assert r.status_code == 422 and field in r.json()["message"]


@pytest.mark.parametrize("content", [b"not json", b"[]", b'"text"', b"3", b"null"])
def test_malformed_body_refused(client, content):
    r = client.post(PATH, content=content, headers={**HEADERS, "Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["ok"] is False and r.json()["message"]


def test_note_and_received_at_not_stored_or_logged(client, settings, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    application_id = record(client)
    email(client, body(received_at="received-value", note="note-value"))
    stored = rows(settings)[application_id]
    assert "received-value" not in json.dumps(stored) and "note-value" not in json.dumps(stored)
    assert "received-value" not in caplog.text and "note-value" not in caplog.text


# --- Matching ---

def test_tolerant_names_match(client, settings):
    application_id = record(client)
    r = email(client, body("Response", company="ACME corp.", role="senior software engineer - applied ai"))
    assert r.status_code == 200 and r.json()["application_id"] == application_id


def test_no_match_404_changes_nothing(client, settings):
    record(client)
    before = rows(settings)
    r = email(client, body(company="Brex"))
    assert r.status_code == 404
    assert r.json()["ok"] is False and r.json()["reason"] == "no_match" and r.json()["message"]
    assert rows(settings) == before


def test_company_matches_but_role_does_not(client):
    record(client)
    r = email(client, body(role="Product Designer"))
    assert r.status_code == 404 and r.json()["reason"] == "no_match"


def test_ambiguous_409_changes_nothing(client, settings):
    first = record(client)
    second = record(client, job_link=OTHER_LINK)
    before = rows(settings)
    r = email(client, body())
    assert r.status_code == 409
    data = r.json()
    assert data["ok"] is False and data["reason"] == "ambiguous" and data["match_count"] == 2 and data["message"]
    assert first not in r.text and second not in r.text
    assert rows(settings) == before


def test_job_link_resolves_ambiguity(client, settings):
    record(client)
    second = record(client, job_link=OTHER_LINK)
    r = email(client, body(job_link=OTHER_LINK + "?utm_source=email"))
    assert r.status_code == 200 and r.json()["application_id"] == second
    assert rows(settings)[second]["status"] == "rejected"


def test_unknown_job_link_falls_back_to_names(client):
    application_id = record(client)
    r = email(client, body(job_link="https://example.com/not-recorded"))
    assert r.status_code == 200 and r.json()["application_id"] == application_id


# --- Mapping and response ---

def test_response_shape(client, settings):
    application_id = record(client)
    set_status(settings, application_id, "applied")
    r = email(client, body("Rejected"))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "application_id": application_id, "company": "Acme Corp",
                        "role": "Senior Software Engineer, Applied AI", "previous_status": "applied",
                        "status": "rejected", "changed": True}


@pytest.mark.parametrize("current", ["verified", "applied"])
def test_applied_confirms_only(client, settings, current):
    application_id = record(client)
    set_status(settings, application_id, current)
    before = rows(settings)[application_id]
    r = email(client, body("Applied"))
    assert r.status_code == 200 and r.json()["changed"] is False and r.json()["status"] == current
    assert rows(settings)[application_id] == before


@pytest.mark.parametrize(("current", "email_status", "after"), [
    ("applied", "Rejected", "rejected"),
    ("interviewing", "Rejected", "rejected"),
    ("offer", "Rejected", "rejected"),
    ("withdrawn", "Rejected", "withdrawn"),
    ("verified", "Response", "interviewing"),
    ("applied", "Response", "interviewing"),
    ("rejected", "Response", "rejected"),
    ("offer", "Response", "offer"),
])
def test_mapping_over_http(client, settings, current, email_status, after):
    application_id = record(client)
    set_status(settings, application_id, current)
    r = email(client, body(email_status))
    assert r.status_code == 200
    assert r.json()["status"] == after and r.json()["changed"] is (after != current)
    assert rows(settings)[application_id]["status"] == after


def test_repeated_rejection(client):
    record(client)
    assert email(client, body()).json()["changed"] is True
    second = email(client, body())
    assert second.status_code == 200 and second.json()["changed"] is False


def test_only_status_and_updated_at_change(client, settings):
    application_id = record(client)
    before = rows(settings)[application_id]
    email(client, body("Response"))
    after = rows(settings)[application_id]
    assert after["status"] == "interviewing" and after["updated_at"]
    strip = lambda r: {k: v for k, v in r.items() if k not in ("status", "updated_at")}
    assert strip(after) == strip(before)


# --- Store failure ---

class FailingStore:
    def legacy_ids(self):
        return {}

    def apply_email_status(self, *args):
        raise ApplicationStoreError("OperationalError: disk I/O error: /secret/out/applications.sqlite3")


def test_store_failure_503(settings, storage, caplog):
    caplog.set_level(logging.INFO, logger="app.requests")
    client = TestClient(create_app(settings, storage, FailingStore()))
    r = email(client, body())
    assert r.status_code == 503 and r.json()["ok"] is False
    assert "/secret" not in r.text and "OperationalError" not in r.text and "disk" not in r.json()["message"]
    assert "application_store_error" in caplog.text


# --- Logging ---

def log_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records
            if r.name == "app.requests" and '"application_request"' in r.getMessage()]


def test_one_log_line_without_body_values(client, settings, caplog):
    application_id = record(client)
    record(client, job_link=OTHER_LINK, role="Staff Engineer")
    caplog.set_level(logging.INFO, logger="app.requests")
    caplog.clear()
    email(client, body("Rejected"))
    email(client, body("Rejected", role="Staff Engineer", job_link=OTHER_LINK, note="n", received_at="r"))
    email(client, body(company="Nobody Inc"))
    email(client, body(), {"X-API-Key": "wrong-key-value"})
    lines = log_lines(caplog)
    assert [(l["method"], l["status"]) for l in lines] == [("POST", 200), ("POST", 200), ("POST", 404), ("POST", 401)]
    assert lines[0]["application_id"] == application_id
    assert all("duration_ms" in l for l in lines)
    assert "application_id" not in lines[2] and "application_id" not in lines[3]
    text = caplog.text
    for value in ("Acme Corp", "Staff Engineer", "Senior Software Engineer", "Rejected", "rejected", OTHER_LINK,
                  "Nobody", "wrong-key-value", API_KEY):
        assert value not in text


def test_ambiguous_log_has_no_id(client, caplog):
    record(client)
    record(client, job_link=OTHER_LINK)
    caplog.set_level(logging.INFO, logger="app.requests")
    caplog.clear()
    email(client, body())
    lines = log_lines(caplog)
    assert len(lines) == 1 and lines[0]["status"] == 409 and "application_id" not in lines[0]
