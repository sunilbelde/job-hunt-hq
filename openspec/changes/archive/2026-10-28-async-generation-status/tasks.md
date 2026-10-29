# Tasks

## 1. Job records in the application store

- [x] 1.1 Add the `generation_jobs` table (design §3) to `app/applications.py`, created with `CREATE TABLE IF NOT EXISTS` in `ApplicationStore.__init__`. Verify with a `tests/test_applications.py` test that a store created before jobs existed opens with every application row and report unchanged and no job rows.
- [x] 1.2 Add `start_job(application_id, kind, started_at)` using the single upsert from design §4, returning claimed, already running (with the running job's `started_at`) or no application. Verify with tests for: a new claim, a claim while running (no change, existing `started_at`), a reclaim after `done` or `failed` (result fields cleared), an unknown application (no row), and independent claims for `resume` and `cover_letter`.
- [x] 1.3 Add `finish_job(application_id, kind, started_at, status, saved_path, error, result)` that updates only the matching running row (design §5). Verify with tests that it records `done` with `saved_path` and `result` JSON, records `failed` with `error`, and is a no-op after the application is deleted or when `started_at` differs.
- [x] 1.4 Add `get_job(application_id, kind)`, returning `None` for an unknown application, a distinct "no job" value for an application without one, or the record with `match` or `text` decoded. Verify with tests for all three cases.
- [x] 1.5 Extend `delete()` to remove the application's job rows in the same transaction. Verify with a test that no job rows remain after delete, and that a later `finish_job` recreates nothing.
- [x] 1.6 Mark every `running` job `failed` with "Interrupted by a service restart" and `finished_at` in `ApplicationStore.__init__` (design §7). Verify with a test that reopens a store holding running, done and failed jobs: only the running one changes.
- [x] 1.7 Raise `ApplicationStoreError` from every new method on SQLite errors, like the existing methods. Verify with a test against an unreadable store file.

## 2. Background runner and logging plumbing

- [x] 2.1 Add the `start_job` parameter to `create_app`, defaulting to starting a daemon thread (design §6), and make the test fixtures in `tests/conftest.py` pass a synchronous runner. Verify that the existing test suite still passes.
- [x] 2.2 Refactor `note_generation` into a helper that returns the log fields for a match and run, used both for `request.state` and for job log lines. Add a `log_job(event, application_id, outcome, duration_ms, fields)` helper that emits one JSON line. Verify with a unit test that the job line contains no company, path or text.
- [x] 2.3 Update `request_event` so every `/resume…` path maps to `resume_request` and every `/cover-letter…` path to `cover_letter_request`, and log `method` for every event. Verify by updating the log assertions in `tests/test_api.py` and `tests/test_cover_letter.py`.

## 3. Async resume generation and its status endpoint

- [x] 3.1 Add `GenerationAccepted` and `ResumeJobStatus` to `app/models.py` with field descriptions (no examples, like the other response models), and remove `ResumeCreated`. Verify that `tests/test_docs.py` checks their documented fields.
- [x] 3.2 Rewrite `create_resume`. After the key, body, lookup and store checks, call `start_job`. Return 202 `GenerationAccepted` when the job is claimed or already running, 404 when the application vanished, and 503 on a store error. Move generation, save, `save_report`, `finish_job` and the `resume_job` log line into a job function that catches every exception and records the generic errors from the spec. Verify with `tests/test_api.py` cases for 202, a duplicate POST (one generation call), 401-before-404, a render error, a tailoring error and a storage error (job `failed` with a generic `error`, no path), and the report still saved on success.
- [x] 3.3 Add `GET /resume/{application_id}/status` in `create_app`, so both apps get it, with the inline key check, `parse_application_id` and `get_job`. Return 404 "Application not found" or "No job for this application", and 503 on a store error. Verify with tests for 401 on an unknown ID without a key, 404 for both cases, running, done and failed bodies with exact keys and null rules, a read that changes nothing, and the endpoint answering on the public app while `GET /application/{id}` there still answers 404.
- [x] 3.4 Add one test that uses the real thread runner: POST /resume returns 202 before generation finishes (a fake generator blocks on an event), `/health` and the status endpoint answer `running` meanwhile, and the status endpoint reaches `done` after the event is released.
- [x] 3.5 Update the OpenAPI text for `POST /resume` (202 and background run, duplicate reuse, poll the status endpoint, no 10-minute timeout) and add the status operation under the `resumes` tag with 200, 401, 404 and 503. Update `RESPONSES` and the operation count in `tests/test_docs.py` (13 → 14), and the response-shape assertions. Verify that `pytest tests/test_docs.py` passes.
- [x] 3.6 Update the README's `POST /resume` row and add a `GET /resume/{id}/status` row describing POST-then-poll, with a 10–15 s poll interval and a ~12 min limit, plus the request-log section (`resume_job` line). Verify by reading the rendered table against the spec.

## 4. Async cover letter generation and its status endpoint

- [x] 4.1 Add `CoverLetterJobStatus` to `app/models.py` and remove `CoverLetterCreated`. Verify that the model example tests pass.
- [x] 4.2 Rewrite `create_cover_letter` like 3.2. The no-posting-text 422 stays on the POST, before `start_job`. Write the `cover_letter_job` log line. Verify with `tests/test_cover_letter.py` cases for 202, 422 with no job row created, a duplicate POST, a resume and a letter running together, a gate failure, a storage failure, and the resume job and report left unchanged.
- [x] 4.3 Add `GET /cover-letter/{application_id}/status` like 3.3, returning `text` in place of `match`. Verify with the same set of tests as 3.3.
- [x] 4.4 Update the OpenAPI text for `POST /cover-letter` and add the status operation under `cover letters`. Drop the `500_letter` and 502 entries from the POST. Update `tests/test_docs.py` to 15 operations, including the `Job status values` and `Background generation described` checks. Verify that `pytest tests/test_docs.py` passes.
- [x] 4.5 Update the README's `POST /cover-letter` row and add the `GET /cover-letter/{id}/status` row, plus the cover letter section's timeout wording. Verify against the spec.

## 5. Restart recovery wiring

- [x] 5.1 Confirm that `app/serve.py` builds the store once before both apps, so recovery runs once per process before either listener serves. Add a `tests/test_serve.py` test that a running job in the store is `failed` once `main`'s app setup runs (with uvicorn stubbed). Verify that the test passes.
- [x] 5.2 Add an API test: seed a running job, build a new app on that store file, and check that `GET /resume/{id}/status` reports `failed` with "Interrupted by a service restart" and that a new POST starts a run.

## 6. Smoke test

- [x] 6.1 Change `scripts/smoke_test.sh` to expect 15 operations. Expect 202 from `POST /resume`, then poll `GET $base/resume/$application_id/status` (e.g. every 1 s, up to 60 s) until `done`. Fail on `failed`, on a timeout or on 404, then read `match.status` and `saved_path` from the status body. Keep the cover letter 422 check and the cleanup. Update the help text and the comment saying "thirteen operations".
- [x] 6.2 Update `scripts/test_smoke_test.sh`: the stub serves 202 and a status sequence. Rename the fixtures to fifteen operations, and test fourteen and thirteen operations failing. Add cases for status `failed`, a status that never finishes, a 404 from the status endpoint, and the cleanup still running in each. Verify that `sh scripts/test_smoke_test.sh` reports no `FAIL`.

## 7. Integration checks

- [x] 7.1 Run the full suite (`pytest`) and `sh scripts/test_smoke_test.sh` and `sh scripts/test_install_service.sh`, and verify that all pass.
- [x] 7.2 Run `openspec validate async-generation-status --strict` and verify that it passes.
- [x] 7.3 Run `python -m app.serve --port 8080 --docs-port 8081` locally. Check that `/docs` on 8081 lists 15 operations, then run `API_KEY=… scripts/smoke_test.sh http://127.0.0.1:8080`, and verify that it passes end to end.

## Workflow follow-up

- Open a PR from `generation-status-endpoint` to `main` (do not push to main).
- Update Muse to POST and then poll the status endpoint before or alongside deploying. Deploying first breaks Muse's reading of `saved_path` from the POST.
- Archive the change after review and deploy.
