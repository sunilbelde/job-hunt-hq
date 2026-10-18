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

from app.main import create_app
from app.serve import by_local_port, parse_args
from tests.conftest import API_KEY, VALID_APPLICATION

HEADERS = {"X-API-Key": API_KEY}
PUBLIC, DOCS = 8080, 8081
DOCS_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]
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
    public = create_app(settings.model_copy(update={"api_docs_enabled": False}), storage)
    docs = create_app(settings.model_copy(update={"api_docs_enabled": True}), storage)
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
        first = httpx.post(f"{docs_base}/application", json=VALID_APPLICATION, headers=HEADERS)
        again = httpx.post(f"{base}/application", json=VALID_APPLICATION, headers=HEADERS)
        assert first.status_code == 201 and again.status_code == 200
        assert first.json()["application_id"] == again.json()["application_id"]
    finally:
        proc.terminate()
        output, _ = proc.communicate(timeout=10)

    lines = [json.loads(line) for line in output.splitlines() if line.startswith('{"event"')]
    assert [(line["event"], line["status"], line["duplicate"]) for line in lines] == [
        ("application_request", 201, False),
        ("application_request", 200, True),
    ]
    assert API_KEY not in output
