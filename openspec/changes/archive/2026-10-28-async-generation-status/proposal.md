# Proposal

## Why

Muse calls `POST /resume` through Tailscale Funnel on the public port, and its connection drops at about 270 seconds. A tailored resume takes about 5 minutes and is capped at about 10. Muse never sees the result, even when the resume was generated and saved. It also has no other way to find the result. `GET /application/{id}` is registered only on the tailnet docs port, and the public app answers 404 there. The cover letter's `saved_path` and `text` are kept nowhere: only `resume_reports` is stored.

## What Changes

- **BREAKING** `POST /resume` and `POST /cover-letter` start generation in the background and respond **202** `{"ok": true, "application_id", "status": "running", "started_at"}` instead of waiting and responding 201. The synchronous mode is removed, not kept beside the new one: no client on the public port can wait long enough for it.
- Checks that need no generation still answer on the POST itself, before any run starts: 401 bad key, 422 bad body, 404 unknown application, 503 store unavailable, and for the cover letter the 422 for missing posting text.
- Failures during generation no longer come back as 500 or 502 on the POST. They are recorded on the job as `status: "failed"` with a fixed, generic `error` message. The message never holds exception text, Claude or TeX output, posting text, paths or secrets.
- A POST for an application and kind (`resume` or `cover_letter`) that already has a running job starts no second run. It responds 202 with the running job's `started_at`, so a client can safely retry after a dropped connection.
- A new job record per application and kind is stored in the application store: `status` (`running`, `done` or `failed`), `started_at`, `finished_at`, `saved_path`, `error`, and the result: `match` for a resume, `text` for a cover letter. A new run replaces the previous record. Deleting the application removes its records.
- Two new endpoints, both API-key protected and served on the **public** port as well as the docs port:
  - `GET /resume/{application_id}/status` returns the job state, `saved_path` and `match`.
  - `GET /cover-letter/{application_id}/status` returns the job state, `saved_path` and `text`.
  They return no posting text and no full report, so the viewer reads stay tailnet-only. The API key is checked first (401), then the ID. An unknown application, or one with no job of that kind, gets 404.
- On startup, every job still marked `running` is marked `failed` with the error "Interrupted by a service restart", since its thread did not survive the restart.
- Each finished job writes one structured log line (`resume_job` / `cover_letter_job`) with its outcome, duration and the match and Claude-run fields the request line carries today. The POST's own request line now records 202.
- The Swagger/OpenAPI docs, the docs tests and the smoke test's operation count go from 13 to 15 operations. The smoke test polls the resume status endpoint instead of reading a 201 body. The README is updated too.

## Capabilities

### New Capabilities
- `generation-jobs`: Background resume and cover letter runs, their stored job records, the public status endpoints, duplicate-run handling and restart recovery.

### Modified Capabilities
- `job-api`: `POST /resume` responds 202 and starts a background job. Failures, the log line and the match details move to the job record and a job log line. The non-blocking requirement now covers the background run.
- `cover-letter-api`: `POST /cover-letter` responds 202 and starts a background job. Failures and the run's turns and cost move to the job record and job log line.
- `api-docs`: Documents 15 operations, including the two status endpoints and the 202 responses.
- `local-service-hosting`: The smoke test expects 15 operations and polls `GET /resume/{application_id}/status` for the saved path and match.

## Impact

- **Code**: `app/main.py` (POST handlers, new status routes, background runner, `request_event`, startup recovery), `app/applications.py` (new `generation_jobs` table and methods, removed by `delete`), `app/models.py` (202 and status response models).
- **Tests**: `tests/test_api.py`, `tests/test_cover_letter.py`, `tests/test_applications.py`, `tests/test_docs.py` (13 → 15), `scripts/smoke_test.sh` and `scripts/test_smoke_test.sh`.
- **Docs**: OpenAPI descriptions and examples, `README.md`.
- **Clients**: Muse must switch to POST and then poll the status endpoint. Any client that reads `saved_path` and `match` or `text` from the POST response breaks. That breaking change is the point of this change.
- **No new dependencies.** Jobs run in the service process. There is no external queue.
