# Design

## Context

See proposal.md, Why. Current state:

- `POST /resume` and `POST /cover-letter` (`app/main.py`) validate the request, then `await run_in_threadpool(...)` the whole generation, save the file and reply 201. Failures map to 500 and 502.
- `app/serve.py` builds **two** FastAPI apps in one process, public (8080, Funnel) and docs (8081, tailnet), sharing one `LocalStorage` and one `ApplicationStore`. Any "only one run at a time" rule must hold across both apps.
- `ApplicationStore` (`app/applications.py`) opens a new SQLite connection per call and creates or migrates its tables in `__init__`. `resume_reports` holds the viewer's report and is removed in `delete()`.
- The request log line comes from the `log_request` middleware, which reads `request.state`. `request_event` maps only exact paths for `/resume` and `/cover-letter`.

## Goals / Non-Goals

**Goals:**
- A POST returns within seconds no matter how long generation takes, and the result can be fetched from the public port with the API key.
- Correct across both apps in the process and across restarts.
- No new dependency, and no new process or service to install.

**Non-Goals:**
- A general job queue, job history or job IDs. Only the latest job per application and kind is kept.
- Limiting how many runs execute at once. Today concurrent POSTs already run concurrently, and nothing changes that.
- Cancelling a running job.
- Exposing the viewer reads (`GET /application/{id}` and the PDFs) on the public port.
- Showing job state in the viewer page.
- Changing Muse itself. It lives outside this repo. The README describes the new flow for it.

## Decisions

### 1. Replace the synchronous mode instead of adding a flag
POST always answers 202. Keeping 201 behind something like `?wait=true` would mean two response contracts to document, test and smoke-check, and no client on the public port could use the slow one anyway. Muse is the only external client, and it has to change regardless. The fast no-posting resume path also goes through a job, so there is one flow. The smoke test polls, and the job takes well under a second there.

### 2. Duplicate POST reuses the running job (202), not 409
Muse's connection drops are exactly when it is likely to retry. If a retry gets the same 202 and `started_at`, the retry is harmless and the client needs no new error handling. A 409 would push every client to write "on 409, poll instead". Re-running after `done` or `failed` is allowed and replaces the record, because the API already works as "regenerate on demand".

### 3. Persist jobs in a `generation_jobs` table in the same SQLite file
```
generation_jobs(
  application_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('resume','cover_letter')),
  status TEXT NOT NULL CHECK (status IN ('running','done','failed')),
  started_at TEXT NOT NULL, finished_at TEXT,
  saved_path TEXT, error TEXT, result TEXT,   -- result: JSON {"match": …} or {"text": …}
  PRIMARY KEY (application_id, kind))
```
- It is created with `CREATE TABLE IF NOT EXISTS` like `resume_reports`, so existing stores upgrade in place.
- `resume_reports` stays as it is. The viewer keeps reading it, and a successful resume job still calls `save_report`. The job table holds only what the status endpoints return. It does not replace the report, which holds posting-derived detail that must stay tailnet-only.
- `delete()` also deletes the application's `generation_jobs` rows in its existing transaction.
- An in-memory registry was rejected. It would not survive restarts, and it would not be shared between the two apps unless it lived beside the store anyway. SQLite already gives atomicity across both apps.

### 4. Claim a job atomically with an upsert
`ApplicationStore.start_job(application_id, kind, started_at)` runs one statement:
```
INSERT INTO generation_jobs (application_id, kind, status, started_at)
SELECT ?, ?, 'running', ? FROM applications WHERE id = ?
ON CONFLICT (application_id, kind) DO UPDATE SET
  status='running', started_at=excluded.started_at,
  finished_at=NULL, saved_path=NULL, error=NULL, result=NULL
WHERE generation_jobs.status != 'running'
```
`rowcount == 1` means the job was claimed, and the caller starts the run. `rowcount == 0` means either a job is already running, in which case the caller reads its `started_at` and returns 202, or the application vanished between lookup and claim, in which case the caller returns 404. SQLite serialises writers, so two POSTs, even on different ports, cannot both claim.

### 5. Finish a job only if it is still the same run
`finish_job(application_id, kind, started_at, status, saved_path, error, result)` runs `UPDATE … WHERE application_id=? AND kind=? AND status='running' AND started_at=?`. If the application was deleted mid-run, or startup recovery already failed the row, the update matches nothing and no record is recreated. That is the spec's "deleted while running" scenario. `started_at` has microsecond precision (`utc_now()`), so it serves as the run's identity, and no separate job ID is needed.

### 6. Run each job on its own daemon thread
After claiming, the handler starts `threading.Thread(target=run_job, daemon=True)` and returns 202. The job function is the current synchronous body: `generate_output` or `write_cover_letter`, then the storage save, `save_report` for resumes, `finish_job` and the job log line.
- A thread is not tied to the request, so a client disconnect cannot cancel it. A task waiting on `run_in_threadpool` from a background task would also work, but it would hold one of anyio's shared worker tokens for up to 10 minutes and couple the run to the event loop's lifetime.
- `create_app` takes an optional `start_job: Callable[[Callable[[], None]], None]` parameter, which defaults to starting a daemon thread. Unit tests pass `lambda job: job()`, so the job finishes before the 202 returns and assertions stay deterministic. One test keeps the real thread and polls the status endpoint, to show a real background run.
- Every exception inside the job is caught. Any unexpected exception becomes `failed` with the kind's generic error and an `*_error` log line. A thread that dies silently would leave the row `running` until the next restart.

### 7. Fail interrupted jobs when the store opens
`ApplicationStore.__init__` already creates and migrates tables once per process, before any app is built. It now also runs `UPDATE generation_jobs SET status='failed', finished_at=?, error='Interrupted by a service restart' WHERE status='running'`. `serve.py` builds the store once and shares it, so this runs exactly once per process, before either listener accepts requests. Putting it in `create_app` would run it twice, once per app. That is harmless today, but it would be wrong if an app were ever built while a job was running. A FastAPI lifespan hook was rejected because `by_local_port` sends lifespan only to the public app, which is too indirect for something this important.

### 8. Status endpoints share the POST paths' tags and checks
`GET /resume/{application_id}/status` and `GET /cover-letter/{application_id}/status` are registered in `create_app` (both apps), not in `register_viewer`. They follow the PATCH and DELETE pattern: inline `api_key_valid`, then `parse_application_id`, then the store. "Application not found" is returned when the row is missing. "No job for this application" is returned when the row exists but has no job of that kind. A single join query (`get_job` returns `None`, `"no_job"` or the record) avoids two round trips. The path segments do not collide with `/resume/base.pdf` (one segment versus two).

### 9. Logging
- `request_event` maps every `/resume…` path to `resume_request` and every `/cover-letter…` path to `cover_letter_request`. `method` is logged for every event, not only `application_request`, because POST and GET now share the event name.
- The job line (`resume_job` and `cover_letter_job`) is built from the same fields as `LOGGED_STATE`: match status, scores, turns, cost and judge counts. It also carries `outcome` and `duration_ms`. The code that `note_generation` uses to set `request.state` is refactored into a function that returns a dict, so both the request path and the job path share it.

### 10. Response models
In `app/models.py`, the new `GenerationAccepted` model has `ok`, `application_id`, `status: Literal["running"]` and `started_at`. The new `ResumeJobStatus` and `CoverLetterJobStatus` models have `status: Literal["running","done","failed"]` and nullable fields. `ResumeCreated` and `CoverLetterCreated` are removed, and `ResumeMatch` is reused. Examples are added in `json_schema_extra`, as for the other models. The `errors(...)` sets on the POSTs drop 500 and 502. The `"422_letter"` entry stays. The `"500_letter"` entry is no longer used.

## Risks / Trade-offs

- [A thread hangs past the Claude time limit] → The existing tailoring and letter timeouts (~10 min cap) still bound each run. The row stays `running` only as long as the thread does, and a restart clears it.
- [A crash between file save and `finish_job` leaves `running` with a new file on disk] → Startup marks it `failed`. The file is the newest output, and rerunning replaces it. This is acceptable, and the viewer's report shows the truth for resumes.
- [A deleted application's run still writes its PDF] → This matches today's behavior, where delete keeps generated files. The finish no-ops on the missing row.
- [Many concurrent POSTs for different applications start many Claude runs] → This is unchanged from today. Concurrency limits are a non-goal. The spend cap per run still applies.
- [Breaking change for Muse] → It is deployed together with the Muse update. The README's endpoint table documents POST then poll, and suggests a poll interval of 10–15 s with an overall limit of ~12 min.
- [Daemon threads are killed on shutdown mid-write] → SQLite writes are transactional, and the file write is atomic per `LocalStorage._write`. Startup recovery covers the job row.

## Migration Plan

1. Deploy (merge, then reinstall or restart the service). On first start the store creates `generation_jobs`, and no data migration is needed.
2. Run `scripts/smoke_test.sh`. It now expects 15 operations and polls the status endpoint.
3. Update Muse to read `application_id` from the 202 and poll `GET /resume/{id}/status` (and `/cover-letter/{id}/status`) until `done` or `failed`.
4. Rollback: redeploy the previous commit. The extra table is ignored by old code, and old code's synchronous POST works again for tailnet callers.
