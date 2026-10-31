# Tasks

## 1. Status and delete on list entries

- [x] 1.1 In `app/viewer.py`, restructure each list entry into `<div class="entry" data-id>` with a `<button class="open">` (company, role, badges, scores; carries `aria-current`) and a controls row. Narrow the `#list` click handler to `button.open`. Verify that clicking an entry still selects it and updates the URL fragment.
- [x] 1.2 Build `statusControl` and `deleteButton` for each entry from its list item. Keep the PATCH/DELETE request literals and the confirm text unchanged. A status save updates the list item, and the detail's status text when that application is selected. Keep the inline "Saved"/error note in a per-ID map so `renderList()` keeps it. Verify that using either control does not change the selection or load another application.
- [x] 1.3 Make `detailsCard` show the status as text and drop the Delete button and the `.title-row .delete-control` style. Add compact entry-control styles with no inline `style=` or `on*=` attributes. Verify that `test_page_has_no_inline_styles_or_handlers` still passes.
- [x] 1.4 Update the page tests in `tests/test_viewer.py`: entries are `button.open` inside `.entry`, the list renders the status control and Delete, and `detailsCard` no longer calls `statusControl`/`deleteButton`. Keep `test_page_changes_status_and_deletes`. Verify with `.venv/bin/python -m pytest tests/test_viewer.py`.
- [x] 1.5 Update the README viewer section so status and Delete are described on each list entry, not in the selected application's details. Verify that the section no longer places them under "For the selected one it shows".

## 2. Filters

- [ ] 2.1 Add a filter bar above the list (an `<aside>` wrapping the bar and `#list`) with a status `<select>` ("All statuses" plus the six statuses) and "Recorded from"/"Recorded to" `<input type="date">`. Bind them to a `filters` object that re-renders the list on change. Verify that the bar stays fixed while the list scrolls, and that the mobile layout still stacks.
- [x] 2.2 Filter in `renderList()`: match by status, and by the local calendar day of `created_at` (inclusive, either end optional), never by `date_posted`. Re-filter after a status save. Verify by hand that a status change out of the active filter removes the entry, and that no request is sent when a filter changes.
- [x] 2.3 Add `updateCount()` ("N applications", or "M of N applications" when any filter is set) and use it in `loadList` and `removed`. Add the no-match message with a "Clear filters" button that resets all three filters. Verify that the selected application's details stay shown when its entry is filtered out.
- [x] 2.4 Add page tests: the filter bar markup, the status options, filtering on `created_at` and not `date_posted`, the "of" count text and the "Clear filters" control. Verify with `.venv/bin/python -m pytest tests/test_viewer.py`.
- [x] 2.5 Document the filters in the README viewer section: status, and recorded date as distinct from the posting date. Verify that the README matches the page labels.

## 3. Integration check

- [ ] 3.1 Run the full suite with `.venv/bin/python -m pytest` and confirm it passes. Confirm that `git diff --stat` touches no file under `app/main.py`, `app/models.py`, `scripts/` or the docs tests.
- [x] 3.2 Run the dev server with `API_DOCS_ENABLED=true`, open `/viewer` and check each case:
  - changing an unselected entry's status keeps the current selection;
  - deleting the selected entry clears the detail pane, and deleting another entry does not;
  - a failed write shows the error on its entry;
  - the status filter, the date filter and both together narrow the list correctly.
