# Tasks

## 1. Docs page fixes (api-docs)

- [x] 1.1 Swap the `/health` and `/healthz` decorators in `app/main.py` so `/healthz` registers first; add a `tests/test_docs.py` test that `/healthz` precedes `/health` in `paths` and verify `pytest tests/test_docs.py tests/test_api.py` passes
- [x] 1.2 Serve `/docs` and `/redoc` through custom routes (only when docs are enabled, excluded from the schema) that use exact `swagger-ui-dist@5.33.3` and a resolved exact `redoc` version, with `integrity`/`crossorigin` on the script and stylesheet tags, keeping `persistAuthorization: False` and `/docs/oauth2-redirect`; verify new tests (exact versions, `integrity=` present, no `@5/`/`@2/`) and the existing docs-disabled 404 tests pass
- [ ] 1.3 Manually open the dev server's `/docs` (`API_DOCS_ENABLED=true OUTPUT_DIR=/tmp/job-hunt-hq-dev ...`) and confirm the page loads with the pinned assets (no SRI console errors), tags and coloured badges show, and Authorize, Try it out and reload-forgets-key behave as before

## 2. Launcher with a tailnet docs listener (app)

- [x] 2.1 Add `app/serve.py` with the `by_local_port` dispatcher (docs app only when `scope["server"]` port equals the docs port; everything else, including lifespan and a missing `server`, goes to the public app); verify with `tests/test_serve.py` unit tests, including forged `Host`/`X-Forwarded-*`/`Tailscale-*` headers on the public port still giving 404 for `/docs`
- [x] 2.2 Add the CLI (`--host`, `--port`, `--docs-port`, `--log-config`): build one storage and store, a public app with docs forced off and a docs app with docs forced on, bind loopback sockets, run one `uvicorn.Server` over both; refuse equal ports and non-loopback hosts; verify with unit tests for the refusals
- [x] 2.3 Add an integration test that runs `python -m app.serve` on two ephemeral ports with a temp `OUTPUT_DIR` and `API_KEY`, and checks: `/docs` 404 public and 200 docs; `/health` 200 on both; `POST /application` on the docs port then the same body on the public port gives 200 with the same ID; one `application_request` line per API call and none for docs loads; verify `pytest` passes in full
- [x] 2.4 Update the README "API reference" section: the installed service serves docs on the tailnet listener, with the local and tailnet URLs and the dev command unchanged; verify the documented dev command still works as written

## 3. Install, status, uninstall (local-service-hosting)

- [x] 3.1 Change `deploy/local.job-hunt-hq.plist.template` `ProgramArguments` to `__REPO__/.venv/bin/python -m app.serve --host 127.0.0.1 --port __PORT__ --docs-port __DOCS_PORT__ --log-config ...`, keeping `API_DOCS_ENABLED=false` and updating its comment; verify `plutil -lint` on a rendered copy
- [x] 3.2 In `scripts/install_service.sh`: add `DOCS_PORT` (default 8081, `off` drops the two docs lines), refuse `DOCS_PORT == PORT` before any sudo, check after start that the public `/docs` is 404 (die otherwise) and the docs `/docs` is 200, warn when `tailscale serve status --json` has no handler for `127.0.0.1:$DOCS_PORT` (print `tailscale serve --bg --https=8444 http://127.0.0.1:$DOCS_PORT`) or has one in `AllowFunnel`, and print the docs URLs
- [x] 3.3 Update `scripts/test_install_service.sh`: the plist runs `-m app.serve` with `--docs-port 8081`; `API_DOCS_ENABLED` is still `false`; `DOCS_PORT=9090` is rendered; `DOCS_PORT=off` has no `--docs-port`; `DOCS_PORT=8080` is refused with no sudo call; a per-port curl stub where public `/docs` returns 200 fails install; the tailscale JSON stub covers the mapping present (no warning), missing (serve command printed) and Funnel-enabled (public warning) cases; the docs URL is printed. Verify `sh scripts/test_install_service.sh` prints no `FAIL`
- [x] 3.4 Add a `docs:` line to `scripts/service_status.sh` (ok, FAILING or off, with the port read from the installed plist, plus the Funnel warning) and a reminder in `scripts/uninstall_service.sh` to run `tailscale serve --https=8444 off`; extend the status and uninstall cases in `test_install_service.sh` and verify they pass
- [x] 3.5 Update the README hosting sections (Tailscale setup, security note, uninstall, LAN/loopback statement and the `API_DOCS_ENABLED` row) with the `tailscale serve --https=8444` step, the URLs `http://127.0.0.1:8081/docs` and `https://<machine>.<tailnet>.ts.net:8444/docs`, why 8444 cannot be funnelled, the optional ACL to restrict `:8444`, and that Try it out writes real data; verify every command shown matches the scripts

## 4. Smoke test (local-service-hosting)

- [x] 4.1 In `scripts/smoke_test.sh`, add a `DOCS_URL` check (default `http://127.0.0.1:8081`, `off` skips) before any POST: `$DOCS_URL/docs` 200 and `$DOCS_URL/openapi.json` 200 with exactly six operations, keeping the public 404 checks; update the usage text and README smoke-test line
- [x] 4.2 Extend `scripts/test_smoke_test.sh` with a host-aware curl stub: docs listener healthy passes; docs 404 fails with no POST; a wrong operation count fails; `DOCS_URL=off` skips; public `/docs` 200 still fails. Verify `sh scripts/test_smoke_test.sh` prints no `FAIL`

## 5. Rollout on the Mac mini (integration)

- [ ] 5.1 Run `scripts/install_service.sh`, then `tailscale serve --bg --https=8444 http://127.0.0.1:8081`; verify `tailscale serve status --json` shows `:8444 → 127.0.0.1:8081` and `AllowFunnel` only for `:443`, and that `scripts/service_status.sh` reports health and docs ok
- [ ] 5.2 Run `API_KEY=... scripts/smoke_test.sh https://sunils-mac-mini.tailf96439.ts.net`; verify it passes, including the docs listener check
- [ ] 5.3 Open `https://sunils-mac-mini.tailf96439.ts.net:8444/docs` from another tailnet device and send a `GET /healthz` with Try it out; from a device off the tailnet, verify `https://sunils-mac-mini.tailf96439.ts.net/docs` is 404 and `:8444` does not connect

## Workflow follow-up

- Resolve or confirm the proposal's Open Questions before or during apply.
- Archive the change after the rollout checks pass.
