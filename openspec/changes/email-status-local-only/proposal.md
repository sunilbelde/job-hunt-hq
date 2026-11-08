# Proposal

## Why

PR #27 put `POST /application/email-status` on the public Funnel allowlist because we assumed the job-email workflow was an n8n instance off the Mac. The caller is actually Hermes, which runs locally on this Mac mini, so it can call `http://127.0.0.1:8081/application/email-status`. Publishing the endpoint gives the internet one more keyed write path that nothing needs, so it should go back to being local-only like the other non-Muse endpoints.

## What Changes

- Remove `("POST", "/application/email-status")` from `PUBLIC_ROUTES` in `app/serve.py`. The public listener (the one Funnel publishes) goes back to serving only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter`; `POST /application/email-status` on it gets the same unknown-path 404 as every other local-only endpoint, with or without a key. **BREAKING** for any caller still using the public URL; Hermes switches to the local URL.
- Keep the endpoint unchanged on the local listener (`127.0.0.1:8081`) and on the development server: same API-key check, body, matching, status mapping and responses.
- OpenAPI docs: the top-level description names four public operations again, and the email status operation's description says it is served only on the local listener and names a local workflow such as Hermes instead of n8n. Still twenty-two documented operations.
- Tests: `tests/test_serve.py` expects the four-endpoint allowlist and a 404 for the email status endpoint on the public port (it is now covered by the "every other operation is 404" test); the local-port email status check stays. `tests/test_docs.py` expects four public operations and the local-only wording.
- Smoke test: `POST /application/email-status` joins the public 404 probes (eight local-only probes instead of seven), and the `Applied`/no-such-company `no_match` probe moves to the local listener. The operation count stays twenty-two. Wording goes from "five endpoints" to "four".
- Install script: "five endpoints" wording becomes "four" (no new probe).
- README: replace the n8n wording with the local Hermes workflow, use `http://127.0.0.1:8081/application/email-status` in the example, and say four public endpoints everywhere.
- Main specs updated through delta specs (`local-service-hosting`, `api-docs`). The `email-status-updates` Purpose sentence, which names n8n, is edited directly in the main spec at sync time (a Purpose isn't a delta).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-service-hosting`: the public address and public listener serve only the original four endpoints; the email status endpoint answers 404 there; the smoke test probes it as local-only and checks `no_match` on the local listener.
- `api-docs`: the reference names four public operations, and the email status operation is described as local-only.

## Impact

- Code: `app/serve.py` (allowlist and docstring), `app/main.py` (service description, email status description and comment), `app/models.py` (comment naming n8n).
- Tests: `tests/test_serve.py`, `tests/test_docs.py`, `tests/test_email_status.py` (test name mentioning n8n), `scripts/smoke_test.sh`, `scripts/test_smoke_test.sh`, `scripts/install_service.sh`, `scripts/test_install_service.sh`.
- Docs: `README.md`, `openspec/specs/*` via the delta specs.
- Operations: Hermes must be configured with `http://127.0.0.1:8081/application/email-status`. Funnel itself needs no change: it still publishes port 8080, which now passes four routes.
