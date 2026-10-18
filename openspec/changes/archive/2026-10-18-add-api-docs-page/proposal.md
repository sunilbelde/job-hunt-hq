# Proposal

## Why

There is no readable reference for the service's endpoints, and no quick way to try a request short of hand-writing `curl` commands. FastAPI already serves `/docs` (Swagger UI), `/redoc` and `/openapi.json` with its default settings, but they show very little. Every handler reads the body from the raw `Request` and takes `X-API-Key` as a plain header parameter, so the generated schema has:

- no request bodies;
- no response or error shapes, except FastAPI's default `422 {"detail": [...]}`, which this service never returns;
- no descriptions, tags or examples;
- no Authorize button.

Those pages are also served today, without auth, on the public Tailscale Funnel address, which nobody chose on purpose.

## What Changes

- **Build on FastAPI's built-in Swagger UI rather than adding a custom page.** Swagger UI's "Try it out" already does what the test page needs: you fill in path parameters, headers and a JSON body, send the request to the live service, and see the status, response headers and body. A custom page would mean writing and maintaining a second request builder and a second copy of the schema. All the work goes into making the OpenAPI document accurate.
- Enrich the OpenAPI document for `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}` and `POST /resume`:
  - tags, summaries and descriptions;
  - request body schemas taken from the existing `ApplicationRow`, `ApplicationUpdate` and `ResumeRequest` models, with examples;
  - success response models;
  - every error status the handler can return (401, 404, 422, 500, 502, 503), documented as `{"ok": false, "message": string}`. FastAPI's default `HTTPValidationError` 422 is removed from the docs.
- Declare `X-API-Key` as an OpenAPI API-key security scheme, so Swagger's **Authorize** button sets the header on every request. The key stays in browser memory: authorization persistence stays off, so it is gone when the tab reloads. It never appears in a URL, and the service already never logs it.
- **Docs are off by default.** A new optional setting `API_DOCS_ENABLED` (default `false`) controls `/docs`, `/redoc` and `/openapi.json`. When it is off, all three return 404. The launchd job pins it to `false` through its environment, so the internet-facing installed service never serves them, even if `.env` sets it to `true` for local development. **BREAKING (for anyone browsing them):** `/docs`, `/redoc` and `/openapi.json` stop being served on the installed service. No API client uses them.
- Request handling, validation, auth order, response bodies, status codes and the `{"ok": false, "message"}` error shape stay exactly as they are. Only metadata visible in the schema changes.
- Docs and schema requests emit no `app.requests` structured log line. Requests sent from "Try it out" are real API requests and log exactly as they do now.

## Capabilities

### New Capabilities
- `api-docs`: the interactive API reference: which endpoints it documents and how accurately, how the API key is entered on it, when it is served, and the rule that serving it never changes or adds to API behavior or request logs.

### Modified Capabilities
- `service-config`: adds the optional `API_DOCS_ENABLED` setting, default `false`.
- `local-service-hosting`: the installed service runs with API docs disabled, and the public Funnel address serves no docs or schema.

## Impact

- **Code:**
  - `app/main.py`: route metadata, `openapi_extra` request bodies, `responses=` declarations, an `APIKeyHeader(auto_error=False)` security scheme replacing the plain `Header` parameter, and conditional `docs_url`/`redoc_url`/`openapi_url`.
  - `app/models.py`: response models and the error model, used only for the schema; schema examples.
  - `app/settings.py`: the new setting.
- **Deploy:** `deploy/local.job-hunt-hq.plist.template` gets `API_DOCS_ENABLED=false` in `EnvironmentVariables`. `scripts/smoke_test.sh` gets an optional check that `/docs` returns 404.
- **Docs:** `.env.example` and the README variable table and Development section.
- **Tests:** new tests for the schema contents, the enabled and disabled states, and logging. The existing API tests must pass unchanged.
- **Dependencies:** none new. When it is enabled, Swagger UI loads its JS and CSS from FastAPI's default CDN (jsDelivr) in the browser.

## Open Questions

These were decided by assumption. Confirm or override them before applying.

1. **Off by default, and never on the installed service.** Tailscale Funnel proxies to `127.0.0.1`, so the service cannot tell a local browser from an internet one by client IP. "Local only" is therefore enforced by configuration rather than by request origin. The alternative is to keep docs on the installed service behind the API key, for example with HTTP Basic auth on `/docs`. It was rejected because it exposes the full API surface to the internet and adds a second auth path. Do you want docs reachable on the Mac mini at all, for example over the tailnet only?
2. **ReDoc is kept** alongside Swagger UI when docs are enabled. It costs nothing extra, but it could be dropped to keep one page.
3. **The schema is gated together with the pages.** `/openapi.json` is gated with `/docs`, not left public for client generators. Nothing consumes it today.
4. **Swagger assets come from the CDN.** We accept that the docs page needs internet access in the browser. The alternative is vendoring `swagger-ui-dist` into `app/static/`, which is about 1.5 MB and works offline.
5. **No access-log changes.** Uvicorn's access log keeps its existing line for every request, including `/docs`. "One log line per request" is read as the `app.requests` structured lines. Docs traffic produces none of those, so it cannot be mistaken for API traffic.
6. **The "Try it out" tester runs against the live store.** It can create, change and delete real application rows and write real resume PDFs. There is no dry-run or sandbox mode. Run a local dev instance with a throwaway `OUTPUT_DIR` if that matters.
