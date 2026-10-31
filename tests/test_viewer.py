import json
import logging
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.applications import ApplicationStore, ApplicationStoreError
from app.main import create_app
from app.rendering import RenderError
from app.storage import COVER_LETTER_FILE_NAME, RESUME_FILE_NAME, LocalStorage
from app.tailoring import Match
from tests.conftest import API_KEY, FAKE_PDF, GH_LINK, VALID_APPLICATION, fake_output

HEADERS = {"X-API-Key": API_KEY}
UNKNOWN = "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"
TAILORED = Match(
    "tailored", 58, 81, added_terms=("Airflow",),
    base_breakdown={"score": 58, "keywords": [{"term": "Airflow", "importance": "preferred", "present": False}],
                    "requirements": [{"id": "R1", "text": "Runs Kafka streaming", "status": "missing"}]},
    tailored_breakdown={"score": 81, "keywords": [{"term": "Airflow", "importance": "preferred", "present": True}],
                        "requirements": [{"id": "R1", "text": "Runs Kafka streaming", "status": "met"}]},
    rejected_terms=({"term": "Kafka", "reason": "rejected by the judge"},),
)
READ_PATHS = ["/applications", f"/application/{UNKNOWN}", f"/application/{UNKNOWN}/resume.pdf",
              f"/application/{UNKNOWN}/cover-letter.pdf", "/resume/base.pdf", "/cover-letter/base.pdf"]


@pytest.fixture
def viewer(settings):
    """The docs listener's app: viewer on, saving real files under OUTPUT_DIR."""
    return TestClient(create_app(settings.model_copy(update={"api_docs_enabled": True}), LocalStorage(settings.output_dir)))


@pytest.fixture
def base_letter(tmp_path, monkeypatch):
    """A stand-in for the committed data/COVER_LETTER.pdf."""
    path = tmp_path / "data" / "COVER_LETTER.pdf"
    path.parent.mkdir()
    path.write_bytes(b"%PDF-base-letter")
    monkeypatch.setattr("app.viewer.BASE_COVER_LETTER", path)
    return path


@pytest.fixture
def base_pdf(monkeypatch):
    """Stand-in for the TeX render of the base resume; counts the renders."""
    calls = []

    def render(main_tex="BASE.tex", template_dir=None):
        calls.append(template_dir)
        return b"%PDF-base"

    monkeypatch.setattr("app.viewer.render_pdf", render)
    return calls


def record(client, n=1, **overrides) -> str:
    link = f"{GH_LINK}{n}"
    body = {**VALID_APPLICATION, "job_link": link, "official_apply_url": link, **overrides}
    r = client.post("/application", json=body, headers=HEADERS)
    assert r.status_code == 201, r.text
    return r.json()["application_id"]


def generate(client, monkeypatch, application_id, match=TAILORED, content=FAKE_PDF) -> dict:
    monkeypatch.setattr("app.main.generate_output", lambda application, settings: fake_output(content, match))
    r = client.post("/resume", json={"application_id": application_id}, headers=HEADERS)
    assert r.status_code == 202, r.text
    job = client.get(f"/resume/{application_id}/status", headers=HEADERS).json()
    assert job["status"] == "done", job
    return job


def save_letter(settings, application_id, content=b"%PDF letter", company="Acme Corp") -> Path:
    """A cover letter where POST /cover-letter saves it."""
    path = settings.output_dir / company / application_id / COVER_LETTER_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def store_of(settings) -> ApplicationStore:
    return ApplicationStore(settings.output_dir / "applications.sqlite3")


def assert_error(r, status, message):
    assert (r.status_code, r.json()) == (status, {"ok": False, "message": message})


# --- served only where docs are ---

@pytest.mark.parametrize("path", [*READ_PATHS, "/viewer"])
@pytest.mark.parametrize("headers", [{}, HEADERS])
def test_not_served_without_docs(settings, storage, path, headers):
    public = TestClient(create_app(settings, storage))
    record(public)
    r = public.get(path, headers=headers)
    assert (r.status_code, r.json()) == (404, public.get("/no-such-path").json())  # as for any unknown path


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_reads_need_no_key(viewer, settings, base_pdf, base_letter, headers):
    application_id = record(viewer)
    save_letter(settings, application_id)
    assert viewer.get("/applications", headers=headers).status_code == 200
    assert viewer.get("/resume/base.pdf", headers=headers).content == b"%PDF-base"
    assert viewer.get("/cover-letter/base.pdf", headers=headers).content == b"%PDF-base-letter"
    assert viewer.get(f"/application/{application_id}/cover-letter.pdf", headers=headers).content == b"%PDF letter"
    assert_error(viewer.get(f"/application/{UNKNOWN}", headers=headers), 404, "Application not found")
    assert_error(viewer.get(f"/application/{UNKNOWN}/resume.pdf", headers=headers), 404, "Application not found")


# --- GET /applications ---

def test_list_orders_by_generation_and_summarises_reports(viewer, settings, monkeypatch):
    older, newer, never = record(viewer, 1), record(viewer, 2), record(viewer, 3, full_job_description="secret posting")
    generate(viewer, monkeypatch, newer, Match("base_meets_threshold", 76))
    generate(viewer, monkeypatch, older)
    r = viewer.get("/applications")
    assert r.status_code == 200 and r.json()["ok"] is True
    listed = r.json()["applications"]
    assert [item["id"] for item in listed] == [older, newer, never]
    first = listed[0]
    assert (first["company"], first["role"], first["status"]) == ("Acme Corp", VALID_APPLICATION["role"], "verified")
    assert {k: v for k, v in first["report"].items() if k != "generated_at"} == {
        "status": "tailored", "threshold": 70, "base_score": 58, "tailored_score": 81}
    assert listed[1]["report"]["status"] == "base_meets_threshold" and listed[2]["report"] is None
    assert "secret posting" not in r.text and "Full text of the posting" not in r.text


def test_list_store_unavailable(settings, storage, monkeypatch):
    client = TestClient(create_app(settings.model_copy(update={"api_docs_enabled": True}), storage))

    def broken(self):
        raise ApplicationStoreError("OperationalError: unable to open database file")

    monkeypatch.setattr(ApplicationStore, "list_with_reports", broken)
    assert_error(client.get("/applications"), 503, "Application store unavailable")


# --- GET /application/{id} ---

def test_detail_with_report(viewer, monkeypatch):
    application_id = record(viewer)
    assert generate(viewer, monkeypatch, application_id)["saved_path"] == RESUME_FILE_NAME
    body = viewer.get(f"/application/{application_id}").json()
    assert body["ok"] is True
    application = body["application"]
    assert application["id"] == application_id and application["created_at"]
    links = ("job_link", "official_apply_url")
    assert {k: application[k] for k in VALID_APPLICATION if k not in links} == {
        k: v for k, v in VALID_APPLICATION.items() if k not in links}
    assert application["job_link"] == f"{GH_LINK}1"
    report = body["report"]
    assert (report["status"], report["saved_path"], report["added_terms"]) == ("tailored", RESUME_FILE_NAME, ["Airflow"])
    assert report["base"] == TAILORED.base_breakdown and report["tailored"] == TAILORED.tailored_breakdown
    assert report["rejected_terms"] == [{"term": "Kafka", "reason": "rejected by the judge"}]


def test_detail_without_report(viewer):
    application_id = record(viewer)
    assert viewer.get(f"/application/{application_id}").json()["report"] is None


@pytest.mark.parametrize("application_id", [UNKNOWN, "not-a-uuid", "7"])
def test_detail_unknown_id(viewer, application_id):
    record(viewer)
    assert_error(viewer.get(f"/application/{application_id}"), 404, "Application not found")
    assert_error(viewer.get(f"/application/{application_id}/resume.pdf"), 404, "Application not found")
    assert_error(viewer.get(f"/application/{application_id}/cover-letter.pdf"), 404, "Application not found")


def test_detail_store_unavailable(viewer, monkeypatch):
    application_id = record(viewer)

    def broken(self, application_id):
        raise ApplicationStoreError("OperationalError: unable to open database file")

    monkeypatch.setattr(ApplicationStore, "get_report", broken)
    for path in (f"/application/{application_id}", f"/application/{application_id}/resume.pdf",
                 f"/application/{application_id}/cover-letter.pdf"):
        assert_error(viewer.get(path), 503, "Application store unavailable")


# --- GET /application/{id}/resume.pdf ---

def test_saved_resume_returned(viewer, monkeypatch):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id, content=b"%PDF-1.5 tailored bytes")
    r = viewer.get(f"/application/{application_id}/resume.pdf")
    assert (r.status_code, r.content) == (200, b"%PDF-1.5 tailored bytes")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store" and r.headers["content-disposition"] == "inline"


def test_renamed_company_still_served_from_the_saved_path(viewer, settings, monkeypatch):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id, content=b"%PDF old company")
    viewer.patch(f"/application/{application_id}", json={"company": "Acme Inc"}, headers=HEADERS)
    assert viewer.get(f"/application/{application_id}/resume.pdf").content == b"%PDF old company"


def test_legacy_resume_found_by_current_company(viewer, settings):
    application_id = record(viewer)
    path = settings.output_dir / "Acme Corp" / application_id / RESUME_FILE_NAME
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF legacy")
    r = viewer.get(f"/application/{application_id}/resume.pdf")
    assert (r.status_code, r.content) == (200, b"%PDF legacy")


def test_never_generated(viewer):
    application_id = record(viewer)
    assert_error(viewer.get(f"/application/{application_id}/resume.pdf"), 404, "Resume not found")


@pytest.mark.parametrize("where", ["outside", "symlink_out", "folder"])
def test_saved_path_must_be_a_file_inside_output_dir(viewer, settings, tmp_path, where):
    application_id = record(viewer)
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"%PDF not yours")
    inside = settings.output_dir / "Acme Corp" / application_id / RESUME_FILE_NAME
    inside.parent.mkdir(parents=True)
    if where == "outside":
        saved = secret
    elif where == "symlink_out":
        inside.symlink_to(secret)
        saved = inside
    else:
        saved = inside.parent
    store_of(settings).save_report(application_id, "2026-10-20T10:00:00Z", str(saved), TAILORED.report())
    r = viewer.get(f"/application/{application_id}/resume.pdf")
    assert_error(r, 404, "Resume not found")
    assert b"not yours" not in r.content


# --- GET /application/{id}/cover-letter.pdf ---

def test_saved_cover_letter_returned(viewer, settings):
    application_id = record(viewer)
    save_letter(settings, application_id, b"%PDF-1.5 letter bytes")
    r = viewer.get(f"/application/{application_id}/cover-letter.pdf")
    assert (r.status_code, r.content) == (200, b"%PDF-1.5 letter bytes")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store" and r.headers["content-disposition"] == "inline"


def test_letter_written_before_a_rename_found_beside_the_resume(viewer, settings, monkeypatch):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id)
    save_letter(settings, application_id, b"%PDF old company letter")
    viewer.patch(f"/application/{application_id}", json={"company": "Acme Inc"}, headers=HEADERS)
    assert viewer.get(f"/application/{application_id}/cover-letter.pdf").content == b"%PDF old company letter"


def test_detail_after_a_rename_names_only_the_file(viewer, settings, monkeypatch):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id, content=b"%PDF old company")
    save_letter(settings, application_id, b"%PDF old company letter")
    viewer.patch(f"/application/{application_id}", json={"company": "Acme Inc"}, headers=HEADERS)
    assert viewer.get(f"/application/{application_id}").json()["report"]["saved_path"] == RESUME_FILE_NAME
    assert store_of(settings).get_report(application_id)["saved_path"] == str(
        settings.output_dir.resolve() / "Acme Corp" / application_id / RESUME_FILE_NAME)
    assert viewer.get(f"/application/{application_id}/resume.pdf").content == b"%PDF old company"
    assert viewer.get(f"/application/{application_id}/cover-letter.pdf").content == b"%PDF old company letter"


def test_letter_for_the_current_company_comes_first(viewer, settings, monkeypatch):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id)
    save_letter(settings, application_id, b"%PDF old company letter")
    viewer.patch(f"/application/{application_id}", json={"company": "Acme Inc"}, headers=HEADERS)
    save_letter(settings, application_id, b"%PDF new company letter", company="Acme Inc")
    assert viewer.get(f"/application/{application_id}/cover-letter.pdf").content == b"%PDF new company letter"


def test_no_cover_letter_generated(viewer, monkeypatch):
    application_id = record(viewer)
    assert_error(viewer.get(f"/application/{application_id}/cover-letter.pdf"), 404, "Cover letter not found")
    generate(viewer, monkeypatch, application_id)  # a resume alone is not a letter
    assert_error(viewer.get(f"/application/{application_id}/cover-letter.pdf"), 404, "Cover letter not found")


@pytest.mark.parametrize("where", ["report_outside", "symlink_out", "folder"])
def test_cover_letter_must_be_a_file_inside_output_dir(viewer, settings, tmp_path, where):
    application_id = record(viewer)
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / COVER_LETTER_FILE_NAME).write_bytes(b"%PDF not yours")
    inside = settings.output_dir / "Acme Corp" / application_id / COVER_LETTER_FILE_NAME
    inside.parent.mkdir(parents=True)
    if where == "report_outside":
        store_of(settings).save_report(application_id, "2026-10-20T10:00:00Z", str(secret / RESUME_FILE_NAME),
                                       TAILORED.report())
    elif where == "symlink_out":
        inside.symlink_to(secret / COVER_LETTER_FILE_NAME)
    else:
        inside.mkdir()
    r = viewer.get(f"/application/{application_id}/cover-letter.pdf")
    assert_error(r, 404, "Cover letter not found")
    assert b"not yours" not in r.content


# --- GET /cover-letter/base.pdf ---

def test_base_cover_letter_returned_as_committed(viewer, base_letter):
    r = viewer.get("/cover-letter/base.pdf")
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, b"%PDF-base-letter", "application/pdf")
    assert r.headers["cache-control"] == "no-store"
    base_letter.write_bytes(b"%PDF-re-rendered")
    assert viewer.get("/cover-letter/base.pdf").content == b"%PDF-re-rendered"


def test_base_cover_letter_missing(viewer, base_letter):
    base_letter.unlink()
    assert_error(viewer.get("/cover-letter/base.pdf"), 404, "Base cover letter not found")


def test_base_cover_letter_is_the_committed_file():
    from app.viewer import BASE_COVER_LETTER
    assert BASE_COVER_LETTER == Path(__file__).resolve().parent.parent / "data" / "COVER_LETTER.pdf"


# --- GET /resume/base.pdf ---

def test_base_resume_rendered_once(viewer, base_pdf):
    for _ in range(2):
        r = viewer.get("/resume/base.pdf")
        assert (r.status_code, r.content, r.headers["content-type"]) == (200, b"%PDF-base", "application/pdf")
        assert r.headers["cache-control"] == "no-store"
    assert len(base_pdf) == 1


def test_base_resume_rendered_again_when_the_template_changes(tmp_path, monkeypatch):
    from app.viewer import BaseResumeCache
    template = tmp_path / "template"
    template.mkdir()
    (template / "BASE.tex").write_text("one")
    renders = []
    monkeypatch.setattr("app.viewer.render_pdf", lambda template_dir: renders.append(1) or f"%PDF {len(renders)}".encode())
    cache = BaseResumeCache(template)
    assert cache.get() == cache.get() == b"%PDF 1"
    (template / "BASE.tex").write_text("two, longer")
    assert cache.get() == b"%PDF 2"
    os.utime(template / "BASE.tex", ns=(1, 1))
    assert cache.get() == b"%PDF 3"
    (template / "notes.txt").write_text("not a template file")
    assert cache.get() == b"%PDF 3"


def test_base_render_failure(viewer, monkeypatch, caplog):
    def broken(main_tex="BASE.tex", template_dir=None):
        raise RenderError("tectonic exited with 1")

    monkeypatch.setattr("app.viewer.render_pdf", broken)
    assert_error(viewer.get("/resume/base.pdf"), 500, "Resume generation failed")


# --- reads change nothing, and are logged without content ---

def snapshot(settings) -> tuple:
    with closing(sqlite3.connect(settings.output_dir / "applications.sqlite3")) as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY id").fetchall()
        reports = conn.execute("SELECT * FROM resume_reports ORDER BY application_id").fetchall()
    files = sorted((str(p), p.read_bytes()) for p in settings.output_dir.rglob("*.pdf"))
    return rows, reports, files


def test_reads_change_nothing(viewer, settings, monkeypatch, base_pdf, base_letter):
    first, second = record(viewer, 1), record(viewer, 2)
    generate(viewer, monkeypatch, first)
    save_letter(settings, first)
    before = snapshot(settings), base_letter.read_bytes()
    for path in ["/applications", "/resume/base.pdf", "/cover-letter/base.pdf", "/viewer",
                 *(p for i in (first, second) for p in (f"/application/{i}", f"/application/{i}/resume.pdf",
                                                        f"/application/{i}/cover-letter.pdf"))]:
        viewer.get(path)
    assert (snapshot(settings), base_letter.read_bytes()) == before


def request_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records
            if r.name == "app.requests" and r.getMessage().startswith('{"event": "')
            and json.loads(r.getMessage())["event"] in ("application_request", "resume_request", "cover_letter_request")]


def test_each_read_logged_once_without_content(viewer, settings, monkeypatch, base_pdf, base_letter, caplog):
    application_id = record(viewer, full_job_description="A posting about Kafka streaming platforms.")
    generate(viewer, monkeypatch, application_id)
    save_letter(settings, application_id, b"%PDF Dear Hiring Manager")
    caplog.set_level(logging.INFO, logger="app.requests")
    caplog.clear()
    viewer.get("/viewer")
    assert request_lines(caplog) == []
    for path, event in [("/applications", "application_request"), (f"/application/{application_id}", "application_request"),
                        (f"/application/{application_id}/resume.pdf", "application_request"),
                        (f"/application/{application_id}/cover-letter.pdf", "application_request"),
                        ("/resume/base.pdf", "resume_request"), ("/cover-letter/base.pdf", "cover_letter_request")]:
        caplog.clear()
        viewer.get(path)
        (line,) = request_lines(caplog)
        expected = {"event": event, "method": "GET", "status": 200}
        if path.startswith("/application/"):
            expected["application_id"] = application_id
        assert {k: v for k, v in line.items() if k != "duration_ms"} == expected
    for text in ("Kafka", "Airflow", "Acme Corp", API_KEY, "Runs Kafka streaming", "Dear Hiring Manager",
                 "base-letter", COVER_LETTER_FILE_NAME, str(settings.output_dir)):
        assert text not in caplog.text


# --- the viewer's writes ---

SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


def set_status(client, application_id, body, headers=SAME_ORIGIN):
    return client.patch(f"/viewer/application/{application_id}", json=body, headers=headers)


def delete(client, application_id, headers=SAME_ORIGIN):
    return client.delete(f"/viewer/application/{application_id}", headers=headers)


@pytest.mark.parametrize("path, expected", [
    ("/viewer/application/abc", "application_request"), ("/viewer", None), ("/viewer/", None),
    ("/application/abc", "application_request"),
])
def test_viewer_writes_logged_as_application_requests(path, expected):
    from app.main import request_event
    assert request_event(path) == expected


@pytest.mark.parametrize("headers, allowed", [
    ({}, True),
    ({"Sec-Fetch-Site": "same-origin"}, True),
    ({"Sec-Fetch-Site": "same-site"}, False),
    ({"Sec-Fetch-Site": "cross-site"}, False),
    ({"Sec-Fetch-Site": "none"}, False),
    ({"Origin": "http://testserver"}, True),
    ({"Origin": "http://TestServer"}, True),
    ({"Origin": "https://evil.example"}, False),
    ({"Origin": "null"}, False),
    ({"Sec-Fetch-Site": "same-origin", "Origin": "https://evil.example"}, True),  # Sec-Fetch-Site decides
    ({"Sec-Fetch-Site": "cross-site", "Origin": "http://testserver"}, False),
])
def test_same_origin(headers, allowed):
    from starlette.requests import Request
    scope = {"type": "http", "headers": [(b"host", b"testserver"),
                                         *((k.lower().encode(), v.encode()) for k, v in headers.items())]}
    from app.main import same_origin
    assert same_origin(Request(scope)) is allowed


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, SAME_ORIGIN])
def test_status_changed_without_a_key(viewer, headers):
    application_id = record(viewer)
    before = viewer.get(f"/application/{application_id}").json()
    r = set_status(viewer, application_id, {"status": "applied"}, headers)
    assert (r.status_code, r.json()) == (200, {"ok": True, "application_id": application_id, "status": "applied"})
    after = viewer.get(f"/application/{application_id}").json()
    assert after["application"].pop("status") == "applied"
    for body in (before, after):
        body["application"].pop("status", None)
        body["application"].pop("updated_at")
    assert after == before
    assert next(a for a in viewer.get("/applications").json()["applications"]
                if a["id"] == application_id)["status"] == "applied"


def test_status_write_ignores_other_fields(viewer):
    application_id = record(viewer)
    assert set_status(viewer, application_id, {"status": "offer", "company": "Other"}).json()["status"] == "offer"
    assert viewer.get(f"/application/{application_id}").json()["application"]["company"] == "Acme Corp"


def test_same_status_again(viewer):
    application_id = record(viewer)
    assert set_status(viewer, application_id, {"status": "verified"}).status_code == 200


def test_status_write_keeps_the_report(viewer, monkeypatch):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id)
    report = viewer.get(f"/application/{application_id}").json()["report"]
    set_status(viewer, application_id, {"status": "interviewing"})
    assert viewer.get(f"/application/{application_id}").json()["report"] == report


@pytest.mark.parametrize("body", [{"status": "ghosted"}, {"status": "Applied"}, {"status": None}, {},
                                  {"company": "Acme"}])
def test_bad_status_rejected(viewer, body):
    application_id = record(viewer)
    r = set_status(viewer, application_id, body)
    assert r.status_code == 422 and r.json()["ok"] is False
    assert "status" in r.json()["message"] and "ghosted" not in r.text
    assert viewer.get(f"/application/{application_id}").json()["application"]["status"] == "verified"


@pytest.mark.parametrize("content, content_type", [
    (b"not json", "application/json"), (b"[]", "application/json"), (b'"applied"', "application/json"),
    (b"1", "application/json"), (b"null", "application/json"),
    (b'{"status": "applied"}', "text/plain"), (b'{"status": "applied"}', None),
])
def test_malformed_status_body(viewer, content, content_type):
    application_id = record(viewer)
    headers = {**SAME_ORIGIN, **({"Content-Type": content_type} if content_type else {})}
    r = viewer.patch(f"/viewer/application/{application_id}", content=content, headers=headers)
    assert r.status_code == 422 and r.json()["ok"] is False
    assert viewer.get(f"/application/{application_id}").json()["application"]["status"] == "verified"


def test_status_upper_case_id(viewer):
    application_id = record(viewer)
    r = set_status(viewer, application_id.upper(), {"status": "applied"})
    assert r.json()["application_id"] == application_id


@pytest.mark.parametrize("path_id", ["abc", "1", "0", "-1", UNKNOWN])
@pytest.mark.parametrize("body", [{"status": "applied"}, {"status": "ghosted"}])
def test_status_write_unknown_id(viewer, path_id, body):
    assert_error(set_status(viewer, path_id, body), 404, "Application not found")


def test_unknown_id_with_non_json_body(viewer):
    r = viewer.patch(f"/viewer/application/{UNKNOWN}", content=b"nope", headers=SAME_ORIGIN)
    assert_error(r, 404, "Application not found")


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_deleted_without_a_key(viewer, settings, monkeypatch, headers):
    application_id = record(viewer)
    generate(viewer, monkeypatch, application_id)
    letter = save_letter(settings, application_id)
    files = sorted(settings.output_dir.rglob("*.pdf"))
    r = delete(viewer, application_id, headers)
    assert (r.status_code, r.json()) == (200, {"ok": True, "application_id": application_id})
    assert_error(viewer.get(f"/application/{application_id}"), 404, "Application not found")
    assert application_id not in [a["id"] for a in viewer.get("/applications").json()["applications"]]
    assert sorted(settings.output_dir.rglob("*.pdf")) == files and letter.exists()  # files kept


def test_delete_twice(viewer):
    application_id = record(viewer)
    assert delete(viewer, application_id).status_code == 200
    assert_error(delete(viewer, application_id), 404, "Application not found")


def test_delete_ignores_a_body(viewer):
    application_id = record(viewer)
    r = viewer.request("DELETE", f"/viewer/application/{application_id.upper()}", content=b"junk",
                       headers=SAME_ORIGIN)
    assert r.json() == {"ok": True, "application_id": application_id}


@pytest.mark.parametrize("path_id", ["abc", "1", UNKNOWN])
def test_delete_unknown_id(viewer, path_id):
    assert_error(delete(viewer, path_id), 404, "Application not found")


def test_re_record_after_viewer_delete(viewer):
    application_id = record(viewer)
    delete(viewer, application_id)
    link = f"{GH_LINK}1"
    r = viewer.post("/application", json={**VALID_APPLICATION, "job_link": link, "official_apply_url": link},
                    headers=HEADERS)
    assert r.status_code == 201 and r.json()["application_id"] != application_id


@pytest.mark.parametrize("method", ["update", "delete", "exists"])
def test_writes_store_unavailable(viewer, monkeypatch, method):
    application_id = record(viewer)

    def broken(self, *args):
        raise ApplicationStoreError("OperationalError: unable to open database file")

    monkeypatch.setattr(ApplicationStore, method, broken)
    if method == "delete":
        r = delete(viewer, application_id)
    else:  # exists is only consulted for a bad body
        r = set_status(viewer, application_id, {"status": "ghosted" if method == "exists" else "applied"})
    assert_error(r, 503, "Application store unavailable")


@pytest.mark.parametrize("headers", [{"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
                                     {"Origin": "https://evil.example"}])
def test_cross_site_writes_refused(viewer, headers):
    application_id = record(viewer)
    assert_error(set_status(viewer, application_id, {"status": "applied"}, headers), 403, "Cross-site request refused")
    assert_error(delete(viewer, application_id, headers), 403, "Cross-site request refused")
    # Refused before the ID or body is looked at.
    assert_error(set_status(viewer, "abc", {"status": "ghosted"}, headers), 403, "Cross-site request refused")
    assert viewer.get(f"/application/{application_id}").json()["application"]["status"] == "verified"


def test_preflight_not_granted(viewer):
    r = viewer.options(f"/viewer/application/{UNKNOWN}", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "DELETE"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("headers", [{}, HEADERS])
def test_writes_not_served_without_docs(settings, storage, headers):
    public = TestClient(create_app(settings, storage))
    application_id = record(public)
    unknown = public.get("/no-such-path").json()
    r = public.patch(f"/viewer/application/{application_id}", json={"status": "applied"},
                     headers={**headers, **SAME_ORIGIN})
    assert (r.status_code, r.json()) == (404, unknown)
    r = public.delete(f"/viewer/application/{application_id}", headers={**headers, **SAME_ORIGIN})
    assert (r.status_code, r.json()) == (404, unknown)
    assert public.patch(f"/application/{application_id}", json={"status": "offer"}, headers=HEADERS).json()["status"] == "offer"


def test_keyed_endpoints_still_need_the_key(viewer):
    application_id = record(viewer)
    assert viewer.delete(f"/application/{application_id}", headers=SAME_ORIGIN).status_code == 401
    assert viewer.patch(f"/application/{application_id}", json={"status": "applied"}).status_code == 401
    assert viewer.get(f"/application/{application_id}").json()["application"]["status"] == "verified"


def test_writes_touch_only_the_store(viewer, settings, monkeypatch, base_pdf, base_letter):
    first, second = record(viewer, 1), record(viewer, 2)
    generate(viewer, monkeypatch, first)
    save_letter(settings, first)
    files = snapshot(settings)[2]
    monkeypatch.setattr("app.main.generate_output", lambda *a: pytest.fail("generation started"))
    set_status(viewer, first, {"status": "applied"})
    delete(viewer, second)
    delete(viewer, first)
    assert snapshot(settings)[2] == files and base_letter.read_bytes() == b"%PDF-base-letter"


def test_each_write_logged_once_without_content(viewer, caplog):
    application_id = record(viewer)
    caplog.set_level(logging.INFO, logger="app.requests")
    for send, method, status in [
        (lambda: set_status(viewer, application_id, {"status": "applied"}), "PATCH", 200),
        (lambda: set_status(viewer, application_id, {"status": "secret-ish-value"}), "PATCH", 422),
        (lambda: delete(viewer, application_id), "DELETE", 200),
    ]:
        caplog.clear()
        send()
        (line,) = request_lines(caplog)
        assert {k: v for k, v in line.items() if k != "duration_ms"} == {
            "event": "application_request", "method": method, "status": status, "application_id": application_id}
        assert "applied" not in caplog.text and "secret-ish-value" not in caplog.text


@pytest.mark.parametrize("send", [
    lambda c: set_status(c, "not-a-uuid", {"status": "applied"}),
    lambda c: delete(c, "not-a-uuid"),
    lambda c: delete(c, UNKNOWN, {"Sec-Fetch-Site": "cross-site"}),
])
def test_refused_writes_logged_without_the_path_id(viewer, caplog, send):
    caplog.set_level(logging.INFO, logger="app.requests")
    send(viewer)
    (line,) = request_lines(caplog)
    assert "application_id" not in line and line["status"] in (403, 404)
    assert "not-a-uuid" not in caplog.text and UNKNOWN not in caplog.text


# --- the page ---

def test_page_served_without_a_key_and_without_data(viewer, monkeypatch):
    application_id = record(viewer, full_job_description="secret posting words")
    generate(viewer, monkeypatch, application_id)
    r = viewer.get("/viewer")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    for text in (application_id, "secret posting words", "Acme Corp", API_KEY):
        assert text not in r.text
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"


def test_page_loads_nothing_from_another_origin(viewer):
    html = viewer.get("/viewer").text
    assert re.findall(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", html) == []
    assert "@import" not in html and "url(" not in html
    assert "innerHTML" not in html and "localStorage" not in html and "sessionStorage" not in html
    assert "document.cookie" not in html


def directives(policy: str) -> dict:
    return {part.split()[0]: part.split()[1:] for part in policy.split("; ")}


def test_policy_allows_only_its_own_script_and_style(viewer):
    r = viewer.get("/viewer")
    policy = directives(r.headers["content-security-policy"])
    nonce = re.search(r'<script nonce="([^"]+)"', r.text).group(1)
    assert policy["default-src"] == ["'none'"]
    assert policy["script-src"] == policy["style-src"] == [f"'nonce-{nonce}'"]
    assert policy["frame-src"] == ["blob:"] and policy["connect-src"] == ["'self'"]
    assert policy["frame-ancestors"] == ["'none'"]
    assert r.text.count(f'nonce="{nonce}"') == 2  # the one style block and the one script
    assert len(re.findall(r"<script", r.text)) == 1 and len(re.findall(r"<style", r.text)) == 1


def test_nonce_differs_per_response(viewer):
    first, second = (directives(viewer.get("/viewer").headers["content-security-policy"])["script-src"] for _ in range(2))
    assert first != second


def test_page_asks_for_no_key_and_stores_nothing(viewer):
    html = viewer.get("/viewer").text
    for text in ("X-API-Key", 'type="password"', "?key", "api_key=", "localStorage", "sessionStorage", "document.cookie"):
        assert text not in html, text


def test_page_switches_between_resume_and_cover_letter(viewer):
    html = viewer.get("/viewer").text
    assert '"Resume"' in html and '"Cover letter"' in html and '"aria-pressed": "true"' in html
    assert "/cover-letter/base.pdf" in html and '/cover-letter.pdf"' in html
    assert "No cover letter has been generated for this application yet." in html


def test_page_changes_status_and_deletes(viewer):
    html = viewer.get("/viewer").text
    assert '["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"]' in html
    assert '"/viewer/application/" + app.id, false, { method: "PATCH"' in html
    assert '"/viewer/application/" + app.id, false, { method: "DELETE" }' in html
    assert 'if (!confirm("Delete " + app.company + " – " + app.role + "? This cannot be undone.")) return;' in html
    assert '"Content-Type": "application/json"' in html and 'credentials: "omit"' in html


def test_page_has_no_inline_styles_or_handlers(viewer):
    html = viewer.get("/viewer").text
    assert re.search(r"<[^>]+\sstyle=", html) is None
    assert re.search(r"<[^>]+\son[a-z]+=", html) is None
