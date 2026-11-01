# Tasks

## 1. Public listener allowlist

- [x] 1.1 Add `public_only(app)` to `app/serve.py`. For `http` and `websocket` scopes it passes only exact `(GET, /health)`, `(POST, /application)`, `(POST, /resume)` and `(POST, /cover-letter)`. Everything else gets the app's unknown-path 404 (`{"detail": "Not Found"}`, JSON). Lifespan and other scopes pass through. Wrap the public app with it in `main()`. Verify with `pytest tests/test_serve.py`.
- [x] 1.2 In `tests/test_serve.py`, update the `apps` fixture so the public app is wrapped. Add tests for each of these, and verify with `pytest tests/test_serve.py`:
  - each of the four pairs reaches the app on the public port (not 404)
  - every other operation in the docs app's `/openapi.json`, plus `GET /healthz`, returns 404 on the public port, with or without a valid key; this case gets an existing application with a finished job, which must be unchanged afterwards
  - `GET /resume` and `PUT /application` return 404, not 405
  - a blocked path's 404 matches the app's own 404 for a random path in status, body and content type
- [x] 1.3 Update `test_api_same_on_both_ports` and `test_one_resume_run_across_both_ports` to use only the allowed endpoints on the public port, with status reads on the docs port. Extend `test_launcher_serves_both_ports` to assert that `GET /healthz` and `GET /resume/<zero uuid>/status` return 404 on the public port and are served on the docs port. Verify with `pytest tests/test_serve.py`.
- [x] 1.4 Run `pytest tests/test_api.py` to confirm the development app (`create_app` without the wrapper) still serves every endpoint, `/healthz` and the status endpoints included.

## 2. API reference and viewer wording

- [x] 2.1 In `app/main.py`:
  - add a paragraph to `DESCRIPTION` saying the public address serves only the four operations and that the rest are served only on the Mac's local listener
  - remove "Served on the public address too" (or similar) from `status_description`, and say the endpoints are local-only
  - replace "tailnet docs listener" in the viewer-writes text with "local listener"
  - update the comments and docstrings at lines ~183, ~249, ~311 and ~791 that call the status endpoints public or the docs tailnet-only

  Verify with `grep -n -i tailnet app/main.py`, which should return no description text.
- [x] 2.2 In `app/viewer.py`, update the module docstring, and any page copy that mentions the tailnet, to describe the loopback-only listener. Verify with `grep -n -i tailnet app/viewer.py`, which should return nothing.
- [x] 2.3 In `tests/test_docs.py`, add tests and keep the existing 18-operation test passing. Verify with `pytest tests/test_docs.py`:
  - the top-level description names the four public operations
  - both status descriptions say local-only
  - no operation description contains "tailnet"
- [x] 2.4 In `tests/test_viewer.py`, add a test that the served page's HTML and script contain no absolute `http://` or `https://` URL other than the blob, data and CSP keywords it already uses. Verify with `pytest tests/test_viewer.py`.

## 3. Install, status and uninstall scripts

- [x] 3.1 In `scripts/install_service.sh`:
  - refuse `DOCS_PORT=off`: exit non-zero, saying the local listener is required for job status and the viewer, and install nothing
  - remove the `sed` branch that strips `--docs-port`
  - update the usage header
- [x] 3.2 Extend the install script's post-start checks so `GET /healthz` and `GET /resume/00000000-0000-0000-0000-000000000000/status` on the public port must return 404, failing with the path otherwise.
- [x] 3.3 Invert the install script's Tailscale docs check, using `deploy/tailscale_docs.py` exit codes:
  - 1: print nothing
  - 0: warn that the docs and viewer are reachable from the tailnet, and print `tailscale serve --https=<port> off`
  - 3: warn that they are public, and print the `tailscale funnel` off command, then the serve-off command

  Print only the local docs and viewer URLs.
- [x] 3.4 In `scripts/service_status.sh`:
  - show `docs: ok (http://127.0.0.1:<port>/docs, local only)` when no mapping exists
  - warn with the removal command for exit codes 0 and 3
  - report a plist without `--docs-port` as `docs: not configured; reinstall` and exit non-zero
- [x] 3.5 In `scripts/uninstall_service.sh`, drop the `tailscale serve --https=8444 off` reminder.
- [x] 3.6 Update `scripts/test_install_service.sh` and verify with `sh scripts/test_install_service.sh`:
  - the default stub serve JSON has no 8081 mapping
  - the default install prints local URLs and no tailnet URL or docs warning
  - `DOCS_PORT=off` is refused and installs nothing
  - a leftover `:8444` mapping produces the warning and the serve-off command
  - a Funnel mapping on the docs port still warns
  - the public port answering `/healthz` with 200 fails the install
  - the status script shows `local only`, warns on a leftover mapping, and reports an old `off` plist as not configured
  - uninstall no longer mentions 8444

## 4. Smoke test

- [x] 4.1 In `scripts/smoke_test.sh`:
  - refuse `DOCS_URL=off` with exit 2 and the usage text
  - add public-address 404 checks for `GET /healthz`, `GET /resume/<zero uuid>/status` and `GET /cover-letter/<zero uuid>/status`, plus keyed `PATCH` and `DELETE /application/<zero uuid>`, all before any application is created
  - send the leftover-text `PATCH`, the status polling and the cleanup `DELETE` to `$docs`
  - keep `POST /application`, `/resume` and `/cover-letter` on `$base`
  - update the header comment and usage
- [x] 4.2 Update `scripts/test_smoke_test.sh` so its stub serves the moved endpoints only on the docs URL, then verify with `sh scripts/test_smoke_test.sh`. Replace the `DOCS_URL=off skips` case with "`DOCS_URL=off` is refused". Add cases where the run fails:
  - the public stub answers `/healthz` with 200
  - the public stub answers `DELETE /application/<zero uuid>` with anything but 404
  - status is only served on the public address

## 5. README

- [x] 5.1 Update `README.md`:
  - the intro and endpoint table: mark which four endpoints are public, and change the `GET /resume/{application_id}/status` row's "Served on the public address too" to local-only
  - the hosting paragraph (~line 297)
  - the API docs and viewer sections (~lines 257–267): Mac-only URLs
  - replace "API docs on the tailnet" with a short "Local listener" section that has the `tailscale serve --https=8444 off` migration step
  - the `DOCS_PORT=off` and uninstall lines
  - the install and smoke test descriptions (~lines 377 and 395)
  - the folder-permissions note (~line 178)

  Verify with `grep -n -i "8444\|tailnet-only\|DOCS_PORT=off\|DOCS_URL=off" README.md`: the only match should be the migration step.

## 6. Integration check

- [x] 6.1 Run the full suite with `pytest` and both shell test scripts, and verify they all pass.
- [ ] 6.2 On the Mac mini:
  - reinstall with `scripts/install_service.sh`, and confirm it warns about the old `:8444` mapping
  - run `tailscale serve --https=8444 off`
  - run `scripts/service_status.sh` and confirm `local only` with no warning
  - run `API_KEY=… scripts/smoke_test.sh https://<machine>.<tailnet>.ts.net` and confirm it passes
  - open `http://127.0.0.1:8081/viewer` and confirm in the browser's network panel that every request goes to `127.0.0.1:8081`

## Workflow follow-up

- Archive `viewer-fill-form` before this change, since its 18-operation count is the baseline here.
- After archiving this change, update the `Purpose` lines in `openspec/specs/resume-viewer/spec.md` and `openspec/specs/generation-jobs/spec.md` so they no longer say "tailnet" or "public status endpoints".
