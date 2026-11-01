# Proposal

## Why

The Funnel address is on the public internet and its only guard is the API key, yet it still serves every keyed API endpoint, though Muse uses only four of them. The docs and viewer listener is also published to the tailnet, though the owner now uses the viewer only on the Mac mini. Each extra endpoint or listener reachable from off the Mac is attack surface with no user. Cutting both down to what is used shrinks what a leaked key or a tailnet device can reach.

## What Changes

- **BREAKING** The public listener (the one Funnel publishes) serves only:
  - `GET /health`
  - `POST /application`
  - `POST /resume`
  - `POST /cover-letter`

  Every other path answers 404 there, as an unknown path would, whatever `X-API-Key` the request carries. That covers `GET /healthz`, `PATCH`/`DELETE /application/{id}`, `GET /resume/{id}/status` and `GET /cover-letter/{id}/status`, plus the docs and viewer paths that are already 404.
- **BREAKING** The second listener (today the "docs port", 8081) becomes loopback-only. The install script no longer suggests a `tailscale serve` mapping for it and instead warns, both at install and in the status script, when any Tailscale serve or Funnel mapping still proxies it. It keeps serving the full API, the API reference and the viewer at `http://127.0.0.1:8081`. Nothing in the API itself changes there.
- **BREAKING** `DOCS_PORT=off` is no longer accepted. Without the local listener, nothing could read job status or edit and delete applications, so the install script refuses `off`.
- The viewer keeps calling only same-origin, relative paths, so opened at `http://127.0.0.1:8081/viewer` it uses only loopback endpoints. Its text, the API reference descriptions and the README no longer mention tailnet access, and the reference says which four operations are also on the public address.
- The smoke test checks that the public address answers 404 for the moved endpoints. It uses an all-zero UUID for those probes, so a `DELETE` can never hit a real row. It polls the resume status and edits and deletes its application on the local listener, and `DOCS_URL=off` is no longer supported.
- The install script's post-start check adds a probe that a moved endpoint answers 404 on the public port and is present on the local port.
- The development server (`uvicorn app.main:create_app`) is unchanged: it still serves the full API, with or without docs. Only the installed public listener is restricted.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `local-service-hosting`: the public listener is restricted to the four Funnel endpoints, and the docs listener becomes a loopback-only local listener with no tailnet mapping. The changes reach the install, status and smoke test requirements and remove `DOCS_PORT=off`.
- `generation-jobs`: the status endpoints are served on the local listener only, no longer on the public port.
- `job-api`: on the public listener only `GET /health` answers. `GET /healthz` stays on the local listener and the development server.
- `resume-viewer`: the keyed `PATCH`/`DELETE /application/{id}` no longer behave the same "on every listener". The public listener does not serve them.
- `api-docs`: the reference states which operations the public address serves, and its descriptions drop "served on the public address too" and the tailnet wording.

## Impact

- Code:
  - `app/main.py`: `create_app` gains a public-only mode that registers just the four routes.
  - `app/serve.py`: builds the public app in that mode.
  - `app/viewer.py`: docstring and page wording.
- Scripts:
  - `scripts/install_service.sh` and `scripts/service_status.sh`: no tailnet docs mapping, a warning when a mapping exists, and `DOCS_PORT=off` removed.
  - `scripts/smoke_test.sh`: public 404 probes, and status, `PATCH` and `DELETE` via the local listener.
  - `scripts/uninstall_service.sh`: no reminder to remove the docs mapping.
  - Their shell tests.
- `deploy/tailscale_docs.py`: still used, now only to detect a mapping that should not exist.
- Tests: `tests/test_serve.py`, `tests/test_api.py`, `tests/test_docs.py`, `scripts/test_install_service.sh`, `scripts/test_smoke_test.sh`.
- Docs: README endpoint table, the hosting section and the "API docs on the tailnet" section, plus the OpenAPI descriptions. The operation count on the local listener stays at eighteen.
- Ops: after reinstalling, the owner runs `tailscale serve --https=8444 off` to remove the old docs mapping. The install and status scripts warn until it is gone. Muse keeps working unchanged, as long as it calls only the four endpoints.
- Coordination: builds on `viewer-fill-form` (still open, 9/10 tasks), whose fill endpoint makes eighteen operations. That change should be archived first, or the two archived in order.
