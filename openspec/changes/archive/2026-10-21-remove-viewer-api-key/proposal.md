# Proposal

## Why

The resume viewer asks for the API key every time the page loads, because it keeps the key only in memory. The viewer and its four read endpoints exist only on the docs listener, which Tailscale publishes to the owner's tailnet alone; the public Funnel address answers 404 for all of them. Being on the tailnet already restricts who can reach the viewer, so the key prompt adds friction and almost no protection.

## What Changes

- `/viewer` loads the application list straight away, with no key prompt, no key held in the page and no `X-API-Key` header on its requests.
- **BREAKING** (contract only): `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf` and `GET /resume/base.pdf` no longer require or check `X-API-Key`. A missing or wrong key is ignored, and they never answer 401.
- These four reads stay registered only where API docs are enabled. The public listener still answers 404 for them, so nothing new reaches the internet.
- Every write endpoint (`POST /application`, `PATCH`/`DELETE /application/{id}`, `POST /resume`) still requires the key on both listeners.
- The OpenAPI document drops the security requirement and the 401 response from the four viewer reads. The operation count stays at ten.
- The README's viewer section and the tailnet docs note no longer tell the owner to enter the key in the viewer. They state that anyone on the tailnet can read the viewer's data.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `resume-viewer`: the page no longer asks for or sends a key, and the list, detail, saved-resume and base-resume reads no longer require one.
- `api-docs`: the documented error statuses and security scheme no longer include the key or a 401 for the four viewer reads.
- `local-service-hosting`: the tailnet viewer scenario opens without entering a key.

## Impact

- `app/main.py`: `register_viewer` endpoints lose the key check and the `Security(api_key_header)` parameter, and the API description stops saying every endpoint needs the key.
- `app/viewer.py`: the key gate form, the `apiKey` state, `lock()` and the 401 handling are removed. The page loads the list on start.
- `tests/test_viewer.py`, `tests/test_docs.py`: the key-required tests become "reads work without a key" tests, and the docs expectations change.
- `README.md`: the viewer section and the tailnet docs listener notes.
- `scripts/smoke_test.sh`: no change needed (the operation count is still 10, and `/viewer` is still 404 on the public address).
- Security: anyone signed into the owner's tailnet can read every application, posting text and resume through the docs port. That is fine while the owner is the only person on the tailnet. If that changes, the tailnet policy rule for `tcp:8444` that the README already describes becomes the guard.
