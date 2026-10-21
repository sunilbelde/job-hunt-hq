# Design

## Context

- launchd runs `uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080 --log-config deploy/logging.json` with `API_DOCS_ENABLED=false` pinned in the plist.
- `tailscale serve status --json` on the Mac mini today shows one mapping, `sunils-mac-mini.tailf96439.ts.net:443 → http://127.0.0.1:8080`, with `AllowFunnel` set for `:443`. Funnel is enabled per `host:port` and only accepts ports 443, 8443 and 10000.
- `create_app()` takes `settings`, `storage` and `applications`, so two app instances can share one store and one storage object. Docs routes exist only when `settings.api_docs_enabled` is true (FastAPI registers nothing otherwise).
- In uvicorn 0.54, `Server.serve(sockets=[...])` accepts several pre-bound sockets. `scope["server"]` is the socket's local `(host, port)`. `ProxyHeadersMiddleware` rewrites only `client` and `scheme`, never `server`, so no request header can change it.
- Current Swagger page: `swagger-ui-dist@5` (resolves to 5.33.3 today) from jsDelivr. `/health` is listed before `/healthz` because the `/health` decorator is applied first.

See proposal.md for the motivation and the options compared.

## Goals / Non-Goals

**Goals:**
- Docs (and Try it out) on a loopback port that only the tailnet reaches. The public port stays byte-for-byte as it is now.
- Routing that fails closed and does not trust anything the client sends.
- One process, one store, one log file, one launchd job.

**Non-Goals:**
- No per-user auth on the docs beyond tailnet membership (proposal Open Question 7).
- No change to `create_app()`'s behaviour for local development: `API_DOCS_ENABLED=true uvicorn ...` still serves docs on its single port.
- No new settings field: the docs port is a launcher argument that the install script renders into the plist.

## Decisions

### 1. Launcher `app/serve.py` with two sockets and a port dispatcher
`python -m app.serve --host 127.0.0.1 --port 8080 [--docs-port 8081] --log-config <path>`:
1. `settings = get_settings()`, one `LocalStorage` and one `ApplicationStore`.
2. `public = create_app(settings.model_copy(update={"api_docs_enabled": False}), storage, applications)`. It is forced off in code, so the plist pin is a second guard and not the only one.
3. If `--docs-port` is given: `docs = create_app(settings.model_copy(update={"api_docs_enabled": True}), storage, applications)`.
4. `app = by_local_port(public, {docs_port: docs})`: an ASGI callable that sends `http` and `websocket` scopes to `docs` only when `scope["server"][1] == docs_port`, and everything else to `public`. Lifespan goes to `public`, because neither app has lifespan handlers. Lifespan is forwarded only to keep uvicorn's startup protocol satisfied.
5. Bind both sockets (`SO_REUSEADDR`, loopback only) and run `uvicorn.Server(uvicorn.Config(app, log_config=..., proxy_headers=True, forwarded_allow_ips="127.0.0.1")).serve(sockets=[...])`. These are the same defaults the CLI used.

`--docs-port` equal to `--port` exits with an error. `--host` other than a loopback address is refused, as a guard for the "Loopback-only listener" requirement.

*Alternatives:*
- Two `uvicorn.Server`s in one loop: each installs signal handlers, which conflict in uvicorn's `capture_signals`.
- A second launchd job: two writers on SQLite (it has a 5 s busy timeout, so it would work), but double install, status, uninstall and logging work.
- Choosing by `Host` header: the client controls it.

`rename_legacy_folders` runs inside each `create_app()` call. The second call is a no-op because renamed folders no longer match the legacy pattern. This is accepted rather than refactoring `create_app()`.

### 2. Tailnet publication on HTTPS 8444
`tailscale serve --bg --https=8444 http://127.0.0.1:8081` adds a `:8444` web handler without `AllowFunnel`. It cannot be funnelled even by mistake, because Funnel rejects 8444. URLs:
- Mac mini: `http://127.0.0.1:8081/docs`
- Tailnet: `https://sunils-mac-mini.tailf96439.ts.net:8444/docs` (README uses `<machine>.<tailnet>.ts.net`)

Same origin, so Try it out needs no CORS and FastAPI's relative `/openapi.json` URL works behind serve.

### 3. Install, status, uninstall
- `install_service.sh`: `docs_port=${DOCS_PORT:-8081}`; `off` disables it. It refuses `docs_port == port` before any sudo. The template carries `<string>--docs-port</string>` and `<string>__DOCS_PORT__</string>` on two lines; when docs are off the script deletes those two lines with `sed` before rendering, so `render_template.py` stays unchanged.
- After `/health` answers: `curl` `127.0.0.1:$port/docs` must be 404 (otherwise die), and `127.0.0.1:$docs_port/docs` must be 200 (otherwise die, with the log path).
- Tailscale checks, using `tailscale serve status --json` parsed with the venv's Python: warn if no handler proxies `127.0.0.1:$docs_port`; warn loudly if that handler's `host:port` is in `AllowFunnel`. Then print both docs URLs (the tailnet one is built from the serve status hostname and port when found).
- `service_status.sh`: a `docs:` line (ok, FAILING or off). The docs port comes from the installed plist (`plutil -extract ProgramArguments`), so status matches what is installed. It also prints the same Funnel warning.
- `uninstall_service.sh`: prints `tailscale serve --https=8444 off` as a reminder. It does not run it.

### 4. Smoke test
`DOCS_URL` env (default `http://127.0.0.1:8081`; `off` skips). Before creating anything: the public `/docs` and `/openapi.json` must be 404 (existing check), `$DOCS_URL/docs` must be 200, and `$DOCS_URL/openapi.json` must be 200 with exactly the six operations (counted with `python3 -c`). The stubbed curl in `test_smoke_test.sh` is extended to answer by host (`http://x` public, `http://d` docs).

### 5. Pinned Swagger UI
Create the app with `docs_url=None` and register a custom `GET /docs` (only when docs are enabled, `include_in_schema=False`). It returns `get_swagger_ui_html(...)` with `swagger_js_url`/`swagger_css_url` pinned to `swagger-ui-dist@5.33.3`, the same `swagger_ui_parameters` (`persistAuthorization: False`), and the oauth2 redirect route kept as FastAPI registers it. FastAPI's helper has no `integrity` argument, so the returned HTML gets `integrity="sha384-..." crossorigin="anonymous"` added to the two tags (hashes computed once and kept as constants next to the URLs, with a comment on how to regenerate them). ReDoc gets the same treatment (`redoc@2.x.y` pinned). A test asserts that no asset URL on either page contains `@5/` or `@next`, and that both tags carry `integrity=`.

*Alternative:* vendor the files and serve them as static files. This gives no CDN dependency, but adds ~1.5 MB to the repo plus a static route on the docs app (proposal Open Question 6).

### 6. Health order
Swap the two decorators on `healthz()` so `/healthz` is registered first. Handler, responses and descriptions are unchanged.

### 7. Logging
No middleware change. Both apps share the `app.requests` logger and its one handler. A request on either port runs through exactly one app's middleware, so it gets one line. Docs paths stay unlogged. uvicorn's access log already writes the local port nowhere, so the two listeners look the same in logs (proposal Open Question 5).

### 8. Tests
- `tests/test_serve.py`: the dispatcher sends a scope with `server=("127.0.0.1", docs_port)` to the docs app, and any other port, a missing `server`, and lifespan to the public app. Forged `host`/`x-forwarded-*`/`tailscale-*` headers on the public port still give 404 for `/docs`. Equal ports and a non-loopback host are refused. An integration test starts `python -m app.serve` on two ephemeral ports with a temp `OUTPUT_DIR`, then checks `/docs` (404 public, 200 docs), `/health` on both, an application recorded on the docs port being visible (as a 200 duplicate) on the public port, and one log line per API request.
- `tests/test_docs.py`: pinned assets with integrity, `/healthz` before `/health`. The existing `client` fixture already parametrizes docs on and off, so API behaviour stays covered.
- `scripts/test_install_service.sh`: the plist's `ProgramArguments` runs `-m app.serve` with `--docs-port 8081`; `API_DOCS_ENABLED` is still `false`; `DOCS_PORT=9090` is rendered; `DOCS_PORT=off` leaves no `--docs-port`; `DOCS_PORT=$PORT` is refused with no sudo; the curl stub answers `/docs` per port (a public 200 fails the install); the tailscale stub returns JSON with and without the docs handler and with `AllowFunnel` on it, checking the warnings; the docs URL is printed.
- `scripts/test_smoke_test.sh`: docs listener 200 passes; docs listener 404, or a wrong operation count, fails before any POST; `DOCS_URL=off` skips.

## Risks / Trade-offs

- [Custom launcher replaces the uvicorn CLI, so a uvicorn upgrade could change `serve(sockets=)`] → `requirements.txt` already caps uvicorn below 1; the integration test exercises the real launcher.
- [Anyone on the tailnet can open the docs] → It is the owner's tailnet. API calls still need the key. README shows the ACL snippet to restrict `:8444` if the tailnet is shared.
- [A future `tailscale serve`/`funnel` command could publish 8081 on a Funnel port] → The install and status scripts warn when any Funnel-enabled handler proxies the docs port. The public listener still never serves docs.
- [SRI hashes go stale if the pinned version is changed carelessly] → The page would refuse to load (fail closed). The comment next to the constants says how to recompute them.
- [Try it out writes real data on the installed service] → This was already true for dev. The page description already warns. README repeats it for the installed docs URL.

## Migration Plan

1. Merge, then `scripts/install_service.sh` (the new plist runs the launcher with `--docs-port 8081`).
2. `tailscale serve --bg --https=8444 http://127.0.0.1:8081`; `tailscale serve status` shows both mappings, and Funnel only on `:443`.
3. `API_KEY=... scripts/smoke_test.sh https://sunils-mac-mini.tailf96439.ts.net` passes, including the docs listener check.
4. Open `https://sunils-mac-mini.tailf96439.ts.net:8444/docs` from another tailnet device. From a device off the tailnet (phone on cellular with Tailscale off), confirm `https://…ts.net/docs` is 404 and `:8444` does not connect.
5. Rollback: `tailscale serve --https=8444 off`, then reinstall with `DOCS_PORT=off` (or revert the commit and reinstall).
