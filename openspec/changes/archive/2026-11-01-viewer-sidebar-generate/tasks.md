# Tasks

## 1. Baseline

- [x] 1.1 Archive `viewer-fill-form` (it is merged; check its task 3.5 with the owner first, or archive with that box noted). Verify that `openspec/specs/resume-viewer/spec.md` contains "Fill form from the viewer" and that `openspec validate viewer-sidebar-generate` passes.

## 2. Job summaries in the list

- [x] 2.1 Extend `ApplicationStore.list_with_reports` to left-join `generation_jobs` once per kind. Select only `status, started_at, finished_at, error` and return `jobs: {resume, cover_letter}` (null when there is no row). Verify with new `tests/test_applications.py` cases: running, failed and done jobs, no jobs, and a done job whose `saved_path`/`result` never appear.
- [x] 2.2 Add `JobSummary` and `ApplicationListItem.jobs` in `app/models.py`, and update the `GET /applications` description. Verify that a `tests/test_viewer.py` list test sees `jobs` and that `tests/test_docs.py` checks the schema has exactly the four fields per kind, nullable, with no `saved_path`/`match`/`text`.

## 3. Viewer generation endpoints

- [x] 3.1 Build a `generate(request, kind, application)` callable in `create_app` from `start_generation` + `resume_work` / `cover_letter_work`, pass it to `register_viewer`, and move the cover letter 422 message into a shared constant. Verify that the existing `tests/test_api.py` and `tests/test_generation.py` still pass unchanged.
- [x] 3.2 Add `POST /viewer/application/{application_id}/resume` and `.../cover-letter` in `register_viewer`. Order of checks: cross-site 403 first, then 404 for a bad or unknown ID, then 422 for a letter without posting text, then 503 when the store fails, else 202 via `generate`. Tag `viewer`, no body, no security. Verify with `tests/test_viewer.py`: 202 body, already running (including one started by keyed `POST /resume`), resume and letter together, 422, 404, 403 with no job row created, 404 when docs are disabled, keyed `POST /resume` still 401 without a key, the result readable via `GET /resume/{id}/status`, and one `application_request` POST log line with no content.
- [x] 3.3 Update `tests/test_docs.py` to twenty operations, with each new endpoint's statuses (resume: 202/403/404/503; letter: 202/403/404/422/503), no request body or security, and description wording. Update `scripts/smoke_test.sh` and `scripts/test_smoke_test.sh` to twenty. Verify with `pytest tests/test_docs.py` and `scripts/test_smoke_test.sh`.

## 4. Sidebar redesign

- [x] 4.1 Restyle the filter bar. Put a search input on the first row, then the status select and a compact recorded from–to pair, with a Clear button shown only while filtering. Add the search to `filters`/`matches()` (company or role, case-insensitive, trimmed) and to `clearFilters()`. Verify with page tests that the markup has the search field, and check in a browser that typing filters with no network request.
- [x] 4.2 Rebuild each list entry as a single `<button class="entry">` card. Show company plus a right-aligned score coloured against the threshold, the role, a status pill, the match badge and the recorded date. Add a running-job dot ("Resume…"/"Letter…") that doesn't pulse under `prefers-reduced-motion`. Remove the status select, Fill form, Delete and the per-entry notes from cards. Verify with page tests that the list script has no per-entry controls, and check in light and dark mode at 1280 px and 390 px widths.

## 5. Detail action bar and generation UI

- [x] 5.1 Add a sticky action bar to the detail view with the title, status select, Generate/Regenerate resume, Generate/Regenerate cover letter, Fill form and Delete, plus one `aria-live` note line keyed by application ID. Move the status, fill and delete handlers there, keeping their messages; after a delete, clear the selection and the fragment. Verify with updated page tests and, in a browser, a status change, Fill form and a cancelled and a confirmed Delete.
- [x] 5.2 Wire the generate buttons. Use "Regenerate" when a report exists, the job is `done` or the generated PDF loaded, and confirm before regenerating. POST to the viewer endpoint and show the 422/other error message in the note. Disable the button and show "Generating…" while the job runs. Verify in a browser on a test application: first generate sends without a prompt, a cancelled regenerate sends nothing, and the letter without posting text shows the 422 message.
- [x] 5.3 Add list polling every 5 s while any job is `running`, with a single timer and a failed poll keeping the last list. Diff the selected application's jobs: on resume `done`, reload the detail while keeping the current document view (add a keep-document option to `select`); on letter `done`, refresh the letter panes now if they are shown, else on the next switch; on `failed`, show "<Kind> failed: <error>". Verify in a browser with a fast `no_job_description` resume run, check that polling stops afterwards in the network tab, and confirm a job started by the keyed API shows its indicator after reload.
- [x] 5.4 Update the README viewer section (search, action bar, generating from the viewer, job indicator) and the viewer write list. Verify the README names both new endpoints.

## 6. Integration

- [x] 6.1 Run `pytest` and `scripts/test_smoke_test.sh`; both pass.
- [ ] 6.2 Reinstall the service on the Mac mini, run `scripts/smoke_test.sh` (twenty operations), and at `/viewer` regenerate one resume and one cover letter end to end.

## Workflow follow-up

- Open a PR from `viewer-sidebar-generate` to `main`.
- Archive this change after `viewer-fill-form` is archived and the PR is merged.
