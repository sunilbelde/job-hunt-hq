# Proposal

## Why

Each application will soon get a cover letter as well as a resume, and clients such as Muse need to know where it lives without guessing the file name. Adding the path to the `POST /resume` response now fixes the contract and the file location early, so cover letter generation can be added later without changing the API again.

## What Changes

- `POST /resume` returns a new `cover_letter_path` field next to the existing `saved_path`: the absolute path of `SUNIL BELDE - Cover Letter.pdf` in the same application folder as the resume.
- `saved_path` keeps its name and meaning, so existing clients (Muse, `scripts/smoke_test.sh`) keep working. The change is additive, not breaking.
- The cover letter location is defined as `<OUTPUT_DIR>/<company folder>/<application_id>/SUNIL BELDE - Cover Letter.pdf`.
- **Placeholder:** no cover letter is generated or written yet. `cover_letter_path` is the path where it *will* be saved, and nothing exists there for now. A `TODO` in the code marks where cover letter generation and saving will go.
- The OpenAPI response model, README and tests are updated for the new field.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `job-api`: the `POST /resume` success response gains `cover_letter_path`, and the per-request log must not contain it.
- `output-storage`: defines where an application's cover letter file goes (next to the resume), and that the service writes no cover letter file yet.

## Impact

- **Code:** `app/storage.py` (cover letter file name constant), `app/models.py` (`ResumeCreated`), `app/main.py` (`create_resume` response and OpenAPI description).
- **API:** additive field on the `POST /resume` 201 response. Clients that check for an exact set of keys need to accept the new one.
- **Tests:** `tests/test_api.py` asserts the exact response keys, so it needs updating. New assertions check the cover letter path and that no file is written there.
- **Docs:** the README `POST /resume` row and its example response.
- **Out of scope:** generating the cover letter, its content, and any change to `scripts/smoke_test.sh`. It still checks only the resume file.
