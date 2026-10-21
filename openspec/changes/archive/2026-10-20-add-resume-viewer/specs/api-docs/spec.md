# Spec Delta

## MODIFIED Requirements

### Requirement: Docs disabled by default
When API docs are disabled, which is the default, the system SHALL NOT serve `/docs`, `/redoc`, `/docs/oauth2-redirect`, `/openapi.json`, `/viewer`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf` or `GET /resume/base.pdf`. A request to any of them SHALL be handled as an unknown path.

#### Scenario: Default configuration
- **WHEN** the service runs without API docs enabled and a client requests `GET /docs`, `GET /redoc` or `GET /openapi.json`
- **THEN** each responds 404 and reveals no endpoint list or schema

#### Scenario: Viewer and read endpoints off
- **WHEN** the service runs without API docs enabled and a client sends a valid `X-API-Key` to `GET /viewer`, `GET /applications`, `GET /application/{id}`, `GET /application/{id}/resume.pdf` or `GET /resume/base.pdf`
- **THEN** each responds 404 and returns no application, report or file content

#### Scenario: API unaffected when disabled
- **WHEN** API docs are disabled
- **THEN** `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}` and `POST /resume` behave exactly as they do with docs enabled

### Requirement: Documented endpoint coverage
The OpenAPI document SHALL describe `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf` and `GET /resume/base.pdf`, each with a summary, a description and a tag that groups it with related endpoints, and SHALL describe no other operations.

#### Scenario: All endpoints listed
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains exactly those ten operations, each with a non-empty summary, description and tag

#### Scenario: Health alias
- **WHEN** the OpenAPI document is fetched
- **THEN** `GET /healthz` and `GET /health` are both present, and their descriptions say they are equivalent

#### Scenario: Viewer page not an operation
- **WHEN** the OpenAPI document is fetched
- **THEN** it does not list `/viewer`

### Requirement: Documented responses and errors
The OpenAPI document SHALL list, for each operation, its success status and response shape and every error status the endpoint can return. Every error response SHALL be described as a JSON object with `ok` (always `false`) and `message` (string). It SHALL NOT describe a `{"detail": ...}` validation error, because the service never returns one.

#### Scenario: Error statuses listed
- **WHEN** the OpenAPI document is fetched
- **THEN** `POST /application` lists 200, 201, 401, 422 and 503; `PATCH /application/{application_id}` lists 200, 401, 404, 422 and 503; `DELETE /application/{application_id}` lists 200, 401, 404 and 503; `POST /resume` lists 201, 401, 404, 422, 500, 502 and 503; `GET /applications` lists 200, 401 and 503; `GET /application/{application_id}` lists 200, 401, 404 and 503; `GET /application/{application_id}/resume.pdf` lists 200, 401, 404 and 503; and `GET /resume/base.pdf` lists 200, 401 and 500

#### Scenario: PDF responses
- **WHEN** the OpenAPI document is fetched
- **THEN** the 200 responses of `GET /application/{application_id}/resume.pdf` and `GET /resume/base.pdf` are described as `application/pdf`

#### Scenario: No FastAPI validation error shape
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains no `HTTPValidationError` or `ValidationError` schema, and every 4xx and 5xx response refers to the `{ok, message}` error shape

### Requirement: API key entry through an authorize control
The OpenAPI document SHALL declare `X-API-Key` as an API-key security scheme sent in a header, applied to every endpoint that requires it and to no health endpoint, so the reference page offers a single control for entering the key once for all requests.

#### Scenario: Security scheme declared
- **WHEN** the OpenAPI document is fetched
- **THEN** it declares an `apiKey` scheme in `header` named `X-API-Key`, required by the three application write operations, `POST /resume` and the four viewer read operations, and not by `GET /health` or `GET /healthz`

#### Scenario: Key not a per-request field
- **WHEN** the OpenAPI document is fetched
- **THEN** no operation lists `X-API-Key` as an ordinary header parameter
