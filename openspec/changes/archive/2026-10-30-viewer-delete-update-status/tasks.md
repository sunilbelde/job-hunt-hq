# Tasks

## 1. Viewer write endpoints

- [x] 1.1 Add `ViewerStatusUpdate` (required `status: ApplicationStatus`, extra fields ignored, with a docs example) to `app/models.py`, and a `403` entry in `ERROR_DESCRIPTIONS` in `app/main.py`; verify `tests/test_models.py` gets a case that accepts `{"status": "applied"}`, ignores extra fields and rejects `"ghosted"` and a missing `status`
- [x] 1.2 Add the `same_origin(request)` helper (`Sec-Fetch-Site` first, then `Origin` against `Host`, allow when neither is present) and extend `request_event` so `/viewer/application/…` logs as `application_request` while `/viewer` still logs nothing; verify with unit tests for each header combination and for both paths in `request_event`
- [x] 1.3 Register `PATCH /viewer/application/{application_id}` in `register_viewer`: guard (403), then ID parse (404), then JSON content type and body (422, unknown ID still 404), then `applications.update(id, {"status": ...})` (503 on store error), returning `{ok, application_id, status}`; verify with new `tests/test_viewer.py` tests covering every scenario of "Viewer status update endpoint", "Viewer status update validation" and the PATCH cases of "Viewer writes for unknown applications"
- [x] 1.4 Register `DELETE /viewer/application/{application_id}` in `register_viewer` with the same guard and ID handling, calling `applications.delete` and keeping all files; verify with tests for deleted → later GET 404, delete twice, not a UUID, store unavailable, re-record gives a new ID, and the resume and cover letter PDFs still on disk
- [x] 1.5 Add tests for the cross-site guard on both endpoints (`Sec-Fetch-Site: cross-site` and `same-site` → 403, foreign `Origin` without `Sec-Fetch-Site` → 403, `same-origin` → processed, no headers → processed, an `OPTIONS` preflight carries no `Access-Control-Allow-Origin`), and for docs disabled → 404 with or without a valid key, and keyed `DELETE /application/{id}` without a key still 401 with docs enabled; verify `pytest tests/test_viewer.py tests/test_api.py` passes
- [x] 1.6 Update `test_reads_change_nothing` and `test_each_read_logged_once_without_content` (or add siblings) so writes log one `application_request` line with method, status and ID and never the status value, a refused or non-UUID write logs no path ID, and a write leaves the output folder unchanged; verify `pytest tests/test_viewer.py` passes

## 2. API docs, smoke test and README

- [x] 2.1 Give both routes `tags=["viewer"]`, a summary, a description (served only with the viewer, no key, refuses cross-site requests, the delete keeps generated files), `responses=` (PATCH: 200, 403, 404, 422, 503; DELETE: 200, 403, 404, 503) and `openapi_extra=json_body(ViewerStatusUpdate, …)` for the PATCH, with no security requirement; verify `/openapi.json` on a docs-enabled dev server shows them as described
- [x] 2.2 Update `tests/test_docs.py`: add both operations to `RESPONSES`, rename and change the count test to seventeen, keep them out of `PROTECTED`, add the path to the docs-disabled 404 parametrisation, and add checks for the status body enum, the example being accepted and the description wording; verify `pytest tests/test_docs.py` passes
- [x] 2.3 Change `scripts/smoke_test.sh` from 15 to 17 operations (comment, check and failure message); verify with `bash -n scripts/smoke_test.sh` and by grepping that no `15` operation count is left
- [x] 2.4 Update the README "Resume viewer" section (no longer read-only: status control and Delete with confirm, the two key-free write endpoints, docs listener only, files kept on delete) and the access-control paragraph under hosting; verify the README matches the docs descriptions and mentions no public-address viewer write

## 3. Viewer page

- [x] 3.1 Extend `api()` in `app/viewer.py` to take `{method, body}` (sends JSON with `Content-Type: application/json`, keeps `credentials: "omit"` and `cache: "no-store"`); verify the existing page tests still pass and the page source has no `X-API-Key`
- [x] 3.2 Replace the Status row in `detailsCard` with a `<select>` of the six statuses that sends the PATCH on change, is disabled while saving, updates the `applications` entry and `renderList()`, shows "Saved", and on error puts the old value back and shows the message, all with `textContent`; verify with a page-source test asserting the six options and the `/viewer/application/` PATCH call, and by hand on a dev server (`API_DOCS_ENABLED=true`)
- [x] 3.3 Add a Delete button to the details card that runs `confirm("Delete <company> – <role>? This cannot be undone.")`, sends the DELETE only on confirm, then removes the entry, revokes blob URLs, clears `selected` and the fragment, re-renders the list and count and resets the detail pane, or shows the error inline; verify with a page-source test for `confirm(` and the DELETE call, and by hand: cancel sends nothing, confirm removes the entry, reload keeps it gone
- [x] 3.4 Add the styles for the select, the Delete button (danger colour from the existing `--bad` tokens, light and dark) and the inline saved and error notes in the nonce-tagged stylesheet; verify `test_policy_allows_only_its_own_script_and_style` and `test_page_loads_nothing_from_another_origin` still pass, and that the page has no inline `style=` or `on*=` attributes

## 4. Integration

- [x] 4.1 Run the full suite with `pytest`; verify it passes with no skipped viewer or docs tests
- [x] 4.2 On a docs-enabled dev server, change one application's status and delete another from `/viewer` in a browser; verify the log has one `application_request` line per write with no status value, and `GET /applications` reflects both
- [x] 4.3 Run `openspec validate viewer-delete-update-status --strict`; verify it passes

## Workflow follow-up

- After merge and reinstall, run the smoke test against the installed service and confirm it reports 17 operations on the docs listener and 404 for `/viewer/application/<id>` on the public address.
- When archiving, update the `resume-viewer` main spec's Purpose: it is no longer "read-only", since it can now change status and delete.
- Open a PR from `viewer-delete-update-status` to `main`.
