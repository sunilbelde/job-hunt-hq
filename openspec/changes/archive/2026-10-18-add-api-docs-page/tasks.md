# Tasks

## 1. Docs toggle setting

- [x] 1.1 Add `api_docs_enabled: bool = False` to `Settings` in `app/settings.py`; verify with new `tests/test_settings.py` cases: default is false, `API_DOCS_ENABLED=true` in `.env` enables it, a process env `false` overrides `.env` `true`, and `maybe` fails with an error naming `API_DOCS_ENABLED`
- [x] 1.2 In `create_app()`, pass `docs_url`/`redoc_url`/`openapi_url` only when enabled (all `None` otherwise) and set explicit `swagger_ui_parameters` that leave `persistAuthorization` off; add `tests/test_docs.py` with a `docs_client` fixture and verify `/docs`, `/redoc`, `/openapi.json` are 404 on the default `client` and 200 on `docs_client`, and that the `/docs` HTML does not enable `persistAuthorization`
- [x] 1.3 Add `API_DOCS_ENABLED=false` to `.env.example` with a "local development only" note, and a row to the README variable table; verify both list the variable and its default

## 2. API key security scheme

- [x] 2.1 Replace `Header(default=None)` with `Security(APIKeyHeader(name="X-API-Key", auto_error=False, scheme_name="ApiKey"))` on `POST /application`, `PATCH`/`DELETE /application/{application_id}` and `POST /resume`, keeping the inline `api_key_valid()` 401; verify the whole existing `tests/test_api.py` passes unmodified
- [x] 2.2 Add schema tests: `components.securitySchemes.ApiKey` is `apiKey`/`header`/`X-API-Key`, applied to the four protected operations and not to `/health` or `/healthz`, and no operation lists an `X-API-Key` parameter; verify they pass

## 3. Schema models and route metadata

- [x] 3.1 Add schema-only models `ErrorResponse`, `ApplicationRecorded`, `ApplicationUpdated`, `ResumeCreated`, `HealthStatus` to `app/models.py`, plus `json_schema_extra` examples on `ApplicationRow`, `ApplicationUpdate`, `ResumeRequest` (reuse the README/conftest example shape); verify `tests/test_models.py` still passes and each example validates against its model
- [x] 3.2 Add tags (`health`, `applications`, `resumes`), summaries and descriptions to all six routes, stating the `/health`↔`/healthz` equivalence, the pairing rules, immutable fields, and that malformed IDs give 404; verify a test asserts exactly the six operations each have non-empty tag/summary/description
- [x] 3.3 Add `openapi_extra` request bodies for `POST /application`, `PATCH /application/{application_id}`, `POST /resume` and register the model schemas in `components.schemas` via a custom `app.openapi()`, leaving `await request.json()` parsing untouched; verify tests check required fields and enum values for `ApplicationRow`, that the update schema omits the immutable fields, and that `application_id` path params are still `type: string`
- [x] 3.4 Add per-route `responses=` tables (success models plus every error status per the `api-docs` spec, all errors referencing `ErrorResponse`); verify tests assert the exact status sets per operation and that no `HTTPValidationError`/`ValidationError` component exists
- [x] 3.5 Add a test that sends every documented example body (with a valid key, creating an application first for PATCH and `/resume`) and asserts no 422; verify it passes

## 4. Behavior and logging guarantees

- [x] 4.1 Parametrize the `client` fixture in `tests/conftest.py` over docs disabled/enabled so the existing API suite runs against both; verify `pytest` passes for both parameters with no test edits beyond the fixture
- [x] 4.2 Add a caplog test: requesting `/docs`, `/redoc` and `/openapi.json` on `docs_client` emits no `app.requests` record, while a `DELETE /application/{id}` on the same client emits exactly one `application_request` line; verify it passes

## 5. Installed service stays docs-free

- [x] 5.1 Add `API_DOCS_ENABLED=false` to `EnvironmentVariables` in `deploy/local.job-hunt-hq.plist.template`; verify `scripts/test_install_service.sh` passes and the rendered plist passes `plutil -lint` and contains the key
- [x] 5.2 Extend `scripts/smoke_test.sh` to fail unless `GET /docs` and `GET /openapi.json` return 404, and extend the curl stub in `scripts/test_smoke_test.sh` with cases for 404 (pass) and 200 (fail); verify `scripts/test_smoke_test.sh` passes
- [x] 5.3 Add a README Development note: run with `API_DOCS_ENABLED=true` and a throwaway `OUTPUT_DIR`, open `http://localhost:8080/docs`, click Authorize, use Try it out; and state that the installed service never serves docs; verify the documented command starts a dev server whose `/docs` returns 200

## 6. Integration check

- [ ] 6.1 Manually, on a local dev server with docs enabled: Authorize with the key, Try it out on all six operations, confirm status/headers/body are shown and errors appear as `{"ok": false, "message"}`; reload `/docs` and confirm the key is gone; confirm the browser's local/session storage holds no key and the service log has one `app.requests` line per tried request and none for page loads
- [x] 6.2 Run the full `pytest` suite and both shell test scripts; verify all pass

## Workflow follow-up

- After merge, rerun `scripts/install_service.sh` and run `scripts/smoke_test.sh https://<mac-tailscale-name>` to confirm `/docs` is 404 on the public address.
- Archive the change once the open questions in proposal.md are confirmed and the follow-up check passes.
