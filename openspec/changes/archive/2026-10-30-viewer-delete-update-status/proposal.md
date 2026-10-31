# Proposal

## Why

The resume viewer is where the owner reviews every application, but it is read-only: to mark one as applied or drop a stale one they have to leave the page and send `PATCH` or `DELETE /application/{id}` with the API key from Swagger or curl. Changing status and deleting should happen where the list already is.

## What Changes

- The viewer shows the selected application's status as a control with the six statuses. Choosing another status saves it at once, and the list badge updates without a reload.
- The viewer gets a Delete button on the selected application. It asks for confirmation that names the company and role. After the delete, the application leaves the list and the detail pane is cleared.
- Two new key-free endpoints, registered only where the viewer is (docs enabled, so on the installed service only the tailnet docs listener):
  - `PATCH /viewer/application/{application_id}` with body `{"status": "<status>"}` changes only the status.
  - `DELETE /viewer/application/{application_id}` removes the application and its report, like the existing `DELETE`. Generated PDFs stay in the output folder.
- Both refuse requests a browser marks as cross-site, and the status write accepts only a JSON body. This stops another website the owner visits from triggering them.
- The existing keyed `PATCH` and `DELETE /application/{application_id}` stay exactly as they are. The public listener gets no new paths.
- The "Viewer reads never change data" rule is narrowed: browsing still changes nothing, and only the two explicit actions write.
- The OpenAPI document grows from fifteen to seventeen operations. The docs tests, smoke test count and README change with it.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `resume-viewer`: adds the status control, the delete action and the two key-free write endpoints with their cross-site guard and logging. Narrows "Viewer reads never change data" so the explicit actions may write.
- `api-docs`: endpoint coverage goes from fifteen to seventeen operations. The docs-disabled list gains the two viewer write paths.
- `local-service-hosting`: the public address also refuses the viewer write paths. The smoke test expects seventeen operations.

## Impact

- `app/main.py`: two routes in `register_viewer`, plus `request_event` so `/viewer/application/…` logs as `application_request`.
- `app/models.py`: a status-only body model and an example for the docs.
- `app/viewer.py`: status select, delete button, confirm dialog and the write calls. The CSP's `connect-src 'self'` already allows them.
- `tests/test_viewer.py`, `tests/test_docs.py` (`RESPONSES`, count 17), `scripts/smoke_test.sh` (15 → 17), README viewer section.
- Security: on the tailnet docs port, anyone on the tailnet can now change a status or delete an application without the key. They can already read everything there. The public Funnel address is unchanged.
