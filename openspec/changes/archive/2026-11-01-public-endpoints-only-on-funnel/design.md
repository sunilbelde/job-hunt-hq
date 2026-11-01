# Design

## Context

`app/serve.py` runs one uvicorn server on two loopback sockets. `by_local_port` sends each connection to one of two FastAPI apps, chosen by `scope["server"]`, the local port the connection arrived on:

- **Public app** (port 8080, published by Funnel): built with `api_docs_enabled=False`. It registers `/health`, `/healthz`, `POST`/`PATCH`/`DELETE /application`, `POST /resume`, `GET /resume/{id}/status`, `POST /cover-letter`, `GET /cover-letter/{id}/status`, plus a stub `GET /application/{id}` that returns 404 so the shared path doesn't answer 405.
- **Docs app** (port 8081): built with `api_docs_enabled=True`. It serves everything above, plus the docs, the viewer and its endpoints. Its 18 operations appear in `/openapi.json`.

Today `tailscale serve --https=8444` publishes port 8081 to the tailnet. The install and status scripts suggest that mapping and check it with `deploy/tailscale_docs.py`, which exits 0 for a tailnet-only mapping, 3 for a Funneled one, and 1 when there is none.

The viewer page (`app/viewer.py`) already calls `fetch(path)` with relative paths only, so it follows whatever origin it was loaded from.

The specs in this change define the required behavior. This document covers how to get there.

## Goals / Non-Goals

**Goals:**
- Make the public listener's surface one explicit allowlist that a test can enumerate.
- Keep the docs-port app and the development server byte-for-byte the same in behavior.
- Make the scripts treat any Tailscale mapping to 8081 as a misconfiguration.

**Non-Goals:**
- Adding auth to the viewer endpoints. They stay keyless, because loopback-only access is their guard.
- Renaming `DOCS_PORT`, `--docs-port` or `DOCS_URL`. The listener is now "local", but renaming would ripple through the plist, scripts and docs for no behavior gain.
- Adding rate limiting on the public address.
- Changing Funnel's own 443 mapping.

## Decisions

### 1. An ASGI allowlist in front of the public app, rather than conditional route registration

`serve.py` will wrap the public app in `public_only(app)`. For `http` scopes it passes a request through only when `(method, path)` is exactly one of:

- `("GET", "/health")`
- `("POST", "/application")`
- `("POST", "/resume")`
- `("POST", "/cover-letter")`

Any other request gets the same 404 response the app gives for an unknown path: `{"detail": "Not Found"}`, `application/json`. Non-http scopes, lifespan included, pass through unchanged.

- **Why:** the spec says every other path *and method* is handled as an unknown path. Conditional registration inside `create_app` would leave `GET /resume` or `PUT /application` answering 405, which reveals the path exists. It would also have to untangle the stacked `/health` and `/healthz` decorators and keep the `no_application_read` stub. An allowlist is four lines to audit, it does not depend on FastAPI routing, and it sits next to `by_local_port`, which already holds the port-based security decision.
- **Alternative considered:** a `public: bool` parameter on `create_app` that skips registering routes. It is cleaner in-process, since the handlers wouldn't exist, but it is harder to make 405-free and spreads the policy over ~10 `if` blocks. Rejected.
- **Alternative considered:** blocking paths in Tailscale. Funnel proxies by path prefix only, cannot filter by method, and lives outside the repo, so tests cannot check it. Rejected.
- Paths match exactly, with no trailing-slash normalization. FastAPI's `/health/` → `/health` redirect is not reproduced, so `/health/` returns 404.
- The public app is still built with `api_docs_enabled=False`, which gives a second layer for docs and viewer paths.

### 2. Blocked requests are not logged as API events

The wrapper answers before the app's `log_request` middleware runs, so a blocked `PATCH /application/<id>` writes no structured `application` line. Uvicorn's access log still records it, with query strings stripped by `log_filters`. This is acceptable: these are probes, not API traffic, and the access log keeps an audit trail.

### 3. Local listener always on; `DOCS_PORT=off` refused

Without port 8081, nothing could read job status or edit and delete applications. So:

- The install script refuses `off`.
- The `sed` branch that strips `--docs-port` from the plist goes away.
- `serve.py --docs-port` stays optional, for tests and dev use.
- The status script reports a plist with no `--docs-port` (an old `off` install) as `docs: not configured; reinstall` and exits non-zero.

### 4. Tailscale check inverted, not removed

`deploy/tailscale_docs.py` stays as it is, since it already finds any mapping that proxies a port. The scripts change how they read its exit codes:

| Exit code | Before | After |
|---|---|---|
| 1 (no mapping) | Warning | Fine. Status prints `local only` |
| 0 (tailnet mapping) | Fine | Warning, with `tailscale serve --https=<port> off`. The port is taken from the printed URL, default 443 |
| 3 (Funnel mapping) | Warning | Warning, with `tailscale funnel --https=<port> off`, then the serve-off command |

The uninstall script's `tailscale serve --https=8444 off` reminder is dropped. Install and status already flag a leftover mapping.

### 5. Smoke test uses both URLs, with zero-UUID probes

- On the public `<base_url>`: the existing 404 checks, plus 404 checks for `GET /healthz`, both status paths and keyed `PATCH`/`DELETE /application/00000000-0000-0000-0000-000000000000`. The all-zero UUID means a broken deployment that still serves `DELETE` can't remove a real row.
- Also on the public URL: `POST /application`, `POST /resume` and `POST /cover-letter`. This is the Muse path.
- On `DOCS_URL`: the status polling, the `PATCH` that clears leftover posting text, and the cleanup `DELETE`.
- `DOCS_URL=off` exits 2 with usage.

### 6. Docs text

- `DESCRIPTION` in `app/main.py` gains a short paragraph: the four public operations, with everything else local-only on the Mac.
- The status endpoints' description drops "served on the public address too".
- The `viewer_writes` text drops "tailnet docs listener".
- `app/viewer.py`'s module docstring and any page copy drop the tailnet wording.
- The operation count stays 18, because the docs-port schema is unchanged.

## Risks / Trade-offs

- [Muse or another tool polls a status endpoint or uses `/healthz`.] → The owner confirmed only the four endpoints are used. If something breaks, the remedy is adding a pair to the allowlist. Mention this in the README.
- [The owner can no longer open the viewer from a phone or laptop.] → This is intended. To get it back, re-add a `tailscale serve` mapping, which the scripts will warn about, or revert this change.
- [A leftover `:8444` mapping keeps the docs on the tailnet after reinstall.] → Install and status warn and print the removal command. The migration plan below includes running it.
- [The allowlist and the app's real routes drift, for example a route renamed in `main.py`.] → `tests/test_serve.py` asserts that each allowed pair reaches the app (not 404) and that every other operation in the docs app's OpenAPI document gets 404 on the public port, so a rename fails a test.
- [The 404 body differs from Starlette's unknown-path 404.] → A test compares the public 404 for a blocked path with the app's own 404 for a random path: status, body and content type.

## Migration Plan

1. Archive `viewer-fill-form` first, since this change's specs assume its 18 operations. Then merge this change through a PR.
2. On the Mac mini, run `scripts/install_service.sh`. It will warn about the existing `:8444` mapping.
3. Run `tailscale serve --https=8444 off`, then `scripts/service_status.sh` to confirm `docs: … local only` with no warning.
4. Run `API_KEY=… scripts/smoke_test.sh https://<machine>.<tailnet>.ts.net`.
5. Rollback: revert the merge, reinstall, and re-run `tailscale serve --bg --https=8444 http://127.0.0.1:8081`.

After archiving, update the `Purpose` lines of `openspec/specs/resume-viewer/spec.md` ("served only on the owner's tailnet") and `openspec/specs/generation-jobs/spec.md` ("poll the public status endpoints"). Delta specs cannot change a Purpose.
