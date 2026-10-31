# Proposal

## Why

Changing an application's status or deleting it in the viewer means opening each application first, which loads its details, scores and two PDFs. Working through many applications (marking several as applied, clearing out stale ones) is slow, and with 20+ applications the list is hard to scan without a way to narrow it.

## What Changes

- Each entry in the left application list gets its own status control and Delete button, so the owner can change a status or delete an application without opening it. They save and confirm exactly as today (same endpoints, same confirmation text, same error handling).
- The status control and Delete button are removed from the detail pane. The detail pane shows the status as plain text. **BREAKING** (UI only): status and delete are no longer available inside the detail view.
- Clicking the rest of a list entry still opens it; using its status control or Delete does not open or change the selection.
- A filter bar above the list narrows it by application status (all, or one of the six statuses) and by the date the application was recorded in the database (`created_at`, a from/to date range), not the posting date.
- The header count shows how many applications match out of the total when a filter is active.
- Filtering happens in the page over the data `GET /applications` already returns. No API, endpoint or OpenAPI change.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `resume-viewer`: "Status changed from the viewer" and "Application deleted from the viewer" move from the selected application's detail pane to every list entry; "Application details shown" shows status as text; a new requirement covers filtering the list by status and recorded date.

## Impact

- `app/viewer.py`: list entry markup (entries can no longer be a single `<button>`, since a `<select>` and a `<button>` cannot nest inside one), list styles, the status and delete controls, the detail card, a new filter bar and filter state, and the header count.
- `tests/test_viewer.py`: page tests for the moved controls and the filter bar.
- No change to `app/main.py`, `app/models.py`, the OpenAPI docs, the smoke test count or the README's endpoint list.
