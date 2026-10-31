# Design

## Context

- `register_viewer` in `app/main.py` adds the viewer page and its key-free reads only when `settings.api_docs_enabled`. On the installed service that means only the tailnet docs listener on `127.0.0.1:8081`. The public Funnel listener always runs with docs off. That registration is the reads' only guard, and the new writes reuse it.
- The keyed `PATCH` and `DELETE /application/{id}` check the key before anything else. The docs port runs them unchanged ("Try it out uses the same API"), so they cannot quietly skip the key there.
- The store already has the operations needed: `ApplicationStore.update(id, {"status": ...})` returns the new status, and `ApplicationStore.delete(id)` removes the row, its report and its job state in one transaction. Neither touches files.
- The page script uses `fetch` with `credentials: "omit"`, builds every node with `textContent`, and the CSP allows `connect-src 'self'` and no inline handlers. `form-action 'none'` blocks form posts. The page has no modal or toast component yet.

## Goals / Non-Goals

**Goals:**
- Two narrow writes (status and delete) callable from the viewer without the key, existing only where the reads already exist.
- No change to the keyed API, the public listener or the store schema.

**Non-Goals:**
- Editing other fields (salary, notes and so on) from the viewer.
- Deleting generated PDFs, or cleaning up orphaned output folders.
- Bulk actions, undo, or a soft-delete or archive state.
- Rate limiting or auth for the tailnet docs port.

## Decisions

**Separate `/viewer/application/{id}` paths, not a key bypass on the existing routes.** Letting `PATCH`/`DELETE /application/{id}` skip the key on the docs listener would break the "same API on both ports" rule. It would also turn a docs flag into an auth switch for the full update body. With new paths, the key-free surface is just these two status-only operations, and on the public listener they don't exist at all, so they fall through to the normal 404. The `/viewer/` prefix also makes them obvious in logs and in the docs. Alternatives considered: the page asks for the key and calls the existing routes (rejected by the owner, and it breaks "viewer never asks for a key"); `POST /application/{id}/status` (shares the keyed resource path, which makes the 405/404 handling for docs-off harder).

**Status-only body model.** Add `ViewerStatusUpdate(BaseModel)` with `status: ApplicationStatus` (required) and pydantic's default `extra="ignore"`. Write it with `applications.update(id, {"status": value})`. Ignoring extra fields, instead of rejecting them, matches the existing update rules. Building the change dict from `status` alone means nothing else can ever reach the store. Reuse `validation_message` so the 422 names `status` and doesn't echo the value.

**Cross-site guard as a small helper run first.** `same_origin(request) -> bool` does this:
- If `Sec-Fetch-Site` is present, return true only when it is `same-origin`.
- Otherwise, if `Origin` is present, compare its `host[:port]` to the `Host` header.
- Otherwise (curl and other non-browser clients), allow.

`Sec-Fetch-Site` comes first because every current browser sends it, and it doesn't depend on whether Tailscale serve keeps the original `Host`. The `Origin` fallback only covers older browsers. `PATCH` and `DELETE` already need a CORS preflight, and the app has no CORS middleware, so a cross-origin browser call can't get through anyway. The guard is defence in depth and also covers a form or `navigator.sendBeacon` style misuse. The status write also requires `Content-Type: application/json`, which `read_update`-style parsing would otherwise not check.

**Check order:** guard (403) → parse the ID (404) → for `PATCH`, read and validate the body. On a bad body, check `exists` so an unknown ID still gets 404, the same pattern as `update_application`. Then the store call, with 503 on `ApplicationStoreError`. Set `request.state.application_id` only after the UUID parses, so logs never carry a raw path value.

**Logging:** extend `request_event` so paths starting with `/viewer/application/` map to `application_request`. `/viewer` itself must still return `None`, so match the longer prefix only.

**UI.**
- In `detailsCard`, the "Status" row becomes a `<select>` with the six values. Its `change` listener sends the `PATCH`. While it's in flight the select is disabled. On success, update the `applications` array entry and call `renderList()`, then show a short inline "Saved". On failure, put the select back to its previous value and show the message in an inline note beside it.
- A "Delete" button sits in the details card header. It uses the native `confirm()` with "Delete <company> – <role>? This cannot be undone." No new modal is needed, and `confirm` is allowed under the CSP. On success, remove the entry from `applications`, revoke this application's blob URLs, clear `selected` and the URL fragment (`history.replaceState`), re-render the list and count, and reset `#detail` to "Select an application." On failure, show the message inline.
- `api()` grows an options argument (method and body) instead of a second fetch helper, and keeps `credentials: "omit"` and `cache: "no-store"`.
- Every new label is set with `textContent`, so a company name can't inject markup. `confirm()` takes a plain string.

**Docs:** both routes get `tags=["viewer"]`, a summary, a description and `responses=` with `errors(403, 404, 422, 503)` or `errors(403, 404, 503)`. The `PATCH` gets `openapi_extra=json_body(ViewerStatusUpdate, ...)` and has no `Security` dependency. The 403 example message is added wherever the error examples are built. The success models are the existing `ApplicationUpdated` and `ApplicationRecorded`.

## Risks / Trade-offs

- [Anyone on the tailnet can delete or relabel applications without the key] → This is the same trust boundary that already exposes every posting, resume and report on that port. The public listener is unaffected, and the tests assert 404 there.
- [DNS rebinding against `127.0.0.1:8081` from a malicious page] → The browser would see it as same-origin. This risk already exists for the reads. Not addressed here; a `Host` allow-list for the docs listener is a possible follow-up.
- [Deleting while a generation job is running] → `delete` removes the job row. The finished job's `finish_job` then updates nothing, and its PDF is still written to the output folder. This is how the keyed `DELETE` already behaves. Accepted.
- [Native `confirm()` is plain and can be suppressed by the browser] → If it is suppressed, `confirm` returns false and nothing is deleted, which is the safe failure.
- [Status in the list goes stale if another client changes it] → It's refreshed on reload, as it is today.

## Migration Plan

No data migration. Deploy by reinstalling the service as usual. The smoke test then expects 17 operations on the docs listener. To roll back, revert the commit and reinstall. Rows deleted in the meantime stay deleted.
