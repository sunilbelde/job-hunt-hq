# Proposal

## Why

The viewer lists every application ever recorded. Rejected, withdrawn or simply irrelevant postings pile up and bury the live ones, and the only way to clear them is Delete, which is permanent and also loses the report and history. The owner wants to put an application out of sight and still be able to bring it back.

## What Changes

- Add a **hidden** flag to every application, stored with the row so it survives reloads, restarts and other browsers. Hiding is independent of status.
- Viewer list: hidden applications are left out by default. A **"Show hidden (N)"** checkbox under the status filter adds them back, dimmed and tagged "Hidden". The header count covers visible applications and notes how many are hidden.
- Viewer action bar: a **Hide** button beside Delete on the selected application, which becomes **Unhide** when it is hidden. No confirmation, since it is reversible. The selected application stays open after hiding so the owner sees what happened.
- New viewer-only endpoint `PUT /viewer/application/{application_id}/hidden` with `{"hidden": true|false}`, guarded like the other viewer writes.
- `GET /applications` entries gain a `hidden` boolean. The keyed API list is otherwise unchanged and still returns hidden applications.
- Existing stores gain the column in place; every existing row reads not hidden.
- API docs, docs tests and the smoke test operation count (22 → 23) are updated in the same change.

Out of scope: hiding from the keyed API, bulk hide, auto-hiding on `rejected`/`withdrawn`, and any effect on generation, form filling, email status matching or duplicate detection (a hidden application keeps matching and stays hidden if its link is posted again).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `resume-viewer`: hide/unhide endpoint and its guards, list default, show-hidden control, Hidden tag, Hide/Unhide action, counts.
- `application-store`: hidden flag stored per row, preserved across updates, added to existing stores.
- `api-docs`: the new operation is documented and counted (twenty-three); `hidden` in the list is documented.
- `local-service-hosting`: the smoke test expects twenty-three operations.

## Impact

- `app/applications.py` (column, migration, list column, setter), `app/models.py` (request/response models), `app/main.py` (endpoint), `app/viewer.py` (page markup, list filter, action bar).
- `scripts/smoke_test.sh`, `scripts/test_smoke_test.sh`, `tests/test_docs.py`, viewer/API/store tests, README endpoint list.
- No new dependencies. Personal data stays local; nothing new is exposed on the public listener.
