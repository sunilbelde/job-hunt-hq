# Tasks

These tasks follow the default answers to the proposal's Open Questions. If an answer changes, revise the affected tasks before implementing them.

## 1. Store lookup

- [x] 1.1 Add `ApplicationStore.get(application_id) -> dict | None` in `app/applications.py` (design §3). Verify with new tests in `tests/test_applications.py`:
  - an existing row returns its stored values without `job_link_key`
  - a missing or deleted ID returns `None`
  - a store error raises `ApplicationStoreError`
  - the call leaves `updated_at` unchanged

## 2. Models and generation interface

- [x] 2.1 In `app/models.py`, add `ResumeRequest` and `StoredApplication` (design §2, §4) and delete `JobRow`. Verify in `tests/test_models.py`:
  - the `JobRow` tests are replaced
  - `ResumeRequest` accepts `{"application_id": 7, "x": 1}` and rejects `"7"`, `7.5`, `true`, `null` and a missing ID, with errors naming `application_id`
  - `StoredApplication` accepts a row whose optional fields are null
- [x] 2.2 Change `generate_output` to `generate_output(application: StoredApplication) -> GeneratedFile`, drop `job_id`, and update the docstring. Verify that `tests/test_generation.py` builds a `StoredApplication` and still asserts one `render_pdf` call with a PDF result.

## 3. Resume file storage

- [x] 3.1 Rewrite `app/storage.py` (design §5): add `company_folder`, `RESUME_FILE_NAME`, `LocalStorage(root)` with the create-and-probe step but no `outputs/`, and `save_resume(company, application_id, content) -> Path` with folders at 700, a temporary file at 600, then fsync and `os.replace`. Reduce the `Storage` protocol to `save_resume`. Delete `LinkSigner`, keys, `content_type_for`, `path_for` and `cleanup`.
- [x] 3.2 Rewrite `tests/test_storage.py`:
  - each `company_folder` case from the output-storage spec: spaces and case kept, separators, `../../etc`, `..`, empty or whitespace-only, the `applications.sqlite3` prefix in any case, and the 100-character cut
  - `save_resume` writes `<root>/Acme Corp/7/SUNIL BELDE.pdf` and returns its absolute path
  - two applications at one company get separate folders
  - regenerating replaces the content and leaves exactly one file and no `.tmp-*`
  - a simulated write failure leaves the previous file intact, removes the temporary file and raises `StorageError`
  - folder and file modes are 700 and 600
  - a company of "applications.sqlite3" leaves the store file untouched
  - the unwritable-root startup error still names `OUTPUT_DIR`

  Verify with `pytest tests/test_storage.py`.

## 4. Settings removal

- [x] 4.1 Remove `link_signing_secret`, `public_base_url`, `output_retention_days`, `signed_url_ttl_seconds`, `MAX_SIGNED_URL_TTL_SECONDS` and both related validators from `app/settings.py`. Trim `.env.example` to `API_KEY`, `OUTPUT_DIR` and `ANTHROPIC_API_KEY`, and fix its comments.
- [x] 4.2 Update `tests/test_settings.py`:
  - drop the TTL, signing-secret, URL and retention tests
  - add a test that the service starts with only `API_KEY` set
  - add a test that leftover retired variables, including an invalid `SIGNED_URL_TTL_SECONDS=999999`, are ignored
  - keep the missing-`API_KEY` failure, with the error naming `API_KEY` and no value

  Verify with `pytest tests/test_settings.py`.

## 5. `POST /resume` and removal of downloads

- [x] 5.1 In `app/main.py`, replace `/jobs` with `POST /resume`, following the handler order in design §6 and returning `{"ok", "application_id", "saved_path"}`. Delete the `/files` route, the cleanup loop and the lifespan (design §7). Remove `require_api_key` and any unused imports. Build `LocalStorage(settings.output_dir)`, and fix the comment that mentions `/jobs`' `{"detail"}`.
- [x] 5.2 Update the logging middleware (design §8): `/resume` maps to `resume_request`, there is no `job_id` and no `key`, and render and storage error lines carry `application_id`.
- [x] 5.3 Update the fakes and fixtures in `tests/conftest.py` to the new `Storage` protocol and settings. Rewrite the `/jobs`, download and cleanup tests in `tests/test_api.py` for `/resume`, using a recorded application as the fixture. Cover these cases:
  - 401 with the `ok`/`message` shape for a missing or wrong key, a wrong key with a non-JSON body, and a wrong key with an unknown ID
  - 422 for non-JSON, non-object, `{}` and non-integer IDs, with no value echoed
  - 404 "Application not found" for unknown or deleted IDs, `0`, `-1` and `2**63`, with no folder created
  - 201 with exactly the three keys, where `saved_path` is absolute, equals `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` and the file exists
  - a repeat request returns the same path with the file replaced
  - extra body fields are ignored, and the folder uses the stored company
  - a `PATCH`ed `role` reaches `generate_output`
  - a `PATCH`ed company writes to the new folder and leaves the old one
  - a null `full_job_description` still returns 201
  - status and `updated_at` are unchanged, and `rejected` still returns 201
  - 503 for a store failure, 500 for a render failure with any earlier resume untouched, and 502 for a write failure, all with generic bodies
  - exactly one `resume_request` line per request, with `application_id` and no key, body values, company or path, and no `job_request` lines
  - `POST /jobs` and `GET /files/...` both return 404

  Verify with `pytest`, which must pass in full.

## 6. Docs and smoke test

- [x] 6.1 Update `README.md`:
  - the intro and endpoint table: `POST /resume`, its request, `saved_path`, and 401/404/422/500/502/503. The `GET /files` row is removed
  - replace the `JobRow` section with the `{"application_id"}` body
  - the curl example
  - "Storage and links" becomes "Resume files": the path layout, the folder naming rule, overwrite, permissions, files kept forever, and that `DELETE /application` does not remove them
  - the configuration table cut to three variables
  - the access-control and `service.log` lines, plus the code-layout line
  - a breaking-change and migration note: remove the four variables, delete `outputs/` by hand, and old links stop working

  Verify that `grep -n '/jobs\|JobRow\|job_id\|LINK_SIGNING\|PUBLIC_BASE_URL\|SIGNED_URL\|RETENTION\|/files' README.md` finds only migration-note mentions and job-board example links.
- [x] 6.2 Rewrite `scripts/smoke_test.sh` to the flow in design §9: record, `/resume`, check the file at `saved_path` for `%PDF`, and use a trap to clean up only what it created. Update the usage text to say it must run on the Mac.
- [x] 6.3 Update `scripts/test_smoke_test.sh` so its curl stub tells `/application`, `/resume` and `DELETE` apart and returns a `saved_path` under a temporary folder. Cover:
  - success
  - a failed `/application`
  - a `/resume` 401 or 404
  - a missing file at `saved_path`
  - a non-PDF file
  - a missing API key
  - cleanup (DELETE plus folder removal) when the record step returned 201
  - no cleanup when it returned 200

  Verify that `sh scripts/test_smoke_test.sh` exits 0.

## 7. Integration check

- [x] 7.1 Run `pytest` and `sh scripts/test_smoke_test.sh`, and confirm `grep -rn '"/jobs"\|job_request\|JobRow\|LinkSigner\|presigned\|signed_url\|retention' app tests scripts` returns nothing. Then:
  1. Start the service locally with a temporary `OUTPUT_DIR` and a `.env` that still contains the retired variables.
  2. Run `API_KEY=... scripts/smoke_test.sh http://127.0.0.1:8080`, which should print OK.
  3. Confirm that `OUTPUT_DIR` holds no smoke-test application row or folder afterwards, and that `curl /files/x` returns 404.

## Workflow follow-up

- After merge and reinstall, update Muse, or any other `/jobs` caller, to the record-then-generate flow.
- Remove the retired variables from the live `.env` and delete `<OUTPUT_DIR>/outputs/` once old links are no longer needed.
- Archive the change with `/opsx:archive` once implemented and verified, syncing all six capability deltas.
