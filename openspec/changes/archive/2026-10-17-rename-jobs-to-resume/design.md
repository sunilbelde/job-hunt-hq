# Design

## Context

See proposal.md for motivation, and the delta specs (`job-api`, `output-storage`, `service-config`, `application-store`, `application-api`, `local-service-hosting`) for the required behavior.

Current state:

- **`POST /jobs`** (`app/main.py`):
  - Uses `require_api_key`, which gives `{"detail"}` errors.
  - Validates the body as `JobRow` and calls `generate_output(job, job_id=...)` in the threadpool.
  - Calls `storage.upload()`, which writes `outputs/YYYY-MM-DD/<uuid>.pdf`, then `storage.presigned_url()`.
  - Returns `job_id`, `url`, `expires_at` and `key`.
- **`GET /files/{key}`** serves files through `LinkSigner` verification.
- **Cleanup:** a lifespan task runs `storage.cleanup()` at startup and every hour.
- **`app/storage.py`** holds the `Storage` protocol, `LocalStorage`, `LinkSigner`, `build_key`, `is_valid_key` and `content_type_for`. `LocalStorage.__init__` creates `OUTPUT_DIR` and `outputs/` with mode 700, and probes that they can be written.
- **`app/settings.py`** requires `LINK_SIGNING_SECRET` and `PUBLIC_BASE_URL`, and validates TTL, URL format and retention against TTL. `extra="ignore"` is already set.
- **Logging:** the `log_request` middleware maps the path to an event and emits the `request.state` fields `key`, `application_id` and `duplicate`.
- **`/application` handlers** check the key inline and use `application_error`, `application_not_found` and `validation_message`. `POST /resume` reuses these.
- **`ApplicationStore`** has no single-row read.

## Goals / Non-Goals

**Goals:**

- One handler, `POST /resume`, that follows the `/application` conventions and writes the PDF to a fixed per-application path.
- Remove every piece that existed only for download links: the route, signing, keys, retention, and four settings.
- A generation interface that takes the stored application.

**Non-Goals:**

- No schema change to `applications.sqlite3`, and the row does not record where its resume lives.
- No cleanup of the legacy `outputs/` folder or of resumes for deleted applications.
- No change to Funnel or Tailscale setup, the install and uninstall scripts, or the access-log query redaction filter. The filter stays as general protection.
- No new resume or template inputs. `SUNIL BELDE.pdf` is a module constant.

## Decisions

### 1. Inline auth and `application_error` for every error

`POST /resume` checks `api_key_valid` inline and returns `application_error(...)` for 401, 404, 422, 500, 502 and 503. After this change `require_api_key` has no callers and is removed. Once the `/files` route is removed, no route uses `HTTPException`.

- *Alternative:* add a global exception handler that rewrites `HTTPException`. Rejected because inline checks match the existing `/application` code.

### 2. Body model `ResumeRequest` with `StrictInt`

`ResumeRequest(BaseModel)` has `application_id: StrictInt` and `extra="ignore"`. `StrictInt` rejects `"7"`, `7.5` and `true`, which gives the 422 through `validation_message`. After validation, an integer outside `1..MAX_APPLICATION_ID` gets 404 without a store read, matching `parse_application_id`.

- *Alternative:* `Field(gt=0)`, which would make 0 a 422. Rejected so that the "cannot name a row ⇒ 404" rule matches the path endpoints.

### 3. `ApplicationStore.get(application_id) -> dict | None`

The new method reads one row in a single `SELECT` with `sqlite3.Row`. It returns `id`, `job_link`, every `FIELDS` column, `status`, `created_at` and `updated_at`, or `None`, and wraps `sqlite3.Error` in `ApplicationStoreError`.

### 4. Generation takes a `StoredApplication`

`StoredApplication(BaseModel)` is a read model of a stored row:

- required: `id`, `company`, `role`, `job_link`, `posting_source_type`, `verification_method`, `official_apply_url`, `status`
- optional, as `str | None`: every other posting field, including `full_job_description`

The signature becomes `generate_output(application: StoredApplication) -> GeneratedFile`, and `job_id` is dropped. `ApplicationRow` is not reused, because its pairing validator belongs to recording, not reading. `JobRow` is deleted.

### 5. Storage becomes a resume writer

`app/storage.py` is cut down to the following:

- **`company_folder(company: str) -> str`** applies the spec's naming rule in this order:
  1. Replace `/`, `\`, `:` and control characters (Unicode category `Cc`) with `-`.
  2. Strip spaces and dots from both ends.
  3. Cut to 100 characters, then strip again.
  4. Use `unknown-company` if the result is empty.
  5. Prefix `_` when `name.lower().startswith("applications.sqlite3")`, which covers the store file and its `-wal`, `-journal` and `-shm` siblings.

  It is a pure function with its own unit tests.
- **`RESUME_FILE_NAME = "SUNIL BELDE.pdf"`**.
- **`LocalStorage(root)`** keeps the constructor's create-and-probe of `OUTPUT_DIR` with mode 700, but no longer creates `outputs/`.
- **`LocalStorage.save_resume(company, application_id, content: bytes) -> Path`** works as follows:
  1. Build `root / company_folder(company) / str(application_id)`.
  2. Check that the resolved path `is_relative_to(root.resolve())`, as a second guard. Failing it raises `StorageError`.
  3. Create each missing folder with mode 700.
  4. Write with `mkstemp(prefix=".tmp-", dir=app_dir)`, which creates the file with mode 600, then `fsync`, then `os.replace` onto `RESUME_FILE_NAME`.
  5. Unlink the temporary file on any `OSError` and raise `StorageError`.
  6. Return the absolute path.

  `os.replace` gives the atomic overwrite.
- **`Storage` protocol:** reduced to `save_resume`, so the test fakes in `conftest.py` stay small.
- **Removed:** `LinkSigner`, `build_key`, `is_valid_key`, `KEY_RE`, `content_type_for`, `CONTENT_TYPES`, `presigned_url`, `verify_link`, `path_for`, `cleanup`, `STALE_TMP_SECONDS`.

Alternatives considered:

- *Write directly to the final name and skip the temporary file.* Rejected, because an interrupted regeneration would destroy the previous good resume.
- *Slugify company names to ASCII.* Rejected, because the user expects to see the real company name in Finder. Replacing only the characters that break paths is enough on APFS.
- *Keep a stale-temp sweep.* Not needed, because temporary files are unlinked on failure, and a hard kill leaves at most one `.tmp-*` file in that application's folder.

Folder name collisions on case-insensitive APFS, such as "Acme" and "acme", merge into one company folder. That is harmless because the application-ID folder underneath is unique.

### 6. `POST /resume` request handling order

The handler runs these steps in order:

1. auth (401)
2. JSON/object/`ResumeRequest` validation (422)
3. range check, then `get()` in the threadpool (404, or 503 on `ApplicationStoreError`)
4. set `request.state.application_id`, which happens as soon as the integer is parsed
5. build a `StoredApplication` and run `generate_output` in the threadpool (500 on `RenderError`)
6. run `storage.save_resume(app.company, app.id, generated.content)` in the threadpool (502 on `StorageError`)
7. return `JSONResponse(201, {"ok": True, "application_id": id, "saved_path": str(path)})`

`generated.extension` and `content_type` are no longer used by the caller. `GeneratedFile` keeps them so that tailoring can later use the same interface.

### 7. Remove downloads, cleanup and settings

- **`app/main.py`:**
  - Delete the `/files` route.
  - Delete `run_cleanup`, `cleanup_loop`, `CLEANUP_INTERVAL_SECONDS` and the `lifespan`. The app has no lifespan left.
  - Remove the `FileResponse`, `HTTPException`, `Depends`, `asyncio`, `contextlib`, `timedelta` and `uuid` imports if they become unused.
  - Build `LocalStorage(settings.output_dir)`.
- **`app/settings.py`:** delete `link_signing_secret`, `public_base_url`, `output_retention_days`, `signed_url_ttl_seconds`, `MAX_SIGNED_URL_TTL_SECONDS`, `_absolute_http_url` and `_retention_covers_ttl`. `extra="ignore"` already makes leftover `.env` entries harmless.
- **`.env.example`:** keeps only `API_KEY`, `OUTPUT_DIR` and `ANTHROPIC_API_KEY`.

### 8. Logging

- `request_event` maps `/resume` to `resume_request`, and the `/jobs` branch is removed.
- The middleware stops minting `job_id`.
- `request.state.key` is no longer set, so the emitted fields are `application_id` and, for `/application`, `duplicate`. The saved path is never put on `request.state`.
- Render and storage error lines log `application_id`.

### 9. Smoke test flow

`scripts/smoke_test.sh <base_url>` must run on the Mac, because it reads the saved file. It does the following:

1. Posts a fixed `employer_site` application (company `Smoke Test Co`, `job_link` `https://example.com/job-hunt-hq-smoke-test`, `official_apply_url` set to `""`).
2. Remembers whether the response was 201 (created) or 200 (existing).
3. Posts `{"application_id": ...}` to `/resume` and expects 201.
4. Reads `saved_path` and checks that the file exists and starts with `%PDF`.
5. Runs cleanup from a trap. Only when step 1 returned 201, it sends `DELETE /application/{id}` and removes `$(dirname "$saved_path")`, then removes the company folder if it is now empty (`rmdir`, which ignores failure).

## Risks / Trade-offs

- [A client still calling `/jobs` or holding old links breaks immediately] → Call this out in the README and commit. Proposal Open Question 1 offers a 410 stub instead.
- [The company name in a folder name reveals which companies you applied to, to anyone who can list `OUTPUT_DIR`] → Folders are mode 700 and files mode 600. The log line never includes the path.
- [A company rename or an application delete leaves orphaned resume folders] → Accepted and documented (proposal Open Questions 6 and 7). They are easy to find by hand.
- [A smoke test against the live service writes to the real store and `OUTPUT_DIR`] → It uses a fixed synthetic link and removes only what it created.
- [Stale `LINK_SIGNING_SECRET` and similar entries left in `.env` confuse future readers] → The README migration note says to delete them, and the service ignores them.

## Migration Plan

1. Back up `applications.sqlite3`, which is optional because the schema is unchanged. Deploy with `scripts/install_service.sh`.
2. Remove `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL`, `SIGNED_URL_TTL_SECONDS` and `OUTPUT_RETENTION_DAYS` from `.env`. This is optional, because they are ignored.
3. Update any `/jobs` client to the record-then-generate flow.
4. Run `scripts/smoke_test.sh http://127.0.0.1:8080` on the Mac.
5. Delete `<OUTPUT_DIR>/outputs/` by hand once old links are no longer needed.
6. Rollback: revert and reinstall. The old build needs its four settings back in `.env`, and it starts cleaning `outputs/` again. Resume folders are left alone because they sit outside `outputs/`.
