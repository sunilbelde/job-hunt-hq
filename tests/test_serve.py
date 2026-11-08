import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import serve
from app.applications import ApplicationStore
from app.main import create_app
from app.serve import PUBLIC_ROUTES, by_local_port, parse_args, public_only
from tests.conftest import API_KEY, VALID_APPLICATION

HEADERS = {"X-API-Key": API_KEY}
PUBLIC, DOCS = 8080, 8081
DOCS_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]
ZERO = "00000000-0000-0000-0000-000000000000"
REPO = Path(__file__).resolve().parent.parent


# --- dispatcher ---

def recorder(name, seen):
    async def app(scope, receive, send):
        seen.append(name)
    return app


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ({"type": "http", "server": ("127.0.0.1", DOCS)}, "docs"),
        ({"type": "websocket", "server": ("127.0.0.1", DOCS)}, "docs"),
        ({"type": "http", "server": ("127.0.0.1", PUBLIC)}, "public"),
        ({"type": "http", "server": ("127.0.0.1", 9999)}, "public"),
        ({"type": "http", "server": None}, "public"),
        ({"type": "http"}, "public"),
        ({"type": "lifespan"}, "public"),
    ],
)
def test_dispatch_by_local_port(scope, expected):
    seen = []
    app = by_local_port(recorder("public", seen), {DOCS: recorder("docs", seen)})
    asyncio.run(app(scope, None, None))
    assert seen == [expected]


@pytest.fixture
def apps(settings, storage):
    store = ApplicationStore(settings.output_dir / "applications.sqlite3")
    public = public_only(create_app(settings.model_copy(update={"api_docs_enabled": False}), storage, store))
    docs = create_app(settings.model_copy(update={"api_docs_enabled": True}), storage, store)
    return by_local_port(public, {DOCS: docs})


def client_on(app, port):
    # TestClient builds scope["server"] from the URL, as uvicorn does from the socket.
    return TestClient(app, base_url=f"http://127.0.0.1:{port}")


@pytest.mark.parametrize("path", DOCS_PATHS)
def test_docs_only_on_docs_port(apps, path):
    assert client_on(apps, PUBLIC).get(path).status_code == 404
    assert client_on(apps, DOCS).get(path).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": f"127.0.0.1:{DOCS}"},
        {"X-Forwarded-Port": str(DOCS), "X-Forwarded-Host": f"127.0.0.1:{DOCS}", "X-Forwarded-For": "100.64.0.1"},
        {"Tailscale-User-Login": "owner@example.com", "Tailscale-Funnel-Request": "?0"},
    ],
)
def test_forged_headers_do_not_reach_docs(apps, headers):
    assert client_on(apps, PUBLIC).get("/docs", headers=headers).status_code == 404


def test_api_same_on_both_ports(apps):
    public, docs = client_on(apps, PUBLIC), client_on(apps, DOCS)
    for client in (public, docs):
        r = client.post("/application", json=VALID_APPLICATION)
        assert r.status_code == 401 and r.json() == {"ok": False, "message": "Invalid or missing API key"}
    first = docs.post("/application", json=VALID_APPLICATION, headers=HEADERS)
    again = public.post("/application", json=VALID_APPLICATION, headers=HEADERS)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["application_id"] == again.json()["application_id"]


# --- the public allowlist ---

def test_public_routes_are_the_five_funnel_endpoints():
    assert PUBLIC_ROUTES == {("GET", "/health"), ("POST", "/application"), ("POST", "/application/email-status"),
                             ("POST", "/resume"), ("POST", "/cover-letter")}


def test_email_status_updates_through_the_public_port(apps):
    recorded = client_on(apps, PUBLIC).post("/application", json=VALID_APPLICATION, headers=HEADERS)
    email = {"company": VALID_APPLICATION["company"], "role": VALID_APPLICATION["role"], "status": "Rejected"}
    r = client_on(apps, PUBLIC).post("/application/email-status", json=email, headers=HEADERS)
    assert r.status_code == 200 and r.json()["application_id"] == recorded.json()["application_id"]
    assert r.json()["status"] == "rejected"
    assert client_on(apps, PUBLIC).post("/application/email-status", json=email).status_code == 401


@pytest.mark.parametrize(("method", "path"), sorted(PUBLIC_ROUTES))
def test_public_routes_reach_the_app(apps, method, path):
    # Without a key the POSTs answer the app's own 401, which proves the request got past the allowlist.
    r = client_on(apps, PUBLIC).request(method, path)
    assert r.status_code == (200 if method == "GET" else 401)


@pytest.fixture
def finished(settings, storage):
    """Both ports over one store, with an application whose resume job has finished."""
    pending = []
    store = ApplicationStore(settings.output_dir / "applications.sqlite3")
    public = public_only(create_app(settings.model_copy(update={"api_docs_enabled": False}), storage, store, pending.append))
    docs = create_app(settings.model_copy(update={"api_docs_enabled": True}), storage, store, pending.append)
    app = by_local_port(public, {DOCS: docs})
    application_id = client_on(app, DOCS).post("/application", json=VALID_APPLICATION, headers=HEADERS).json()["application_id"]
    client_on(app, DOCS).post("/resume", json={"application_id": application_id}, headers=HEADERS)
    pending.pop()()
    return app, application_id


def docs_operations(app):
    schema = client_on(app, DOCS).get("/openapi.json").json()
    return [(method.upper(), path) for path, ops in schema["paths"].items() for method in ops]


def test_every_other_operation_is_404_on_the_public_port(finished):
    app, application_id = finished
    before = client_on(app, DOCS).get(f"/application/{application_id}").json()
    blocked = [op for op in docs_operations(app) if op not in PUBLIC_ROUTES] + [("GET", "/healthz")]
    assert ("GET", "/resume/{application_id}/status") in blocked and ("DELETE", "/application/{application_id}") in blocked
    assert ("GET", "/applications") in blocked and ("PATCH", "/application/{application_id}") in blocked
    public = client_on(app, PUBLIC)
    for method, template in blocked:
        path = template.replace("{application_id}", application_id)
        for headers in ({}, HEADERS):
            body = {"status": "applied"} if method in ("PATCH", "POST") else None
            r = public.request(method, path, headers=headers, json=body)
            assert (r.status_code, r.json()) == (404, {"detail": "Not Found"}), (method, path, headers)
    assert client_on(app, DOCS).get(f"/application/{application_id}").json() == before
    job = client_on(app, DOCS).get(f"/resume/{application_id}/status", headers=HEADERS)
    assert job.status_code == 200 and job.json()["status"] == "done"


@pytest.mark.parametrize(("method", "path"), [("GET", "/resume"), ("PUT", "/application"), ("GET", "/health/"),
                                              ("HEAD", "/health"), ("OPTIONS", "/resume"),
                                              ("GET", "/application/email-status"),
                                              ("PATCH", "/application/email-status"),
                                              ("DELETE", "/application/email-status"),
                                              ("POST", "/application/email-status/")])
def test_other_methods_on_public_paths_are_404_not_405(apps, method, path):
    assert client_on(apps, PUBLIC).request(method, path).status_code == 404


def test_blocked_404_matches_the_apps_unknown_path_404(apps):
    blocked = client_on(apps, PUBLIC).get(f"/resume/{ZERO}/status", headers=HEADERS)
    unknown = client_on(apps, DOCS).get("/no-such-path")
    assert (blocked.status_code, blocked.content, blocked.headers["content-type"]) == (
        unknown.status_code, unknown.content, unknown.headers["content-type"])


def test_status_404_on_public_port_without_a_key(apps):
    assert client_on(apps, PUBLIC).get(f"/resume/{ZERO}/status").status_code == 404


def test_one_resume_run_across_both_ports(settings, storage):
    pending = []
    store = ApplicationStore(settings.output_dir / "applications.sqlite3")
    public = public_only(create_app(settings.model_copy(update={"api_docs_enabled": False}), storage, store, pending.append))
    docs = create_app(settings.model_copy(update={"api_docs_enabled": True}), storage, store, pending.append)
    app = by_local_port(public, {DOCS: docs})
    application_id = client_on(app, PUBLIC).post("/application", json=VALID_APPLICATION, headers=HEADERS).json()["application_id"]
    first = client_on(app, PUBLIC).post("/resume", json={"application_id": application_id}, headers=HEADERS)
    second = client_on(app, DOCS).post("/resume", json={"application_id": application_id}, headers=HEADERS)
    assert (first.status_code, second.status_code) == (202, 202) and first.json() == second.json()
    assert len(pending) == 1
    pending[0]()
    # Status is read on the local listener only: the public port no longer serves it.
    job = client_on(app, DOCS).get(f"/resume/{application_id}/status", headers=HEADERS).json()
    assert job["status"] == "done"
    assert client_on(app, PUBLIC).get(f"/resume/{application_id}/status", headers=HEADERS).status_code == 404


def test_launcher_fails_interrupted_jobs_before_serving(settings, monkeypatch):
    store = ApplicationStore(settings.output_dir / "applications.sqlite3")
    application_id, _ = store.record({**VALID_APPLICATION})
    store.start_job(application_id, "resume", "2026-10-28T10:00:00Z")
    seen = {}

    class Server:
        def __init__(self, config):
            pass

        def run(self, sockets):
            seen["job"] = store.get_job(application_id, "resume")

    monkeypatch.setattr("app.serve.get_settings", lambda: settings)
    monkeypatch.setattr("app.serve.bind", lambda host, port: None)
    monkeypatch.setattr("app.serve.uvicorn.Server", Server)
    serve.main(["--port", str(PUBLIC), "--docs-port", str(DOCS)])
    assert (seen["job"]["status"], seen["job"]["error"]) == ("failed", "Interrupted by a service restart")


# --- arguments ---

@pytest.mark.parametrize(
    "argv",
    [
        ["--port", "8080", "--docs-port", "8080"],
        ["--port", "8080", "--host", "0.0.0.0"],
        ["--port", "8080", "--host", "192.168.1.5"],
        ["--port", "8080", "--host", "localhost"],
        [],
    ],
)
def test_bad_arguments_refused(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(argv)
    assert exc.value.code == 2


def test_docs_port_optional():
    args = parse_args(["--port", "8080"])
    assert args.docs_port is None and args.host == "127.0.0.1"


# --- the real launcher ---

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_launcher_serves_both_ports(tmp_path):
    public, docs = free_port(), free_port()
    env = {**os.environ, "API_KEY": API_KEY, "OUTPUT_DIR": str(tmp_path / "out"), "API_DOCS_ENABLED": "true"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.serve", "--port", str(public), "--docs-port", str(docs)],
        cwd=tmp_path, env={**env, "PYTHONPATH": str(REPO)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        base, docs_base = f"http://127.0.0.1:{public}", f"http://127.0.0.1:{docs}"
        for _ in range(100):
            try:
                if httpx.get(f"{base}/health").status_code == 200 and httpx.get(f"{docs_base}/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("launcher did not answer /health on both ports")

        # API_DOCS_ENABLED=true in the environment still leaves the public port without docs.
        for path in ("/docs", "/openapi.json"):
            assert httpx.get(base + path).status_code == 404
            assert httpx.get(docs_base + path).status_code == 200
        # Only the five Funnel endpoints are on the public port; the rest are served on the local one.
        for path in ("/healthz", f"/resume/{ZERO}/status"):
            assert httpx.get(base + path, headers=HEADERS).status_code == 404
        assert httpx.get(docs_base + "/healthz").status_code == 200
        assert httpx.get(f"{docs_base}/resume/{ZERO}/status", headers=HEADERS).status_code == 404
        assert httpx.get(f"{docs_base}/resume/{ZERO}/status").status_code == 401
        first = httpx.post(f"{docs_base}/application", json=VALID_APPLICATION, headers=HEADERS)
        again = httpx.post(f"{base}/application", json=VALID_APPLICATION, headers=HEADERS)
        assert first.status_code == 201 and again.status_code == 200
        assert first.json()["application_id"] == again.json()["application_id"]
    finally:
        proc.terminate()
        output, _ = proc.communicate(timeout=10)

    lines = [json.loads(line) for line in output.splitlines() if line.startswith('{"event"')]
    # Blocked public requests never reach the app, so only the two docs-port status reads are logged.
    assert [(line["event"], line["status"]) for line in lines if line["event"] != "application_request"] == [
        ("resume_request", 404), ("resume_request", 401)]
    assert [(line["status"], line["duplicate"]) for line in lines if line["event"] == "application_request"] == [
        (201, False), (200, True)]
    assert API_KEY not in output
