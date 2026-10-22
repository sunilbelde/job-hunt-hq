# Design

## Context

- The viewer (`app/viewer.py`) is one HTML page with inline script and a nonce-based CSP. For a selected application, `select()` builds the details, score, additions, gaps and requirements cards and, last, a `.panes` grid with a "Base" and a "Generated" pane. `loadPdfs()` fetches `/resume/base.pdf` once per page load (kept as `baseUrl`) and `/application/{id}/resume.pdf` per selection (kept as `generatedUrl`, revoked on the next selection), and shows each as a `blob:` iframe.
- `register_viewer()` in `app/main.py` registers the read endpoints only when docs are enabled; there is no other guard because they take no key. `find()` resolves the ID, the stored row and the report. `read_resume()` returns bytes only for a regular file inside `OUTPUT_DIR`.
- `POST /cover-letter` (from the `add-cover-letter` change) saves letters at `storage.cover_letter_path(root, company, id)`, the same folder as the resume. Nothing records that a letter exists or where it was saved: no report, no store column.
- `data/COVER_LETTER.pdf` is committed and re-rendered only by the owner's script. The service does not touch it today.
- `request_event()` maps paths to log events: `/resume/base.pdf` → `resume_request`, `/cover-letter` → `cover_letter_request`, anything under `/application/` → `application_request`.

## Goals / Non-Goals

**Goals:**
- Review a tailored letter against the base letter with the same look and behaviour as resumes.
- Keep the resume view, its endpoints and their responses unchanged.
- No new storage or schema: the letter's location is derived, as for legacy resumes.

**Non-Goals:**
- No letter metadata in `GET /applications` or `GET /application/{id}` (no "has letter" flag, no generation time).
- No text diff or highlighting between the two letters; the browser PDF viewer is the comparison, as for resumes.

## Decisions

### A Resume / Cover letter switch above one shared panes grid
The detail view gets a two-button segmented control (`role="tablist"`-style buttons with `aria-pressed`) directly above the panes. Choosing a document replaces the panes grid's contents; the cards above are untouched. Each selection starts on "Resume".

*Alternatives*: a second panes grid under the resume panes would double the page height (each iframe is 1100px) and load four PDFs per selection. A separate page per document would lose the shared details and scores. The switch keeps one comparison on screen at a time and lets the letter PDFs load lazily.

### Letter PDFs load on first switch, cached per selection
Switching to "Cover letter" builds the two panes and fetches the base letter (cached as `baseLetterUrl` for the page load, like `baseUrl`) and `/application/{id}/cover-letter.pdf` (cached as `generatedLetterUrl` for the current selection, revoked with `generatedUrl` on the next selection). Switching back to "Resume" re-shows the resume panes from the URLs already held, without refetching. The existing `loadToken` guard drops results that arrive after the owner moved on. The resume-only "Base resume unchanged" note and the legacy note are about resumes; the letter panes carry no such note.

### Generated letter located by current company, then beside the report's resume
`GET /application/{id}/cover-letter.pdf` tries `cover_letter_path(output_root, company, id)` first, because a letter generated after a rename is saved under the new company. If that has no file and a report exists, it tries `Path(report["saved_path"]).parent / COVER_LETTER_FILE_NAME`, which finds a letter written before a rename next to the resume. Both candidates go through the existing `read_resume()` containment check (renamed to a general `read_output()`), so a symlink or a tampered report path outside `OUTPUT_DIR` yields 404.

*Alternative*: record the letter's saved path in the store on `POST /cover-letter`. Correct across renames without a report, but adds a store migration and changes the cover letter API's "leaves the application unchanged" contract. The two-candidate lookup covers the realistic cases; the remaining gap is under Risks.

### Base letter served from disk, read per request
`GET /cover-letter/base.pdf` reads `TEMPLATE_DIR / "COVER_LETTER.pdf"` (the `data/` folder `app/rendering.py` already uses) on each request, in the threadpool, and returns 404 `Base cover letter not found` on `OSError`. The file is small and the owner re-renders it by hand, so no cache: a re-rendered file shows on the next load without the mtime bookkeeping `BaseResumeCache` needs. It is not rendered by the service: the base letter's source is markdown run through the skill's script, and the spec keeps the service out of generating it.

*Alternative*: 500 when missing, like the base resume's render failure. The base resume is always renderable from committed files; the base letter may legitimately not be drafted yet (task 8.1 of `add-cover-letter`), so "not found" is the honest status and the page shows it as unavailable.

### Logging follows the resume precedent
`/application/{id}/cover-letter.pdf` already falls under `application_request` through the `/application/` prefix and sets `request.state.application_id` via `find()`. `/cover-letter/base.pdf` is added to `request_event()` as `cover_letter_request`, mirroring how `/resume/base.pdf` uses `resume_request`. It carries status and duration only, never turns or cost, since no Claude run happens.

### Route registration only in `register_viewer`
Both routes live in `register_viewer()`, tagged `viewer`, with `pdf_ok(...)` and `errors(...)` entries for the documented statuses (`errors("404_letter", 503)` and `errors("404_base_letter")`, adding the two 404 messages to the shared error examples). On the public listener neither path has any route, so both are plain 404s; `/cover-letter/base.pdf` is a different path from `POST /cover-letter`, so no 405 leaks.

## Risks / Trade-offs

- [A letter generated before a company rename, for an application with no report, is not found] → The viewer says no letter has been generated; regenerating the letter (or the resume, which writes a report) fixes it. Rare: renames after generation are uncommon and reports exist for every resume generated since reports were added.
- [Saved letters become readable over HTTP, which `add-cover-letter` ruled out] → Only through the docs listener, which is bound to the tailnet and already exposes resumes and posting text with the same guard. The output-storage delta keeps "no access by file path" and "404 where docs are disabled".
- [Base letter missing on a fresh checkout] → 404 and an "unavailable" pane; the generated letter still shows.
- [The page grows] → The switch reuses `pane()`, `showPdf()` and `showEmpty()`; only state for two URLs and the switch is new.

## Migration Plan

1. Archive `add-cover-letter` first so `cover-letter-writing`, `cover-letter-api` and its `output-storage`, `api-docs` and `local-service-hosting` changes are in the main specs; this change's deltas modify those requirements.
2. Deploy as usual (`scripts/install_service.sh`), then run `scripts/smoke_test.sh`, which now expects 13 operations.
3. Rollback: reinstall the previous commit; nothing is stored, so no data migration either way.
