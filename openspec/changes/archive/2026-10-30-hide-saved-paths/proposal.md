# Proposal

## Why

API responses return the absolute path where a PDF was saved on the Mac, for example `/Users/belde/…/job-hunt-hq/outputs/Scale AI/<id>/SUNIL BELDE.pdf`. That shows the owner's macOS username, the folder layout and which companies were applied to. `GET /application/{id}` on the docs listener needs no API key and returns this path in `report.saved_path`. The key-protected status endpoints return it on the public Funnel address too. Clients only need the file name.

## What Changes

- `GET /resume/{application_id}/status` and `GET /cover-letter/{application_id}/status` return only the file name in `saved_path` (`SUNIL BELDE.pdf` or `SUNIL BELDE - Cover Letter.pdf`) when the job is `done`. It stays `null` while the job is running and after it fails. **BREAKING** for a client that opens `saved_path` as a path on disk. The field name, its type and the null rules stay the same, so a client that reads the field still works.
- `GET /application/{application_id}` returns only the file name in `report.saved_path`.
- The OpenAPI descriptions of both `saved_path` fields say they hold the file name only and never a path.
- No new field. `saved_path` already holds the file name, so a `file_name` field would only repeat it (see design.md).
- The store keeps the full absolute path in job records and reports. The response layer trims it to the file name. `GET /application/{id}/resume.pdf` and `cover-letter.pdf` still use the stored path to find the files after a company rename.
- No response body contains `OUTPUT_DIR` or the service user's home directory. This includes error responses and 404s.
- The smoke test currently opens the file at `saved_path`. It will build the path from `OUTPUT_DIR` (env var, same default as the service), its own company folder, the application ID and the returned file name.
- README: the status table row, the curl examples and the smoke test section are updated.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `generation-jobs`: the status endpoints return the file name in `saved_path`, never a path. The stored job record still holds the absolute path.
- `job-api`: when a resume job is `done`, its `saved_path` is `SUNIL BELDE.pdf`, not an absolute path.
- `cover-letter-api`: when a cover letter job is `done`, its `saved_path` is `SUNIL BELDE - Cover Letter.pdf`, not an absolute path.
- `resume-viewer`: in the application detail, `report.saved_path` is the file name only.
- `api-docs`: the `saved_path` descriptions say the field holds the file name only.
- `output-storage`: new requirement that no response body contains a host path (`OUTPUT_DIR`, the home directory, or a company or application folder). Stored records keep the absolute path.
- `local-service-hosting`: the smoke test finds the saved PDF from `OUTPUT_DIR` and the returned file name.

## Impact

- Code: `app/main.py` (`job_status` response and `read_application` response), `app/models.py` (`JobState.saved_path` and `ResumeReport.saved_path` descriptions). No change to `app/applications.py`, `app/storage.py` or the PDF read endpoints.
- Scripts: `scripts/smoke_test.sh`, `scripts/test_smoke_test.sh`.
- Tests: `tests/test_api.py` and `tests/test_viewer.py` compare `saved_path` with an absolute path in several places, and those assertions change. A new test checks that no response body leaks a path. `tests/test_docs.py` checks the new descriptions.
- Docs: `README.md`.
- Clients: the Tailored Attach browser extension reads `report.saved_path` only for the file name and already handles both forms, so it needs no coordinated release. Muse and other status-endpoint clients only read the field, so they are unaffected unless they open it as a path.
- The number of operations is unchanged (fifteen), so the smoke test's operation count stays the same.
