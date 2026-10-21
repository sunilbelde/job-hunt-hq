# Proposal

## Why

The interactive API reference (`/docs`, Swagger UI) exists, but the installed service never serves it: its launchd job pins `API_DOCS_ENABLED=false` because the only listener is published to the internet through Tailscale Funnel, and Funnel delivers every request from `127.0.0.1`, so the app cannot tell the owner's requests from the public's. The owner wants to open the docs, and use Try it out, on the Mac mini and on their other tailnet devices, while the public Funnel address keeps answering 404.

## What Changes

- The installed service gets a **second loopback listener just for the docs** (default `127.0.0.1:8081`), in the same process as the public one (`127.0.0.1:8080`). Requests are routed by the local port they arrived on, not by headers or client address. The docs listener serves `/docs`, `/redoc`, `/openapi.json` and the full API, so Try it out works from the same origin. The public listener stays exactly as it is now, with no docs routes.
- Tailscale publishes the docs listener **to the tailnet only** with `tailscale serve --https=8444`. 8444 is not a port Funnel can expose (Funnel allows only 443, 8443 and 10000), so it cannot be made public by mistake. The owner opens:
  - on the Mac mini: `http://127.0.0.1:8081/docs`
  - on any tailnet device (and on the Mac mini): `https://<machine>.<tailnet>.ts.net:8444/docs`
- The launchd job starts a small launcher (`python -m app.serve`) instead of the `uvicorn` CLI, so one process can bind both sockets. `API_DOCS_ENABLED=false` stays pinned in the plist and still governs the public listener.
- The install script renders the docs port (`DOCS_PORT`, default 8081) into the plist, refuses a docs port equal to `PORT`, checks after start that `/docs` is 404 on the public port and 200 on the docs port, warns if `tailscale serve` is not proxying the docs port, and warns if the docs port's HTTPS port is Funnel-enabled. It prints the docs URLs.
- The status script reports the docs listener. The uninstall script output mentions turning off the `tailscale serve` mapping.
- The smoke test keeps checking that the public base URL answers 404 for `/docs` and `/openapi.json`, and also checks that the docs listener (`DOCS_URL`, default `http://127.0.0.1:8081`) answers 200 with the six documented operations.
- Swagger UI style gaps found during review are fixed: the page's script and stylesheet are pinned to an exact `swagger-ui-dist` version (today it loads the floating `@5` from jsDelivr), and `GET /healthz` is listed before its alias `GET /health`.
- README documents the docs URLs, the `tailscale serve` command, and why docs are tailnet-only.
- Unchanged: every API endpoint, request and response shape, error message, the `X-API-Key` check, the one-log-line-per-request convention, and the public Funnel address's behaviour (including 404 for docs).

## Current `/docs` page vs. the requested style

Checked by rendering the current app with docs enabled (FastAPI 0.146, Swagger UI from `swagger-ui-dist@5`):

| Expected | Current | Gap |
|---|---|---|
| Endpoints grouped by tag with tag descriptions | `health`, `applications`, `resumes` tags, each with a description, in that order | none |
| Summary next to each path | All six operations have summaries | none |
| Coloured method badges (GET blue, POST green, PATCH teal, DELETE red), expandable rows | Swagger UI default `BaseLayout`, collapsed operations under expanded tags | none |
| Try it out, Authorize with lock icons | `ApiKey` header scheme on the four protected operations; health ops show no lock | none |
| Stable assets | `swagger-ui-dist@5` (floating major) from jsDelivr; favicon from fastapi.tiangolo.com | **Floating version** on a page where the real API key will now be typed. Pinned in this change |
| Logical order | `GET /health` "Health check (alias)" shown before `GET /healthz` "Health check" (decorator order) | **Alias listed first**. Fixed in this change |
| Version badge | `0.1.0` (FastAPI default) | Cosmetic. Left as is (Open Question 6) |

## Options considered

1. **Separate docs listener, tailnet-only (chosen).** The decision is made by which socket the connection came in on. Clients cannot spoof that, and it does not depend on Tailscale header behaviour. Funnel cannot reach the docs port because no Funnel mapping points at it, and its HTTPS port (8444) is not one Funnel accepts. It fails closed: anything not on the docs socket goes to the docs-less app.
2. **Tell Funnel traffic apart by Tailscale headers** (`Tailscale-Funnel-Request`, `Tailscale-User-Login`). Rejected. It depends on undocumented-or-changing proxy behaviour and on serve stripping client-supplied copies. Tagged devices and direct `127.0.0.1` requests carry no identity header. A missed case exposes the schema to the internet.
3. **Protect `/docs` with the API key.** Rejected. A browser cannot send `X-API-Key` on navigation, so it would need Basic auth or a key in the URL (a second auth mechanism, or keys in history and logs). And the docs would still be reachable from the public address, which the owner explicitly does not want.
4. **A second launchd job running a docs-enabled copy of the service.** Workable, but it means two processes writing the same SQLite store and output folders, two jobs to install, monitor and uninstall, and two log streams. Option 1 gets the same isolation in one process.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-service-hosting`: the loopback-only listener requirement now covers two loopback ports; "Installed service serves no API docs" becomes "the public address serves no API docs, and the docs are served on a tailnet-only listener"; install, status and smoke-test scenarios cover the docs listener.
- `api-docs`: the reference page loads a pinned Swagger UI version, and lists `GET /healthz` before its alias.

## Open Questions

These were assumed so the plan could proceed. Each can be changed before apply.

1. **Ports.** Docs listener `127.0.0.1:8081`, tailnet HTTPS port `8444`. Any free loopback port works. The HTTPS port should stay outside 443, 8443 and 10000 so Funnel can never expose it.
2. **Docs listener on by default.** Assumed the install script always starts it. An opt-out (`DOCS_PORT=off`) is included. Say if you would rather it be opt-in.
3. **Tailscale serve setup is manual.** Assumed the install script only checks and prints the `tailscale serve --bg --https=8444 http://127.0.0.1:8081` command (as it already does for the main port) rather than running `tailscale` with sudo itself.
4. **Funnel on the docs port is a warning, not a failure.** Funnel config can change after install, so the install and status scripts warn. Making install refuse is easy if you prefer.
5. **Log lines do not say which listener served a request.** The one-line convention is unchanged, so a Try it out request looks the same as a Muse request in the logs. Adding a `listener` field would be a logging change. Left out.
6. **Pin rather than vendor Swagger UI.** Assumed pinning an exact `swagger-ui-dist` version on jsDelivr (with subresource integrity) is enough. Vendoring the files into the repo would remove the CDN dependency but adds ~1.5 MB. The `0.1.0` version badge is left as is.
7. **The tailnet can reach the docs without further auth.** Anyone on your tailnet (including shared-in users or tagged devices, if any) can open the docs. API calls from the page still need the key. If your tailnet has members other than you, a Tailscale ACL on port 8444 can narrow it. This is documented, not enforced.

## Impact

- Code: new `app/serve.py` (launcher and port-based dispatcher); `app/main.py` (pinned Swagger asset URLs through a custom docs route, health route order). No change to route handlers, models, middleware or settings fields.
- Deploy: `deploy/local.job-hunt-hq.plist.template` (`ProgramArguments` runs the launcher with `--docs-port __DOCS_PORT__`).
- Scripts: `install_service.sh`, `service_status.sh`, `uninstall_service.sh`, `smoke_test.sh`, and their tests `test_install_service.sh` and `test_smoke_test.sh`.
- Tests: new `tests/test_serve.py`; additions to `tests/test_docs.py`.
- Docs: README hosting and API reference sections.
- Operations: after merging, rerun `scripts/install_service.sh` and run `tailscale serve --bg --https=8444 http://127.0.0.1:8081` once. No new dependencies.
