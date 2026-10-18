# Design

## Context

The service is a single FastAPI process. It runs on the Mac mini as the launchd daemon `local.job-hunt-hq`, bound to loopback and published to the internet through Tailscale Funnel. Today it keeps no records. The only persistent state is the generated PDFs under `OUTPUT_DIR/outputs/`, which the retention cleanup deletes after `OUTPUT_RETENTION_DAYS`. `OUTPUT_DIR` is created with mode `0700` and the install and uninstall scripts never remove it. Every `/jobs` error comes from FastAPI's `HTTPException` and uses the `{"detail": ...}` shape. The new endpoint needs a different envelope, `{"ok": false, "message": ...}`. See proposal.md for motivation and the client's decisions; see `specs/application-api` and `specs/application-store` for the contract.

## Goals / Non-Goals

**Goals:**
- Durable, idempotent recording that is safe under concurrent requests from the threadpool.
- The new error envelope applies to `/application` only. `/jobs` responses, logs and tests stay byte-identical.
- No new dependency and no new setting.

**Non-Goals:**
- Read, list, update or delete endpoints for applications.
- Rate limiting and request-body size caps. These are follow-ups and apply to `/jobs` as well.
- Linking an application to a `/jobs` render.
- Migrating or importing rows from the Google Sheet.

## Decisions

### D1. SQLite via the standard-library `sqlite3`, file `<OUTPUT_DIR>/applications.sqlite3`
The client expects an integer row ID, and dedupe needs a uniqueness guarantee that holds across concurrent requests. SQLite gives both with an `INTEGER PRIMARY KEY AUTOINCREMENT` column and a `UNIQUE` constraint on `job_link_key` (D9), in one file, with no new dependency. The host's SQLite (3.54) is new enough for everything used here.
- *Alternatives:* a JSON or JSONL file with a lock (we would have to write our own uniqueness, atomic writes and ID allocation); Postgres (a server to run for a single-user tool); the Google Sheet (`read_sheet.sh` is read-only and anonymous, and writing to it needs OAuth).
- The file sits at the root of `OUTPUT_DIR`, not under `outputs/`. `LocalStorage.cleanup` only walks `outputs/<date>/`, so the store is outside retention by construction. A test pins this.
- `AUTOINCREMENT` makes sure IDs are never reused, even if a row is ever deleted by hand.

### D2. Insert-or-ignore, then select
`record(row)` computes `job_link_key = dedupe_key(job_link)`, runs `INSERT ... ON CONFLICT(job_link_key) DO NOTHING`, then `SELECT id FROM applications WHERE job_link_key = ?`, in one transaction. `job_link` is stored as sent and is not unique. `cursor.rowcount == 1` means the row was created; otherwise the request is a duplicate. The UNIQUE constraint does the arbitration, so two concurrent first requests both end up with the same ID and no lock is needed in Python.
- *Alternative:* select first, then insert. That leaves a race and needs an exception path for `IntegrityError`.

### D3. One connection per call, default rollback journal, `timeout=5`
Each `record()` call opens a short-lived connection inside `run_in_threadpool`. Traffic is a handful of requests a day, so connection cost is irrelevant, and this avoids sharing a connection across threads. With the default `DELETE` journal mode the only extra file is a transient journal, and SQLite creates it with the database file's permissions. WAL would leave `-wal` and `-shm` files permanently.
- *Alternative:* one shared connection with `check_same_thread=False` and a lock. That works but needs more care for no benefit at this volume.

### D4. Store opened at app creation, failing fast
`create_app(settings, storage=None, applications=None)` builds an `ApplicationStore(settings.output_dir / "applications.sqlite3")` when none is passed in. This mirrors how `storage` is injected today. The constructor creates the file with `os.open(..., O_CREAT, 0o600)` before connecting, so the file never exists with wider permissions. It runs `CREATE TABLE IF NOT EXISTS` and performs a write probe. Any `sqlite3.Error` or `OSError` is wrapped in `StorageError("OUTPUT_DIR ... application store is not writable")`, which matches how `LocalStorage` reports an unwritable directory. Once the service is running, the same errors are wrapped in `ApplicationStoreError`, which the route maps to 503.

### D5. Route-local error envelope, no global exception handler
`POST /application` does not use `Depends(require_api_key)`. That dependency raises `HTTPException`, and its `{"detail": ...}` body is the `/jobs` contract. The key comparison moves into a small helper, `api_key_valid(header) -> bool`, which both paths use. `require_api_key` keeps its current behaviour. The `/application` handler checks the key first, then parses and validates the body, and returns `JSONResponse({"ok": False, "message": ...})` for each failure.
- *Alternative:* a global `HTTPException` handler that branches on the path. It is less explicit and risks changing `/jobs` bodies.

### D6. Model: `ApplicationRow` in `app/models.py`
- Use `ConfigDict(extra="ignore")` and `StrictStr` fields, matching `JobRow`.
- Type `posting_source_type` and `verification_method` as `Literal[...]`.
- Make `official_apply_url` a required `StrictStr`, with no `min_length`.
- Enforce the pairing rules in a `model_validator(mode="after")`, including `official_apply_url == job_link` (plain `==` on the raw strings, no normalization) for `official_apply_match`. It raises errors whose text names the offending field, for example `"official_apply_url must equal job_link when verification_method is official_apply_match"`, and never includes values.
- Do not subclass `JobRow`. The two models' required sets differ (`full_job_description`, `job_link`), and inheriting would couple future `/jobs` changes to this contract.

### D7. Validation message format
Build the message as `"Invalid request: " + "; ".join(f"{field}: {msg}")` from `exc.errors()`. For model-level errors, which have an empty `loc`, use only the message. Pydantic's `input` and `ctx` are never included. Pydantic's `msg` for Literal and type errors lists the expected values, not the submitted one. A test posts a sentinel value and asserts it does not appear in the response.

### D8. Logging
Generalise the existing middleware with a path-to-event table: `/jobs` maps to `job_request` (current fields unchanged), and `/application` maps to `application_request`. For the application event, the handler sets `request.state.application_id` and `request.state.duplicate`, and the middleware adds them when present. No body fields are logged.

### D9. `dedupe_key()`: strip tracking parameters, not the whole query
`dedupe_key(link: str) -> str` is a pure function in `app/applications.py`. It parses the link with `urllib.parse.urlsplit`. If the scheme isn't `http` or `https`, or the host is empty, it returns the link unchanged. Otherwise:
- lowercase the scheme and host, and drop `:443` for https and `:80` for http
- strip trailing `/` from the path, keeping the path's case
- drop the fragment
- split the query on `&` by hand, without `parse_qsl`, so percent-encoded values are never decoded and re-encoded
- drop pairs whose name is in `TRACKING_PARAMS` or starts with `utm_` (case-insensitive)
- sort the remaining pairs and rejoin them

`TRACKING_PARAMS` is one module constant: `gh_src`, `source`, `src`, `ref`, `lever-source`, `lever-origin` and `trk`.
- *Alternative:* strip the whole query, as the client first asked. This is rejected because several ATSs and most Greenhouse-on-employer-site pages carry the job ID in the query (`gh_jid`, `token`, `jobId`, `career_job_req_id`). Stripping it would return an existing posting's ID for a different posting with a 200, which the client reads as "already tracked". The new posting would be lost silently, which is worse than a duplicate row.
- *Alternative:* an allowlist of job-ID parameters. This is rejected because an unknown ATS would fail toward silent merging.

## Risks / Trade-offs

- [Public endpoint with durable writes; a leaked API key could flood the disk with rows] → The exposure is the same as `/jobs`, which already writes PDFs. Follow-ups: rate limiting and a body-size cap. Rotating `API_KEY` is the immediate kill switch.
- [A tracking parameter not in `TRACKING_PARAMS` still produces a duplicate row] → This is a duplicate, not data loss. Extend the constant when one shows up; the client has been asked to report any they see.
- [Changing the normalization rules changes keys for existing rows] → The raw `job_link` is stored, so a one-off script can recompute `job_link_key` and report any collisions before the new rules are deployed.
- [Duplicates never update the row, so a corrected re-send is silently dropped] → The client accepted this (decision 5) and treats 200 as "already tracked". An update path can be added later.
- [SQLite file corruption on power loss] → The default `synchronous=FULL` with a rollback journal is crash-safe. The file is small; back it up with `sqlite3 applications.sqlite3 .backup`, which is documented in the README.

## Migration Plan

This change is additive. Deploy it with the existing `scripts/install_service.sh`, which restarts the daemon; the store is created on first start. To roll back, revert the commit and reinstall. The leftover `applications.sqlite3` file is ignored by the old code and by cleanup.

## Open Questions

None. The client has answered the contract questions; see proposal.md, "Client decisions".
