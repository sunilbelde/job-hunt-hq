# Proposal

## Why

`POST /cover-letter` now writes a tailored letter for an application, but the owner can only check it by opening the PDF from the output folder. The viewer already shows each generated resume beside the base resume. The owner wants to review cover letters the same way: the tailored letter next to the base letter, in the same page, for the same application.

## What Changes

- **Cover letter view in the viewer**: for the selected application, the owner can switch the side-by-side panes between "Resume" and "Cover letter". The cover letter view shows the base letter (`data/COVER_LETTER.pdf`) labelled "Base" and the application's saved letter labelled "Generated", rendered inline by the browser, stacked on narrow screens, exactly like the resume panes. When no letter was generated for the application, the generated pane says so. The resume view stays the default and is unchanged.
- **New `GET /application/{application_id}/cover-letter.pdf`** (viewer read, no API key, docs listener only): returns the application's saved cover letter as `application/pdf` with `Cache-Control: no-store`. It looks in the application's folder for its current company and, failing that, in the folder of the resume its report points to, so a company renamed after generation still finds the letter. 404 `Cover letter not found` when there is none or the path is outside `OUTPUT_DIR`.
- **New `GET /cover-letter/base.pdf`** (viewer read, no API key, docs listener only): returns the committed `data/COVER_LETTER.pdf` as is, read again on each request. 404 `Base cover letter not found` when the file is missing. The service still never generates or edits the base letter, and tailored letters still never use it as input.
- Saved cover letters become readable over HTTP through the viewer endpoint only, on the tailnet docs listener only, the same exposure resumes already have. The public listener still serves neither.
- Both reads are logged without content, change nothing, and are documented in the API reference. The documented operation count goes from 11 to 13, in the docs tests and the smoke test.

Out of scope: scoring or diffing letters (no letter report exists), showing the letter's plain text, a "has a letter" marker in the application list, and generating letters from the viewer.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `resume-viewer`: adds the two cover letter reads and the Resume / Cover letter switch with base and generated letter panes; read-only and logging rules cover the new reads.
- `output-storage`: cover letter files are no longer "never served over HTTP"; the viewer's docs-listener read may serve them, like resumes.
- `cover-letter-writing`: the service now serves the base letter read-only to the viewer, but still never reads it for generation, regenerates or edits it.
- `api-docs`: 13 documented operations, with the two new PDF reads' responses and no API-key requirement.
- `local-service-hosting`: the smoke test expects 13 operations on the docs listener.

`output-storage`, `cover-letter-writing`, `api-docs` and `local-service-hosting` deltas modify requirements that the unarchived `add-cover-letter` change introduces or rewrites, so `add-cover-letter` must be archived before this change.

## Impact

- **Code**: `app/main.py` (`register_viewer` gets the two routes; `request_event` maps the base letter path), `app/viewer.py` (switch, letter panes, lazy fetch of letter PDFs, blob URL cleanup), `app/storage.py` (reuse `cover_letter_path` and `COVER_LETTER_FILE_NAME`; no write changes).
- **API**: two new GET endpoints, only on the docs listener; no change to existing responses.
- **Tests**: `tests/test_viewer.py` (new reads, rename fallback, path containment, no key, logging, page checks), `tests/test_docs.py` (13 operations, statuses, PDF responses), `scripts/smoke_test.sh` and `scripts/test_smoke_test.sh` (count 13).
- **Docs**: README endpoint table and viewer section; the base cover letter note no longer says the service never serves it.
- **Clients**: none; Muse uses neither endpoint.
