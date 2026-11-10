# Tasks

## 1. Store

- [x] 1.1 In `app/applications.py` add the `hidden` column (INTEGER NOT NULL DEFAULT 0) to the schema, `MIGRATION` and `COPIED_COLUMNS`, add `hidden` to `LIST_COLUMNS` (returned as a boolean), and add `set_hidden(application_id, hidden)` that also sets `updated_at` and returns the new value or None if absent. Keep `hidden` out of `UPDATABLE_FIELDS`. Verify with new tests in `tests/test_applications.py`: default visible, survives update/duplicate/email status, keyed PATCH ignores `hidden`, old store without the column migrates with all rows visible and a second startup changes nothing, integer-ID migration keeps the flag.

## 2. Endpoint and API docs

- [x] 2.1 Add request/response models and an example in `app/models.py` (`hidden` strictly boolean, message names the field and never echoes the value) and `PUT /viewer/application/{application_id}/hidden` in `app/main.py`, registered only with the viewer, reusing the same-origin check, UUID parsing and 404-before-422 order. Document `hidden` on the list entry schema. Verify with tests in `tests/test_api.py`/viewer tests covering every scenario of "Viewer hide endpoint" and "Viewer hide validation and guards", plus docs-disabled 404 and re-recording a hidden link staying hidden.
- [x] 2.2 Update docs: tag, no security, 200/403/404/422/503, bool body example, description (viewer-only, cross-site refused, only the flag changes); bump `tests/test_docs.py` operation lists and status sets to twenty-three; update `scripts/smoke_test.sh` and `scripts/test_smoke_test.sh` to twenty-three (keep the twenty-two stub as a failing case); update the README endpoint list. Verify with `pytest tests/test_docs.py`, `bash scripts/test_smoke_test.sh`.

## 3. Viewer UI

- [x] 3.1 In `app/viewer.py` add `hidden` handling to the list: `showHidden` state (off on load), `matches()` leaves out hidden items unless on, "Show hidden (N)" checkbox under the status select (shown when N > 0 or while on, not reset by Clear), muted style and a "Hidden" pill on hidden entries, header count `N applications · M hidden` per the spec (including the "x of y" form), and the "All applications are hidden." empty state. Verify with viewer page tests (markup contains the control and styles; script-level checks following the existing viewer test approach) and by loading the page against sample data.
- [x] 3.2 Add the Hide/Unhide button before Delete in `actionBar`, non-destructive style, no confirm, disabled while busy; on success update the item, list, count and note ("Hidden"/"Unhidden") without losing the selection; on failure show "Not saved: …" and keep state. Verify with tests for the request sent, the failure path and no Hide control on list entries, then manually in the browser: hide, see it vanish and the count suffix, Show hidden, Unhide.

## 4. Integration

- [ ] 4.1 Run the full test suite and `openspec validate hide-applications --strict`; check the viewer in the browser at desktop and narrow widths (filter column, action bar wrapping with the extra button) and with the real store migrated from a copy. Verify all pass and the layout is not broken.
