# Tasks

## 1. Matching and store

- [x] 1.1 Add `normalize_name(value, kind)` and `match_applications(rows, company, role, job_link)` to `app/applications.py`, following the design's normalization rules, the link-first rule, exact-before-fuzzy tiers and the `difflib` ratio threshold of 0.9. Verify with unit tests in `tests/test_applications.py` covering each "Tolerant name comparison" and "Single-application matching" scenario (suffix/case, `Sr.`/punctuation, typo, different role, link decides, unknown link falls back, exact beats near, company-only match gives no match).
- [x] 1.2 Add the email-status transition function (`Applied` → no change; `Rejected` → `rejected` unless `withdrawn`; `Response` → `interviewing` only from `verified`/`applied`). Verify with a parametrized test over all 6 statuses × 3 email statuses against the spec's "Email status mapping" table.
- [x] 1.3 Add `ApplicationStore.apply_email_status(...)`, which runs under `BEGIN IMMEDIATE`, writes only `status` and `updated_at`, and only when the status changes, and returns no-match / ambiguous(count) / updated(row, previous, current, changed). Wrap `sqlite3.Error` in `ApplicationStoreError`. Verify with store tests that other fields and an unchanged row's `updated_at` stay untouched, that two rows give ambiguous with count 2 and no write, and that a threaded Rejected+Response race always ends at `rejected`.

## 2. HTTP endpoint

- [x] 2.1 Add `EmailStatusRequest` (with the strip/title-case `status` validator, strict strings, ignored extras, and an n8n-shaped example) and the `EmailStatusUpdated`, `EmailStatusNoMatch` and `EmailStatusAmbiguous` response models to `app/models.py`, and register them in `BODY_MODELS` / the documented schemas. Verify with model tests that the example validates, ` RESPONSE ` becomes `Response`, `Interview` fails naming `status` without echoing it, and empty or whitespace `company`/`role` fail.
- [x] 2.2 Add `POST /application/email-status` to `app/main.py`. It checks the key first (401), then parses JSON and an object body (422), validates, calls the store in the threadpool, and maps the result to 200, 404 `no_match` or 409 `ambiguous` with `match_count`, and a store error to 503. It sets `request.state.application_id` only on a single match. Verify with API tests in a new `tests/test_email_status.py` covering every scenario under the auth, body, no-match, ambiguous, success-response shape, only-status-changes, store-failure and logging requirements. The logging tests assert that the company, role, note and both status values are absent from the log line.
- [x] 2.3 Write the operation's OpenAPI summary and description (mapping, `Applied` never writes, forward-only, 404/409 change nothing, served on the public address) and responses `200, 401, 404, 409, 422, 503` with the new schemas, and update the top-level `DESCRIPTION` to name the five public operations. In `tests/test_docs.py`, update `RESPONSES` and the count to 22 (`test_documents_exactly_the_twenty_one_operations` → twenty-two), add the endpoint to the API-key security assertion, add tests for the "Email status endpoint documented" and "Email status responses documented" scenarios, and make sure the error-shape test still holds (the new 404/409 schemas extend `{ok, message}`). Verify with `pytest tests/test_docs.py`.

## 3. Public listener and scripts

- [x] 3.1 Add `("POST", "/application/email-status")` to `PUBLIC_ROUTES` in `app/serve.py` and update its comment. In `tests/test_serve.py`, update `test_public_routes_are_the_four_funnel_endpoints` (rename it to five) and the launcher test comment. Check that the parametrized public-reach test, the every-other-operation-is-404 test and the 404-not-405 test cover the new path, including `GET`, `PATCH` and `DELETE` on it. Verify with `pytest tests/test_serve.py`.
- [x] 3.2 Update `scripts/smoke_test.sh`: the expected operation count goes from 21 to 22 and the comment from twenty-one to twenty-two; add `GET /applications` to the public 404 probes; change the "four endpoints" message to five; and add an authenticated `Applied` probe to `POST /application/email-status` on the public URL, with a company and role no application has, that fails unless the response is 404 with `reason` `no_match`. Extend the stub and cases in `scripts/test_smoke_test.sh` (schema fixture at 22 operations, the new probe passing and failing, and the `GET /applications` probe). Verify with `bash scripts/test_smoke_test.sh`.
- [x] 3.3 Update `scripts/install_service.sh` comments and messages from "four public endpoints" to five. Verify with `bash scripts/test_install_service.sh`.

## 4. Documentation

- [x] 4.1 Update `README.md`. List five public endpoints everywhere four are named (intro, code layout, hosting section, API reference section). Add a short "Email status updates (n8n)" section with the request body, the status mapping, the 404/409 meaning, and a curl example using a sample company (no real hostname or key). Verify with `grep -n "four" README.md`, which should show no stale references to the public endpoint count.

## 5. Integration check

- [x] 5.1 Run the full suite (`pytest`) plus `bash scripts/test_smoke_test.sh` and `bash scripts/test_install_service.sh`, and confirm everything passes. Then run `openspec validate email-status-update --strict`.

## Workflow follow-up

- After merge, reinstall the service (`scripts/install_service.sh`), run `scripts/smoke_test.sh` against it, and wire the n8n HTTP Request node as described in design.md "Migration Plan".
- Archive the change once the PR is merged.
