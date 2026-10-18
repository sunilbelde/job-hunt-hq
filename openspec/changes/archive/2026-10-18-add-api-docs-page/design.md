# Design

## Context

Motivation: see proposal.md, Why. These facts about the current code shape the approach:

- `create_app()` builds `FastAPI(title="Job output service")` with the default `docs_url`, `redoc_url` and `openapi_url`, so all three are live today, including through Funnel.
- Every body-taking handler reads `await request.json()` and validates by hand. This is deliberate: it keeps the `{"ok": false, "message"}` shape and the "401 before reading the body" order. A side effect is that FastAPI cannot see the bodies, so the schema has none.
- `x_api_key: str | None = Header(default=None)` makes the key an ordinary per-operation header field in Swagger, with no Authorize button.
- Path IDs are typed `str` on purpose, so a malformed ID gives 404 rather than FastAPI's 422. The schema must not change that typing.
- The `log_request` middleware logs only paths that `request_event()` maps to an event. `/docs`, `/redoc` and `/openapi.json` already map to `None`, so they produce no `app.requests` line today.
- `Settings` is pydantic-settings, reading `.env`. The launchd job runs from the repo and reads the same `.env` a developer uses, so a value set in `.env` for development would reach the public service too.
- Funnel proxies to `127.0.0.1:8080`, so every request, local or internet, arrives from loopback.

## Goals / Non-Goals

**Goals:**
- An accurate OpenAPI document for the six endpoints, generated from the same Pydantic models the handlers validate with, so it cannot drift.
- Use Swagger UI's existing "Try it out" as the endpoint test page.
- Docs are impossible to enable on the installed service by editing `.env` alone.

**Non-Goals:**
- Changing how any handler parses, validates or answers requests (see the `api-docs` spec, "Documentation leaves API behavior unchanged").
- A custom HTML test page, request history, saved requests or a sandbox store.
- Rate limiting or other hardening of the public API, which is a separate follow-up.
- Serving Swagger assets offline (proposal, Open Question 4).
- Changing uvicorn's access log.

## Decisions

### 1. Build on FastAPI's Swagger UI, not a custom page
Swagger UI already provides the request builder: path parameters, headers, a JSON body editor seeded from the examples, and display of the status, response headers and body. ReDoc comes with it for reading. The only gap is schema quality, which we fix at the source.

*Alternative considered:* a hand-written `/console` page that uses `fetch()`. Rejected. It duplicates the request builder, needs its own copy of the field lists, which would drift from the models, and adds HTML and JS to review for key handling. Swagger UI's key handling is already well understood.

### 2. Document bodies with `openapi_extra`, keep raw parsing
Each body-taking route gets `openapi_extra={"requestBody": {...}}`, which points at the models' JSON schema: `ApplicationRow`, `ApplicationUpdate` and `ResumeRequest`. The handlers keep `await request.json()` and their hand-written validation unchanged. The model schemas are registered under `components.schemas`, either through a small custom `app.openapi()` that merges `Model.model_json_schema(ref_template="#/components/schemas/{model}")` or by listing the models as response models. The custom `openapi()` is preferred because it is explicit.

*Alternative considered:* declaring `application: ApplicationRow` as a body parameter. Rejected. FastAPI would then validate before the handler runs, returning `{"detail": [...]}` 422s and checking the body before the API key. That breaks the error shape and the auth order.

Model-level rules, such as the source-type/method pairing and the immutable-field rejection, are not expressible in JSON Schema. They go into the operation `description` text instead.

### 3. Error and success models used only for the schema
Add schema-only models to `app/models.py`:
- `ErrorResponse {ok: Literal[False], message: str}`;
- `ApplicationRecorded {ok: Literal[True], application_id: str}`, used for POST and DELETE;
- `ApplicationUpdated {ok, application_id, status}`;
- `ResumeCreated {ok, application_id, saved_path}`;
- `HealthStatus {status: Literal["ok"]}`.

They are wired in through `responses={status: {"model": ..., "description": ...}}` per route. Handlers keep returning `JSONResponse`/dicts, and no `response_model=` filtering is applied, so serialization is untouched. Declaring `422` on every route replaces FastAPI's default `HTTPValidationError` entry. A unit test asserts that no `HTTPValidationError` or `ValidationError` component remains.

### 4. `APIKeyHeader(name="X-API-Key", auto_error=False, scheme_name="ApiKey")`
Swap `Header(default=None)` for `Security(api_key_header)` on the four protected routes. With `auto_error=False` the dependency returns `None` when the header is missing instead of raising 403, so `api_key_valid()` and the inline 401 work exactly as now. This was checked against FastAPI 0.128: missing header → `None`, present → the value. It adds `components.securitySchemes.ApiKey` and per-operation `security`, which is what produces the Authorize button. The health routes get no security.

### 5. Key handling on the page: Swagger defaults, pinned
Swagger UI keeps authorizations in memory unless `persistAuthorization` is true, and FastAPI does not set it. We pass explicit `swagger_ui_parameters` that leave `persistAuthorization` false, and a test asserts the generated HTML does not enable it. That protects against a future default change. The key travels only as the `X-API-Key` header, because the scheme is `in: header`. The server side already never logs it: the middleware logs only named fields, and uvicorn's access line has no headers.

### 6. Toggle via `API_DOCS_ENABLED`, forced off in the plist
`Settings.api_docs_enabled: bool = False`. `create_app()` passes `docs_url="/docs"`, `redoc_url="/redoc"` and `openapi_url="/openapi.json"` when it is true, and `None` for all three otherwise. FastAPI then registers no route, so the request is a normal 404. Setting `openapi_url=None` also removes `/docs/oauth2-redirect`.

The plist template adds `<key>API_DOCS_ENABLED</key><string>false</string>` to `EnvironmentVariables`. pydantic-settings gives process environment variables priority over `.env`, so the installed service is off even when a developer's `.env` says `true`. The smoke test adds `curl` checks that `/docs` and `/openapi.json` return 404.

*Alternatives considered:*
- Gate on the client address being loopback. This is useless behind Funnel, where every request arrives from loopback.
- Protect `/docs` with the API key or HTTP Basic auth. This is still internet-exposed, and adds a second auth mechanism.
- Have the install script refuse when `.env` enables docs. This is weaker than the plist override, because `.env` can change after install.

### 7. Logging
No middleware change is needed. `request_event()` already returns `None` for the docs paths. Tests lock that in. Requests sent from "Try it out" go through the same routes and middleware, so they log one line each, as today. Telling a tried request apart from a Muse request in the logs is not attempted (proposal, Open Question 5).

### 8. Tests
In `tests/test_docs.py`, using a `docs_client` fixture built with `api_docs_enabled=True`:
- **Disabled (default `client` fixture):** `/docs`, `/redoc` and `/openapi.json` return 404.
- **Enabled:** `/docs` and `/redoc` return 200 HTML, and `/openapi.json` returns 200 with exactly the six operations.
- **Per operation:** a tag, summary and description; the documented response statuses match the spec table; every 4xx and 5xx response `$ref`s `ErrorResponse`; there is no `HTTPValidationError`.
- **Security:** the `ApiKey` scheme is defined and applied to the four protected operations and not the two health ones. No operation has an `X-API-Key` parameter.
- **Request bodies:** the required fields and enums match the models. `ApplicationUpdate`'s schema does not list the immutable fields.
- **Examples:** each documented example is posted to the real app and gets no 422.
- **Key on the page:** the `/docs` HTML does not contain `"persistAuthorization": true`.
- **Logging:** with caplog, loading `/docs` and `/openapi.json` yields no `app.requests` record.
- **Settings:** the default is `False`; the environment overrides `.env`; an invalid value fails naming `API_DOCS_ENABLED`.

Also: run the existing `tests/test_api.py` against both the default and a docs-enabled app, using a parametrized `client` fixture, to prove behavior is unchanged. `scripts/test_smoke_test.sh` covers the new smoke check if that harness stubs `curl`.

A manual check covers the browser-only behavior that pytest cannot see: Authorize, Try it out, reload, then the key is gone. This is listed as a task.

## Risks / Trade-offs

- **[Schema drift from hand-written `responses=` tables]** → The tests assert the documented statuses per route, and the request schemas come from the validating models themselves.
- **[Cross-field rules invisible to JSON Schema]**, so Swagger may let a user build a body that gets a 422 → The rules are stated in the operation descriptions, and the 422 message names the failed rule.
- **[Docs enabled on a dev instance pointed at the real `OUTPUT_DIR`]**: Try it out writes and deletes real rows → The README tells developers to use a throwaway `OUTPUT_DIR` when trying requests.
- **[Swagger UI loaded from the jsDelivr CDN]**: a third-party script on a page where the key is typed → This only happens on local dev instances. FastAPI pins the asset version. Vendoring is an option later.
- **[Switching `Header` to `APIKeyHeader` changes the missing-key path]** → `auto_error=False` was verified to return `None`. The existing 401 tests (missing and wrong key, every protected route) must keep passing.

## Migration Plan

1. Merge, then rerun `scripts/install_service.sh` so the new plist, with `API_DOCS_ENABLED=false`, is loaded.
2. Run `scripts/smoke_test.sh https://<mac-tailscale-name>` and confirm the docs 404 check passes.
3. Rollback: reverting the commit restores FastAPI's defaults, which means docs are public again. Reinstall afterwards.
