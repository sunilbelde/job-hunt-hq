# Design

## Context

The installed service runs two loopback listeners from `app/serve.py`: port 8080, wrapped in `public_only()` and published by Funnel, and port 8081, the full API plus docs and viewer. `public_only()` passes a request on only when `(method, path)` is in `PUBLIC_ROUTES`; anything else gets the same 404 body an unknown path gets. PR #27 added `("POST", "/application/email-status")` to that set. The endpoint itself lives in `app/main.py` and is registered on every app, so it is already served on 8081 and on the development server.

## Goals / Non-Goals

**Goals:**
- Public listener allowlist back to exactly the four pre-#27 routes.
- The smoke test still proves the email status endpoint works on the installed service, now on the local listener.

**Non-Goals:**
- Any change to the endpoint's auth, body, matching, mapping, locking or responses.
- Changing how `public_only()` or `by_local_port()` work, or the Funnel/Tailscale setup.
- Configuring Hermes itself; that lives outside this repo.
- Editing archived change folders under `openspec/changes/archive/`.

## Decisions

- **Remove one entry from `PUBLIC_ROUTES`, nothing else in the launcher.** The existing "every other documented operation is 404 on the public port" test in `tests/test_serve.py` derives its list from the OpenAPI document minus `PUBLIC_ROUTES`, so it automatically covers the email status endpoint (with and without a key) once the entry is gone. The dedicated "updates through the public port" test is rewritten to run on the docs port (8081) instead, so the local path keeps an end-to-end serve test. The "other methods on public paths are 404 not 405" cases for `/application/email-status` stay; they still hold.
- **Smoke test: add the endpoint to the existing public 404 probe loop, move the `no_match` probe to `DOCS_URL`.** The loop already sends a keyed request with body `{}`; a service that wrongly published the endpoint would answer 422 to that, which fails the probe without writing anything. Running the `Applied`/no-such-company probe against the local listener keeps the guarantee that the installed endpoint is reachable and matches, and an `Applied` email never writes. Alternative considered: drop the `no_match` probe entirely — rejected because it would leave the smoke test with no check that Hermes' URL works. The stub in `scripts/test_smoke_test.sh` therefore logs the public email path as a `PROBE` (count 7 → 8) and handles the email probe on the `http://d` docs host; the ordering test (email probe before `CREATE`) stays.
- **Operation count stays twenty-two.** The endpoint is still documented on the docs listener; only where it is served changes. No change to the "Smoke test checks the docs listener" requirement.
- **Install script: wording only.** Its public-port probes are `GET`s, which were already 404 on `/application/email-status`; adding a `POST` probe there would duplicate the smoke test. Only "five endpoints" becomes "four" in comments and the `die` message, and `scripts/test_install_service.sh` greps the new message.
- **Spec scenario names are kept.** OpenSpec rejects a MODIFIED block that drops a scenario, and rejects REMOVED plus ADDED of the same requirement. So in `local-service-hosting` the scenarios "n8n updates a status" and "Email status without API key" keep their names and now say the public address answers 404. `email-status-updates` gets no delta: its behavior is unchanged, and its "n8n summary accepted" scenario keeps its name. Its Purpose sentence, which a delta can't change, is edited directly in the main spec at sync time to name the local Hermes workflow.
- **n8n mentions in code comments and test names** (`app/models.py`, `app/main.py`, `tests/test_email_status.py`) are renamed to the local email workflow so `grep -i n8n` over the live tree (archive excluded) is empty.

## Risks / Trade-offs

- [Hermes or another caller still configured with the public URL gets 404] → README states the local URL; the owner confirms Hermes' HTTP node uses `http://127.0.0.1:8081/application/email-status` before deploying.
- [Port 8081 needs no Tailscale exposure for this] → unchanged: the install/status scripts already warn if 8081 is mapped.

## Migration Plan

1. Merge and reinstall (`scripts/install_service.sh`), which restarts the daemon with the new allowlist.
2. Point Hermes at `http://127.0.0.1:8081/application/email-status` with the same `X-API-Key`.
3. Run `scripts/smoke_test.sh`; it now fails if the public address serves the endpoint and checks `no_match` locally.

Rollback: re-add the tuple to `PUBLIC_ROUTES` and reinstall.
