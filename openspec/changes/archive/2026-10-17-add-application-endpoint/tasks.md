# Tasks

## 1. Baseline

- [x] 1.1 Create `.venv` if it is missing (`python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`) and run `.venv/bin/python -m pytest`. Verify the existing suite passes before any change.

## 2. Application store

- [x] 2.1 Add `dedupe_key(link) -> str` and the `TRACKING_PARAMS` constant to `app/applications.py` (design D9). Verify with table-driven tests in new `tests/test_applications.py`:
  - a trailing slash, a fragment, an uppercase scheme or host, and a default port each collapse to one key
  - `utm_*` in any case, `gh_src`, `source`, `src`, `ref`, `lever-source`, `lever-origin` and `trk` are removed
  - `gh_jid=111` and `gh_jid=222` give different keys
  - `for`/`token` in either order give the same key
  - path case is preserved
  - `%2F` is kept and differs from a literal `/`
  - a query with only tracking params leaves no trailing `?`
  - `"not a url"` and `"ftp://x"` are returned unchanged
- [x] 2.2 Add `ApplicationStoreError`, `ApplicationStore(path)` and `record(fields: dict) -> tuple[int, bool]`, which returns `(application_id, created)`. Implementation:
  - The constructor creates the file with `os.open(O_CREAT, 0o600)`.
  - It creates the `applications` table: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `job_link_key TEXT NOT NULL UNIQUE`, `job_link TEXT NOT NULL`, one TEXT column per other `ApplicationRow` field, and `created_at TEXT` holding UTC ISO 8601.
  - It runs a write probe and wraps any `sqlite3.Error` or `OSError` in `StorageError` naming `OUTPUT_DIR` (D4).
  - `record()` uses a per-call connection with `timeout=5`, runs `INSERT ... ON CONFLICT(job_link_key) DO NOTHING`, then selects the id, and wraps errors in `ApplicationStoreError` (D2, D3).

  Verify in `tests/test_applications.py` with `tmp_path`:
  - first record returns `(id, True)` and a repeat returns `(same id, False)` with the row unchanged
  - a decorated variant of the link returns the same ID and the stored `job_link` keeps its first-seen value
  - two different links get increasing IDs
  - a row recorded through one instance is found by a new instance (restart)
  - omitted optionals are stored as NULL and `""` is stored as `""`
  - file mode is `0o600`
  - a read-only file makes the constructor raise `StorageError` mentioning `OUTPUT_DIR`
  - 8 threads recording the same link yield one row and a single ID
- [x] 2.3 Add a test in `tests/test_storage.py` that puts `applications.sqlite3` in the storage root with an mtime 31 days old (set with `os.utime`) and runs `LocalStorage.cleanup` with a 30-day retention. Verify the file and its rows survive.

## 3. Request model

- [x] 3.1 Add `ApplicationRow` to `app/models.py` (D6):
  - required `company`, `role` and `job_link` (non-empty `StrictStr`)
  - `posting_source_type: Literal["recruiting_platform", "employer_site"]`
  - `verification_method: Literal["official_apply_match", "employer_site"]`
  - required `official_apply_url: StrictStr`
  - optional `StrictStr | None` for `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain` and `full_job_description`
  - an after-validator enforcing the pairing rules, `official_apply_url == job_link` for `official_apply_match`, and `official_apply_url == ""` for `employer_site`
  - `extra="ignore"`

  Verify with new tests in `tests/test_models.py`:
  - the client's example body validates
  - the minimal required body validates
  - each scenario in the "Application field rules", "Posting source and verification method values" and "Source type and method consistency" requirements accepts or rejects as specified, including an `official_apply_url` that differs from `job_link` only by a trailing slash being rejected
  - `found: true` is ignored
  - `JobRow` tests still pass unchanged

## 4. Endpoint

- [x] 4.1 In `app/main.py`, extract `api_key_valid(header) -> bool` from `require_api_key` and keep `require_api_key`'s behaviour. Add the `applications: ApplicationStore | None = None` parameter to `create_app`, defaulting to `ApplicationStore(settings.output_dir / "applications.sqlite3")`. Verify the existing `/jobs` auth tests pass unchanged.
- [x] 4.2 Add `POST /application`. It checks the key first and returns 401 `{"ok": false, "message": "Invalid or missing API key"}`. It returns 422 with `ok: false` and a message for bad JSON, a non-object body, or validation errors, with the message built per D7. It calls `record` through `run_in_threadpool` and returns 201 for a new row or 200 for a duplicate, with body `{"ok": true, "application_id": id}`. It returns 503 with a generic message on `ApplicationStoreError` and logs `application_store_error`. The handler never updates an existing row.

  Verify with new tests in `tests/test_api.py`, using a real store in `tmp_path`, that cover every scenario in `specs/application-api`:
  - 401 missing or wrong key, and 401 before body parsing
  - 422 for malformed JSON, non-object bodies, each field rule and an apply-URL mismatch
  - a sentinel value that never appears in the response
  - 201 then 200 with the same ID
  - a differing `salary` on a duplicate leaves the row unchanged
  - the four decorated Greenhouse links share one ID
  - `?gh_jid=111` and `?gh_jid=222` get different IDs
  - a store stub that raises returns 503 with no path or exception text
  - exact body keys `{"ok", "application_id"}`
- [x] 4.3 Generalise the request-log middleware (D8): `/jobs` keeps `job_request` with its current fields, and `/application` emits `application_request` with status, `duration_ms`, and `application_id` and `duplicate` when set. Verify with `caplog` tests:
  - exactly one `application_request` line per call, for success, duplicate, 401 and 422
  - no `job_request` line is emitted for `/application`
  - no API key or body value appears in the logs
  - the existing `/jobs` logging tests pass unchanged
- [x] 4.4 Run the integration check: run the whole suite with `.venv/bin/python -m pytest`, then start the app locally (`uvicorn app.main:create_app --factory --port 8080` with a scratch `OUTPUT_DIR`). `curl` the client's example body, then the same body with `?utm_source=x` appended to both `job_link` and `official_apply_url`. Verify you get 201 and then 200 with the same `application_id`, that one `application_request` log line appears per call, and that `sqlite3 <OUTPUT_DIR>/applications.sqlite3 'select count(*) from applications'` prints 1.

## 5. Documentation

- [x] 5.1 Update `README.md`:
  - add `POST /application` to the endpoint table (`X-API-Key`; 201/200 `{"ok", "application_id"}`; 401/422 `{"ok": false, "message"}`; 503 store failure)
  - add a request-body table for `ApplicationRow` with the required fields, allowed enum values, pairing rules and the `official_apply_url == job_link` rule
  - describe dedupe: which link variants collapse, the tracking-param list, and that `job_link` is stored as first sent
  - add a curl example and a note that the store lives at `<OUTPUT_DIR>/applications.sqlite3`, with the `sqlite3 ... .backup` command

  Verify that the README curl example, run against the local server, returns the documented response.

## Workflow follow-up

- Tell the client that the server strips only known tracking parameters, not the whole query, and why (job IDs such as `gh_jid` live in the query). Ask them to report any other tracking parameters they see.
- After merge, redeploy on the Mac mini with `scripts/install_service.sh` and confirm through the Funnel URL that `POST /application` returns 401 without a key.
- Archive the change once it is reviewed and deployed.
