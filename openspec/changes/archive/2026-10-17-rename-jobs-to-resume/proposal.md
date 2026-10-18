# Proposal

## Why

`POST /jobs` makes the client send the full job posting again (company, role, job description and so on), even though `POST /application` has already stored all of it on an application row. It then returns a signed download link to a randomly named file that is deleted after 30 days. The service is moving to a local-only setup. Here the resume for an application should be generated from its stored row and kept on disk at a predictable path next to that application. A URL to fetch it is no longer needed.

## What Changes

- **BREAKING** Replace `POST /jobs` with `POST /resume`. The body is exactly `{"application_id": <integer>}`, and other fields are ignored. The service reads the stored application row and generates from it. `/jobs` is removed outright with no alias, so it answers 404 like any unknown path.
- **BREAKING** Save the PDF at `<OUTPUT_DIR>/<company folder>/<application_id>/SUNIL BELDE.pdf`. The company folder is the stored `company`, made safe for use as a folder name. Generating again for the same application replaces the file in place.
- **BREAKING** The success response is 201 with exactly `{"ok": true, "application_id": <integer>, "saved_path": "<absolute path>"}`. `job_id`, `url`, `expires_at` and `key` are dropped.
- **BREAKING** Every error from `POST /resume`, 401 included, uses the `{"ok": false, "message": ...}` shape of the `/application` endpoints, and that includes 500 and 502.
- A missing `application_id`, or one that is not a JSON integer, gets 422 naming `application_id`. An integer that names no stored row (never assigned, deleted, or zero or below) gets 404 `{"ok": false, "message": "Application not found"}`. Nothing is rendered or written in either case. When the application store cannot be read, the response is 503.
- No input outside the application row is needed. The generator is still a stub that renders the baseline resume. The generation interface now takes the stored application instead of a `JobRow`, and `JobRow` is removed. A row with no `full_job_description` is accepted.
- Generating a resume never writes the application row. Status, `updated_at` and every other field stay the same, and any status may generate a resume.
- **BREAKING** The signed download machinery is removed: `GET /files/{key}`, link signing, the `outputs/YYYY-MM-DD/<uuid>` layout, retention cleanup, and the `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL`, `SIGNED_URL_TTL_SECONDS` and `OUTPUT_RETENTION_DAYS` settings. Resume files are kept until deleted by hand. If those variables are still in `.env`, startup ignores them.
- Logging: exactly one line per `POST /resume` request, with event `resume_request`, status, duration and, when known, `application_id`. It never includes the API key, body content or the saved path. The `job_request` event is removed.
- The README, `.env.example` and `scripts/smoke_test.sh` move to the new flow. The smoke test runs on the Mac and checks the file at `saved_path`. It cleans up the application and its folder if the smoke test created them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `job-api`:
  - The submission endpoint is now `POST /resume`, keyed by `application_id`, and returns `saved_path`.
  - The job-posting body and field rules are removed, and so is the signed download endpoint.
  - The 404 lookup, 503 store-failure, error-shape, logging, no-status-change and generation-input requirements are new or changed.
- `output-storage`:
  - Files go to a fixed per-application path with safe company folder names and are replaced on regeneration.
  - Dated keys, signed URLs, download Content-Type and retention cleanup are removed.
- `service-config`: Only `API_KEY` is required. The link signing, public base URL, TTL and retention settings and their validation rules are removed.
- `application-store`: The "Excluded from output retention" requirement is removed, because there is no retention any more.
- `application-api`: The "Job requests unaffected" logging scenario now refers to the `resume_request` event.
- `local-service-hosting`:
  - The log-file and Funnel scenarios name `POST /resume`.
  - The Funnel requirement no longer mentions signed download links.

## Impact

- **Code**:
  - `app/main.py`: the `/resume` route, removal of the `/files` route and the cleanup loop, the middleware event, and error shapes.
  - `app/models.py`: `JobRow` is removed, and `ResumeRequest` and `StoredApplication` are added.
  - `app/generation.py`: the signature changes.
  - `app/applications.py`: a lookup that reads one row is added.
  - `app/storage.py`: rewritten around saving a resume. `LinkSigner`, keys and cleanup are removed.
  - `app/settings.py`: four settings and two validators are removed.
- **Tests**: `tests/test_api.py`, `tests/test_storage.py`, `tests/test_settings.py`, `tests/test_generation.py`, `tests/test_models.py`, `tests/test_applications.py`, `tests/conftest.py` and `scripts/test_smoke_test.sh`.
- **Clients**: Any caller of `POST /jobs`, Muse included if it uses it, must first record the posting with `POST /application`, then call `POST /resume`. It must read `ok`/`message`, and it gets a local path back, not a link. Old download links stop working.
- **Data**: No store schema change. Existing `<OUTPUT_DIR>/outputs/` files are left on disk and are no longer served or cleaned up.

## Open Questions

These are decisions I assumed. Each can be reversed before implementation.

1. **Remove `/jobs` outright, or keep it temporarily?** Assumed: remove it. If Muse or another client still calls `/jobs`, an alternative is to keep it for one release as a stub that answers 410 Gone with a message naming `/resume`.
2. **Should generating a resume change status?** Assumed: no. Generation is read-only, and every status, including `rejected` and `withdrawn`, may generate.
3. **Require `full_job_description`?** Assumed: no, because the stub ignores it. Once the tailoring pipeline exists, a row without a description may need a 4xx.
4. **Body-level ID validation.** Assumed: a non-integer `application_id` (for example `"7"`, `7.5` or `true`) gets 422, and an integer that names no row, including 0 and negatives, gets 404.
5. **Company folder naming.** Assumed:
   - Keep spaces, case and Unicode.
   - Replace `/`, `\`, `:` and control characters with `-`, and trim spaces and dots from both ends.
   - Cap the name at 100 characters, and use `unknown-company` if nothing is left.
   - Prefix `_` to names starting with `applications.sqlite3` (any case).
6. **Company renamed after a resume was generated.** Assumed: the next generation writes under the new company folder, and the old file stays where it is.
7. **Application deleted.** Assumed: its resume folder stays on disk. `DELETE /application/{id}` does not remove files.
8. **File name.** Assumed: `SUNIL BELDE.pdf` is fixed in code, not a setting.
9. **Overwrite status code.** Assumed: regenerating returns 201 like the first generation, not 200.
10. **Legacy `outputs/` folder.** Assumed: left in place for manual deletion, with no automatic cleanup.
11. **Error shape and code for 5xx.** Assumed: 500 for render failures and 502 for failures writing the file, both with `{"ok": false, "message"}` and generic messages. 502 is kept for the local disk to match the existing convention.
12. **Capability name.** Assumed: the spec path stays `job-api`, and no rename to `resume-api` happens, because OpenSpec deltas have no rename operation.
