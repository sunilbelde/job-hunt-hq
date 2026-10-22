# Design

## Context

The four viewer reads are registered by `register_viewer` in `app/main.py`, and only when the app is built with docs enabled. On the installed service that is only the docs listener (`127.0.0.1:8081`, published by `tailscale serve` on `:8444` to the tailnet). The public listener (`:8080`, behind Funnel) is always built without docs, so those paths answer 404 there, and the stub `GET /application/{id}` returns 404 for the PATCH/DELETE path. The app picks docs vs. public by the local port, which no header can change. A development server (`uvicorn ... --port 8080` with `API_DOCS_ENABLED=true`) binds to `127.0.0.1` by default.

Today each viewer read checks `api_key_valid(x_api_key)` through a `Security(api_key_header)` parameter, which also makes the OpenAPI document mark the operation as needing the key. The page in `app/viewer.py` shows a key form (`#gate`), keeps `apiKey` in memory, sends it as `X-API-Key`, and on any 401 calls `lock()` to show the form again.

## Goals / Non-Goals

**Goals:**
- The viewer opens straight to the list on every load.
- The access boundary for the viewer's data is "reachable on the docs listener", with no key.
- The public listener stays unchanged: viewer paths answer 404 there, and writes need the key.

**Non-Goals:**
- Changing the key on any write endpoint, or on `/docs` "Try it out".
- Identifying tailnet users (e.g. through `Tailscale-User-Login` headers) or adding any other auth.
- Rate limiting.

## Decisions

**Drop the key check from the endpoints rather than only from the page.** The page could keep the key in localStorage instead, but the owner chose to have no key. If the page sent no key while the endpoints still required one, nothing would load, so the endpoints have to stop checking. Remove the `x_api_key: ... = Security(api_key_header)` parameter and the `api_key_valid` check from the four reads. Removing the parameter also removes the security requirement from their OpenAPI operations, so the docs follow from the code. Remove `401` from their `errors(...)` lists. `register_viewer` no longer needs the `api_key_valid` argument, so drop it from the signature and the call.

**Ignore a sent key instead of rejecting a wrong one.** An endpoint with no key requirement should not answer 401 just because someone sent a bad header. Rejecting it would also keep a reason for 401 handling in the page.

**Keep the docs-only registration as the guard.** `register_viewer` stays behind `if docs:`, and the 404 stub stays for the public app. Update the docstring and the `/viewer` comment so they say the tailnet boundary is the only protection and the page needs no key.

**Simplify the page.** Remove the `#gate` form and its CSS, the `apiKey` variable, `Unauthorized`, `lock()` and the 401 branch in `api()`. Fetches keep `cache: "no-store"` and `credentials: "omit"` and send no headers. On load the page calls `loadList()` directly. A failed load shows its message in the existing status/detail area with a retry button, because the gate form that used to show load errors is gone. The `hashchange` handler drops its `apiKey !== null` guard. Keep the strict CSP and nonce.

**API description.** Change "Every endpoint except the health checks needs the `X-API-Key` header" to say the health checks and the viewer reads need no key.

## Risks / Trade-offs

- [Anyone on the tailnet can read all applications, posting texts and resumes] → Accepted, because the owner is the only tailnet member. The README tells the owner to restrict `tcp:8444` in the tailnet policy file if that changes.
- [A future change registers the viewer on the public app, or Funnel gets pointed at the docs port] → This now leaks data without any key. The existing guards still cover it: the tests check that the reads 404 without docs, the smoke test checks that `/viewer` is 404 on the public URL, the install and status scripts warn if the docs mapping is Funnel-enabled, and Funnel cannot publish 8444. Add a test that sends the reads with no key to a no-docs app and expects 404, so the guard is checked without relying on a key.
- [A dev server started with `--host 0.0.0.0` and docs enabled would expose the reads to the LAN] → The README's dev command doesn't pass `--host`, so it binds to loopback. Add a line to the README saying the viewer reads have no key.

## Migration Plan

Deploy by pulling to the Mac mini and restarting the launchd service (`scripts/install_service.sh`, or `launchctl kickstart`). No data or config changes. To roll back, revert the commit and restart. Clients that still send `X-API-Key` to the viewer reads keep working.
