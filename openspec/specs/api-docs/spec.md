# api-docs Specification

## Purpose

Defines the interactive API reference: a browsable description of every endpoint that can also send live requests, when it is served, and the guarantees that it never alters API behavior, logs or secrets.

## Requirements

### Requirement: Interactive API reference pages
When API docs are enabled, the system SHALL serve an interactive API reference at `/docs`, an alternative read-only reference at `/redoc`, and the machine-readable OpenAPI document they are built from at `/openapi.json`, all without requiring the API key.

#### Scenario: Docs page served
- **WHEN** API docs are enabled and a browser requests `GET /docs`
- **THEN** the system responds 200 with an HTML page that lists the service's endpoints

#### Scenario: Schema served
- **WHEN** API docs are enabled and a client requests `GET /openapi.json` without `X-API-Key`
- **THEN** the system responds 200 with an OpenAPI 3 JSON document

#### Scenario: ReDoc served
- **WHEN** API docs are enabled and a browser requests `GET /redoc`
- **THEN** the system responds 200 with an HTML page

### Requirement: Docs disabled by default
When API docs are disabled, which is the default, the system SHALL NOT serve `/docs`, `/redoc`, `/docs/oauth2-redirect`, `/openapi.json`, `/viewer`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `GET /resume/base.pdf` or `GET /cover-letter/base.pdf`. A request to any of them SHALL be handled as an unknown path.

#### Scenario: Default configuration
- **WHEN** the service runs without API docs enabled and a client requests `GET /docs`, `GET /redoc` or `GET /openapi.json`
- **THEN** each responds 404 and reveals no endpoint list or schema

#### Scenario: Viewer and read endpoints off
- **WHEN** the service runs without API docs enabled and a client sends a valid `X-API-Key` to `GET /viewer`, `GET /applications`, `GET /application/{id}`, `GET /application/{id}/resume.pdf`, `GET /application/{id}/cover-letter.pdf`, `GET /resume/base.pdf` or `GET /cover-letter/base.pdf`
- **THEN** each responds 404 and returns no application, report or file content

#### Scenario: API unaffected when disabled
- **WHEN** API docs are disabled
- **THEN** `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume` and `POST /cover-letter` behave exactly as they do with docs enabled

### Requirement: Documented endpoint coverage
The OpenAPI document SHALL describe `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume`, `GET /resume/{application_id}/status`, `POST /cover-letter`, `GET /cover-letter/{application_id}/status`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `GET /resume/base.pdf` and `GET /cover-letter/base.pdf`, each with a summary, a description and a tag that groups it with related endpoints, and SHALL describe no other operations.

#### Scenario: All endpoints listed
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains exactly those fifteen operations, each with a non-empty summary, description and tag

#### Scenario: Health alias
- **WHEN** the OpenAPI document is fetched
- **THEN** `GET /healthz` and `GET /health` are both present, and their descriptions say they are equivalent

#### Scenario: Viewer page not an operation
- **WHEN** the OpenAPI document is fetched
- **THEN** it does not list `/viewer`

#### Scenario: Cover letter description
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /cover-letter` description says it always tailors to the posting, needs posting text, saves the PDF beside the resume, runs in the background and returns 202, and that the letter's path and text come from `GET /cover-letter/{application_id}/status`

#### Scenario: Background generation described
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /resume` and `POST /cover-letter` descriptions say the run continues after the response, that a request while a run is in progress starts no second run, and that the client polls the matching status endpoint, and neither tells the client to use a 10-minute timeout

#### Scenario: Status endpoints described
- **WHEN** the OpenAPI document is fetched
- **THEN** the two status endpoints are tagged with their POST endpoint (`resumes` and `cover letters`), require the API key, and their descriptions list the job states, say a restart marks a running job `failed`, and say they return no posting text

#### Scenario: Cover letter reads described
- **WHEN** the OpenAPI document is fetched
- **THEN** the `GET /application/{application_id}/cover-letter.pdf` description says where the letter is looked for, and the `GET /cover-letter/base.pdf` description says it serves the committed base letter unchanged and is never generated by the service; both are tagged with the other viewer reads

### Requirement: Documented request bodies
The OpenAPI document SHALL give `POST /application`, `PATCH /application/{application_id}`, `POST /resume` and `POST /cover-letter` a JSON request body schema that matches the fields, types, allowed values and required fields the endpoint actually validates, with at least one example body that the endpoint accepts.

#### Scenario: Application body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /application` body schema marks `company`, `role`, `job_link`, `posting_source_type`, `verification_method` and `official_apply_url` as required, and lists the allowed values of `posting_source_type` and `verification_method`

#### Scenario: Update body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `PATCH /application/{application_id}` body schema lists the updatable fields and the allowed `status` values, and does not list `job_link`, `posting_source_type`, `verification_method` or `official_apply_url` as updatable

#### Scenario: Cover letter body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /cover-letter` body schema requires a string `application_id`

#### Scenario: Examples are valid
- **WHEN** each documented example body is sent with a valid API key to its endpoint, against an empty store and, for `PATCH`, `POST /resume` and `POST /cover-letter`, an existing application ID
- **THEN** the endpoint does not respond 422 for a body reason

### Requirement: Documented responses and errors
The OpenAPI document SHALL list, for each operation, its success status and response shape and every error status the endpoint can return. Every error response SHALL be described as a JSON object with `ok` (always `false`) and `message` (string). It SHALL NOT describe a `{"detail": ...}` validation error, because the service never returns one.

#### Scenario: Error statuses listed
- **WHEN** the OpenAPI document is fetched
- **THEN** `POST /application` lists 200, 201, 401, 422 and 503; `PATCH /application/{application_id}` lists 200, 401, 404, 422 and 503; `DELETE /application/{application_id}` lists 200, 401, 404 and 503; `POST /resume` lists 202, 401, 404, 422 and 503; `GET /resume/{application_id}/status` lists 200, 401, 404 and 503; `POST /cover-letter` lists 202, 401, 404, 422 and 503; `GET /cover-letter/{application_id}/status` lists 200, 401, 404 and 503; `GET /applications` lists 200 and 503; `GET /application/{application_id}` lists 200, 404 and 503; `GET /application/{application_id}/resume.pdf` lists 200, 404 and 503; `GET /application/{application_id}/cover-letter.pdf` lists 200, 404 and 503; `GET /resume/base.pdf` lists 200 and 500; and `GET /cover-letter/base.pdf` lists 200 and 404

#### Scenario: Response shapes
- **WHEN** the OpenAPI document is fetched
- **THEN** the 202 responses of `POST /resume` and `POST /cover-letter` list exactly `ok`, `application_id`, `status` and `started_at`; the `GET /resume/{application_id}/status` 200 response lists exactly `ok`, `application_id`, `status`, `started_at`, `finished_at`, `saved_path`, `match` and `error`; and the `GET /cover-letter/{application_id}/status` 200 response lists the same with `text` in place of `match`

#### Scenario: Job status values
- **WHEN** the OpenAPI document is fetched
- **THEN** the status responses' `status` field lists exactly `running`, `done` and `failed`

#### Scenario: PDF responses
- **WHEN** the OpenAPI document is fetched
- **THEN** the 200 responses of `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `GET /resume/base.pdf` and `GET /cover-letter/base.pdf` are described as `application/pdf`

#### Scenario: No FastAPI validation error shape
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains no `HTTPValidationError` or `ValidationError` schema, and every 4xx and 5xx response refers to the `{ok, message}` error shape

### Requirement: API key entry through an authorize control
The OpenAPI document SHALL declare `X-API-Key` as an API-key security scheme sent in a header, applied to every endpoint that requires it and to no health endpoint or viewer read, so the reference page offers a single control for entering the key once for all requests.

#### Scenario: Security scheme declared
- **WHEN** the OpenAPI document is fetched
- **THEN** it declares an `apiKey` scheme in `header` named `X-API-Key`, required by the three application write operations, `POST /resume` and `POST /cover-letter`, and not by `GET /health`, `GET /healthz` or the six viewer read operations

#### Scenario: Key not a per-request field
- **WHEN** the OpenAPI document is fetched
- **THEN** no operation lists `X-API-Key` as an ordinary header parameter

### Requirement: API key kept out of storage and URLs
The reference page SHALL hold an entered API key only in the open page's memory. It SHALL NOT write the key to browser storage or cookies, and SHALL send it only in the `X-API-Key` request header, never in a URL or query string.

#### Scenario: Reload forgets the key
- **WHEN** a user enters the API key, sends a request, and then reloads `/docs`
- **THEN** the page is no longer authorized and the key must be entered again

#### Scenario: Key in header only
- **WHEN** a user sends a request from the reference page after entering the key
- **THEN** the key is carried in the `X-API-Key` header, and the request URL contains no key

### Requirement: Live request testing from the reference page
The interactive reference page SHALL let a user fill in path parameters and a JSON body for any documented operation, send it to the running service, and see the response status, response headers and response body.

#### Scenario: Send and inspect
- **WHEN** a user authorizes with a valid key and sends `POST /application` with the documented example body from `/docs`
- **THEN** the page shows status 201 or 200, the response headers and the `{"ok": true, "application_id": ...}` body

#### Scenario: Error shown as returned
- **WHEN** a user sends `PATCH /application/not-a-uuid` from `/docs`
- **THEN** the page shows status 404 and the body `{"ok": false, "message": "Application not found"}`

### Requirement: Documentation leaves API behavior unchanged
Adding the API reference SHALL NOT change any endpoint's paths, methods, accepted bodies, validation order, status codes, response bodies, error messages or the `{"ok": false, "message"}` error shape, whether docs are enabled or disabled.

#### Scenario: Existing contract tests
- **WHEN** the existing API test suite runs, with docs enabled and with docs disabled
- **THEN** every test passes without modification

#### Scenario: Missing key still checked first
- **WHEN** `POST /application` is sent without `X-API-Key` and with an invalid body
- **THEN** the response is still 401 `{"ok": false, "message": "Invalid or missing API key"}`, not 403 or 422

### Requirement: Docs traffic is not logged as API traffic
Requests to `/docs`, `/redoc`, `/docs/oauth2-redirect` and `/openapi.json` SHALL NOT emit a structured request log line such as `application_request` or `resume_request`. Requests sent from the reference page to an API endpoint SHALL be logged exactly as any other request to that endpoint.

#### Scenario: Loading docs logs nothing structured
- **WHEN** a browser loads `/docs`, which also fetches `/openapi.json`
- **THEN** no `application_request` or `resume_request` log line is emitted

#### Scenario: Tried request logged once
- **WHEN** a user sends `DELETE /application/{id}` from the reference page
- **THEN** exactly one `application_request` log line is emitted for it, with no API key or body content

### Requirement: Pinned reference page assets
The interactive reference page SHALL load its Swagger UI script and stylesheet, and `/redoc` its ReDoc script, from an exact, pinned version, with integrity checks, so the code that runs where the API key is typed cannot change without a change to this repository.

#### Scenario: Exact version
- **WHEN** a browser loads `/docs` or `/redoc`
- **THEN** every Swagger UI or ReDoc script and stylesheet URL on the page names an exact version (major, minor and patch), not a range such as `@5` or `@2`

#### Scenario: Integrity checked
- **WHEN** a browser loads `/docs`
- **THEN** the Swagger UI script and stylesheet tags carry a subresource integrity hash, so a modified file is refused

#### Scenario: Page behaviour unchanged
- **WHEN** a user opens `/docs` with the pinned assets
- **THEN** endpoints are grouped by tag with coloured method badges, Authorize and Try it out work, and an entered key is not persisted across reloads

### Requirement: Primary health check listed first
The reference SHALL list `GET /healthz` before its alias `GET /health` within the `health` tag.

#### Scenario: Order in the document
- **WHEN** the OpenAPI document is fetched
- **THEN** the `/healthz` path appears before the `/health` path
