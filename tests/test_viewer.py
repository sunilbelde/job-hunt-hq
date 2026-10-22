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
from app.storage import RESUME_FILE_NAME, LocalStorage
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
READ_PATHS = ["/applications", f"/application/{UNKNOWN}", f"/application/{UNKNOWN}/resume.pdf", "/resume/base.pdf"]


@pytest.fixture
def viewer(settings):
    """The docs listener's app: viewer on, saving real files under OUTPUT_DIR."""
    return TestClient(create_app(settings.model_copy(update={"api_docs_enabled": True}), LocalStorage(settings.output_dir)))


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
    assert r.status_code == 201, r.text
    return r.json()


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
def test_reads_need_no_key(viewer, base_pdf, headers):
    record(viewer)
    assert viewer.get("/applications", headers=headers).status_code == 200
    assert viewer.get("/resume/base.pdf", headers=headers).content == b"%PDF-base"
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
    saved = generate(viewer, monkeypatch, application_id)["saved_path"]
    body = viewer.get(f"/application/{application_id}").json()
    assert body["ok"] is True
    application = body["application"]
    assert application["id"] == application_id and application["created_at"]
    links = ("job_link", "official_apply_url")
    assert {k: application[k] for k in VALID_APPLICATION if k not in links} == {
        k: v for k, v in VALID_APPLICATION.items() if k not in links}
    assert application["job_link"] == f"{GH_LINK}1"
    report = body["report"]
    assert (report["status"], report["saved_path"], report["added_terms"]) == ("tailored", saved, ["Airflow"])
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


def test_detail_store_unavailable(viewer, monkeypatch):
    application_id = record(viewer)

    def broken(self, application_id):
        raise ApplicationStoreError("OperationalError: unable to open database file")

    monkeypatch.setattr(ApplicationStore, "get_report", broken)
    for path in (f"/application/{application_id}", f"/application/{application_id}/resume.pdf"):
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


def test_reads_change_nothing(viewer, settings, monkeypatch, base_pdf):
    first, second = record(viewer, 1), record(viewer, 2)
    generate(viewer, monkeypatch, first)
    before = snapshot(settings)
    for path in ["/applications", "/resume/base.pdf", "/viewer",
                 *(p for i in (first, second) for p in (f"/application/{i}", f"/application/{i}/resume.pdf"))]:
        viewer.get(path)
    assert snapshot(settings) == before


def request_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records
            if r.name == "app.requests" and r.getMessage().startswith('{"event": "')
            and json.loads(r.getMessage())["event"] in ("application_request", "resume_request")]


def test_each_read_logged_once_without_content(viewer, monkeypatch, base_pdf, caplog):
    application_id = record(viewer, full_job_description="A posting about Kafka streaming platforms.")
    generate(viewer, monkeypatch, application_id)
    caplog.set_level(logging.INFO, logger="app.requests")
    caplog.clear()
    viewer.get("/viewer")
    assert request_lines(caplog) == []
    for path, event in [("/applications", "application_request"), (f"/application/{application_id}", "application_request"),
                        (f"/application/{application_id}/resume.pdf", "application_request"),
                        ("/resume/base.pdf", "resume_request")]:
        caplog.clear()
        viewer.get(path)
        (line,) = request_lines(caplog)
        expected = {"event": event, "status": 200}
        if event == "application_request":
            expected["method"] = "GET"
        if path.startswith("/application/"):
            expected["application_id"] = application_id
        assert {k: v for k, v in line.items() if k != "duration_ms"} == expected
    for text in ("Kafka", "Airflow", "Acme Corp", API_KEY, "Runs Kafka streaming"):
        assert text not in caplog.text


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
