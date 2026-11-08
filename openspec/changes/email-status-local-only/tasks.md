# Tasks

## 1. Public listener

- [x] 1.1 Remove `("POST", "/application/email-status")` from `PUBLIC_ROUTES` in `app/serve.py`, and change the module docstring ("the five endpoints") and the allowlist comment to the four Funnel endpoints. Leave `public_only()` and `by_local_port()` unchanged.
- [x] 1.2 In `tests/test_serve.py`: rename `test_public_routes_are_the_five_funnel_endpoints` to `..._four_...` and expect `{GET /health, POST /application, POST /resume, POST /cover-letter}`; rewrite `test_email_status_updates_through_the_public_port` as `test_email_status_updates_through_the_local_port` (record and update on `DOCS`, 200 → `rejected`, 401 without key) and add an assertion that the same keyed `Rejected` email on `PUBLIC` gets `(404, {"detail": "Not Found"})` and leaves the status unchanged. Confirm `test_every_other_operation_is_404_on_the_public_port` now includes `("POST", "/application/email-status")` in `blocked` (add it to the explicit asserts) and that the 404-not-405 cases still pass. Verify with `pytest tests/test_serve.py`.

## 2. API docs

- [x] 2.1 In `app/main.py`: the top-level description names only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter` as public; the email status operation's description names a local email workflow such as Hermes (no "n8n") and says it is served only on the local listener and that the public address answers 404; update the comment above the route (no longer published by the allowlist). Keep summary, body schema, example and responses unchanged.
- [x] 2.2 In `tests/test_docs.py`: drop `POST /application/email-status` from `PUBLIC_OPERATIONS` and assert it is not named among the public operations; in `test_email_status_mapping_described` replace the `"public address"` phrase with the local-only wording (`"only on the local listener"`, `"public address answers 404"`); add a test that no description contains "n8n" and the email status one mentions Hermes. Keep `test_documents_exactly_the_twenty_two_operations`. Verify with `pytest tests/test_docs.py`.
- [x] 2.3 Rename the n8n mentions in `app/models.py` (comment) and `tests/test_email_status.py` (`test_n8n_summary_accepted` → `test_email_workflow_summary_accepted`). Verify with `grep -rni n8n app tests scripts` returning nothing.

## 3. Scripts

- [x] 3.1 `scripts/smoke_test.sh`: update the header comment to four endpoints; add `"POST /application/email-status"` to the public 404 probe loop (keyed, body `{}`) and change its message to "serves only its four endpoints"; move the `Applied`/no-such-company probe from `$base` to `$docs` (the local listener), still requiring 404 with `reason` `no_match` and still running before any application is created; update its comment. Keep the twenty-two operation count.
- [x] 3.2 `scripts/test_smoke_test.sh`: route `http://x/application/email-status` to a `PROBE` line (404 by default, overridable with a new `STUB_PUBLIC_EMAIL`), handle the email probe on `http://d/application/email-status` (logged as `EMAIL`, `no_match` by default); expect eight `PROBE` lines instead of seven; update the email-probe assertion to the `http://d` URL; add a case where a public email status answer of 200 (or 422) fails before creating anything; keep the existing no_match failure cases pointing at the local probe. Verify with `bash scripts/test_smoke_test.sh`.
- [x] 3.3 `scripts/install_service.sh`: "five public endpoints"/"its five endpoints" → four in the header comment, the probe comment and the `die` message. Update the grep in `scripts/test_install_service.sh` to "serves only its four endpoints". Verify with `bash scripts/test_install_service.sh`.

## 4. README

- [x] 4.1 Say four public endpoints everywhere five are named (intro, endpoint note, code layout, hosting section, docs-port section, "any path but the five"), and drop `POST /application/email-status` from the public lists; outside tools in the intro are Muse only.
- [x] 4.2 Rename "Email status updates (n8n)" to "Email status updates (Hermes)" (fix the anchor link in the endpoint table), describe it as the local Hermes workflow on the Mac mini calling the local listener, use `http://127.0.0.1:8081/application/email-status` in the curl example, and change "In n8n, route 404, 409 and 422…" to Hermes.
- [x] 4.3 Update the smoke test paragraph: `POST /application/email-status` is among the public 404 probes, and the `Applied` `no_match` check runs on the local listener. Verify with `grep -ni "n8n\|five" README.md` showing no stale references.

## 5. Specs and integration check

- [x] 5.1 Run `pytest`, `bash scripts/test_smoke_test.sh` and `bash scripts/test_install_service.sh`; all pass. Run `openspec validate email-status-local-only --strict`.
- [x] 5.2 Sync the delta specs to `openspec/specs/` (`local-service-hosting`, `api-docs`) and edit the `email-status-updates` Purpose sentence in the main spec to name the owner's local Hermes workflow on the Mac, which calls the local listener, instead of n8n.

## Workflow follow-up

- After merge, reinstall the service (`scripts/install_service.sh`), point Hermes at `http://127.0.0.1:8081/application/email-status`, and run `scripts/smoke_test.sh`.
- Update the "Service is public via Tailscale Funnel" memory if it names five public endpoints.
- Archive the change once the PR is merged.
