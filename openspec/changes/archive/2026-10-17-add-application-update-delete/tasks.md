# Tasks

## 1. Baseline

- [x] 1.1 Run `.venv/bin/python -m pytest` and check that the existing suite passes. Create `.venv` from `requirements-dev.txt` first if it is missing. Then check that `.venv/bin/python -c 'import sqlite3; print(sqlite3.sqlite_version)'` prints 3.35 or later, which `RETURNING` needs (design D4).

## 2. Store: status column and migration

- [x] 2.1 In `app/applications.py`, add `status TEXT NOT NULL DEFAULT 'verified'` and `updated_at TEXT` to `SCHEMA`. In `ApplicationStore.__init__`, after `CREATE TABLE IF NOT EXISTS`, add the column check and `ALTER TABLE ... ADD COLUMN` migration inside `BEGIN IMMEDIATE` (D1). Wrap any failure in `StorageError` naming `OUTPUT_DIR`. Verify in `tests/test_applications.py`:
  - a fresh store's new row has status `verified` and a null `updated_at`
  - a store file created with the old schema and holding two rows, opened with `ApplicationStore`, has both rows `verified` with their IDs and fields unchanged
  - opening a migrated store again, after setting a row to `offer` with raw SQL, leaves `offer` in place
  - two `ApplicationStore` instances opened on the same old-schema file in two threads both succeed
  - the existing store tests still pass

## 3. Store: update and delete

- [x] 3.1 Add `update(application_id, changes) -> str | None`, `delete(application_id) -> bool` and `exists(application_id) -> bool` to `ApplicationStore` (D4). `update` writes only the given known columns plus `updated_at` (UTC ISO 8601 with a `Z` suffix) in one `UPDATE ... RETURNING status`. Every method wraps `sqlite3.Error` in `ApplicationStoreError`. Verify in `tests/test_applications.py`:
  - `update` changes only the given fields, sets `updated_at` no earlier than `created_at`, keeps `created_at`, and returns the new status
  - `update` with `{"sponsorship": None}` stores NULL
  - `update` and `delete` on a missing ID return `None` and `False`
  - after `delete`, `exists` is false, and `record` of a decorated variant of the same link returns `(new_id, True)` with `new_id` larger than the old ID
  - deleting the largest-ID row and then recording gives a larger ID
  - 8 threads updating different fields of one row each land, with no exceptions
  - an update survives a new `ApplicationStore` instance (restart)
  - a closed or locked database raises `ApplicationStoreError`

## 4. Request model

- [x] 4.1 In `app/models.py`, add `ApplicationStatus` and `ApplicationUpdate` (D2, D3), with `IMMUTABLE_FIELDS` rejected by a before-validator and an empty-update check. Use the same error-message rules as `ApplicationRow`, which name fields and never values. Verify with new tests in `tests/test_models.py`:
  - each of the six statuses is accepted, and "ghosted", "Applied" and `null` are rejected
  - `company: ""` and `company: null` are rejected
  - `salary: 5` is rejected
  - `sponsorship: null` is accepted and appears in `model_dump(exclude_unset=True)` as `None`
  - absent fields do not appear in the dump
  - each immutable field, alone or together with `status`, is rejected with a message naming it
  - `{}` and `{"found": true}` are rejected as having no updatable fields
  - a sentinel value never appears in an error message
  - the `ApplicationRow` and `JobRow` tests still pass

## 5. Endpoints

- [x] 5.1 In `app/main.py`, add `parse_application_id(raw) -> int | None` (D5) and `PATCH /application/{application_id}`. Follow the auth → ID → body → store order: 401, then 404, then 422 (or 404 when the row is missing), then `update`, giving 200 `{"ok": true, "application_id", "status"}`. Return 503 with a generic message and log `application_store_error` when the store fails. Set `request.state.application_id` once the ID parses. Verify with new tests in `tests/test_api.py`, using a real store in `tmp_path`, that cover every PATCH scenario in `specs/application-api`:
  - 401 for a missing or wrong key, including on a missing ID and with a bad body
  - 404 for `999999`, `abc`, `0` and `-1`, with the `{"ok": false, "message"}` shape and no `detail` key
  - 404 for an unknown ID with a non-JSON body
  - 422 for malformed JSON, non-object bodies, a bad status, an immutable field and an empty body, each with the row left unchanged
  - a status-only update changes nothing else
  - setting the same status again returns 200
  - the exact response keys
  - a duplicate `POST` after `PATCH` to `interviewing` keeps `interviewing` and leaves the `POST` body keys unchanged
  - a store stub that raises returns 503 with no path or exception text
- [x] 5.2 Add `DELETE /application/{application_id}` (D5): 401 → 404 for an unparseable ID → `delete` → 200 `{"ok": true, "application_id"}` or 404, and 503 on a store error. Never read the body. Verify with new tests in `tests/test_api.py`:
  - 401 with a wrong key, with the row kept
  - 200 with the exact body keys, then 404 on a repeat delete and on a `PATCH` of the same ID
  - re-posting the deleted `job_link` returns 201 with a larger ID and status `verified`
  - a request body is ignored
  - 404 for `abc`
  - 503 from a raising stub
- [x] 5.3 Update the log middleware (D6) to match `/application` and `/application/*` as `application_request` and to add `method` to every application line. Verify with `caplog` tests:
  - exactly one `application_request` line, with the correct method, status and `application_id`, for each of: a PATCH success, PATCH 401, PATCH 404, PATCH 422, DELETE success and DELETE 404
  - `POST` lines now carry `method: "POST"` and otherwise keep their existing fields
  - no status value, body value or API key appears in any line
  - no `job_request` line is emitted for application paths
  - the existing `/jobs` logging tests pass unchanged
- [x] 5.4 Update `README.md`:
  - add `PATCH /application/{application_id}` and `DELETE /application/{application_id}` to the endpoint table, with their status codes and bodies
  - add a status-values table that says the default is `verified`
  - list the updatable and immutable fields, and explain that `null` clears an optional field
  - say that delete is permanent, frees the link, and that `withdrawn` is the non-destructive alternative
  - add curl examples for both endpoints
  - note under the backup section to back up before upgrading, because of the migration
  - update the `service.log` line to cover all application requests

  Verify that each new curl example, run against a local server, returns the documented response.

## 6. Integration check

- [x] 6.1 Run `.venv/bin/python -m pytest` and check that it passes. Then copy a pre-change `applications.sqlite3` (or one built with the old schema) into a scratch `OUTPUT_DIR`, start `uvicorn app.main:create_app --factory --port 8080`, and run these requests:
  1. `PATCH` an existing ID to `applied` → 200 with status `applied`
  2. `POST` the same `job_link` → 200 with the same ID
  3. `DELETE` it → 200
  4. `DELETE` it again → 404
  5. `POST` it again → 201 with a larger ID

  Verify that `sqlite3 <OUTPUT_DIR>/applications.sqlite3 'select id, status from applications'` matches, and that `service.log` or stdout shows exactly one `application_request` line per call.

## Workflow follow-up

- Take the open questions in `proposal.md` to the client, especially the status vocabulary, whether immutable fields should be rejected or ignored, and hard versus soft delete. Revise the change with `/opsx:update` if any answer differs from the assumption.
- Before deploying on the Mac mini, back up `applications.sqlite3`. Then redeploy with `scripts/install_service.sh` and confirm through the Funnel URL that `PATCH` and `DELETE` without a key return 401.
- Archive the change once it has been reviewed and deployed.
