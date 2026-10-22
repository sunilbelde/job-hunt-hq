## MODIFIED Requirements

### Requirement: Documented responses and errors
The OpenAPI document SHALL list, for each operation, its success status and response shape and every error status the endpoint can return. Every error response SHALL be described as a JSON object with `ok` (always `false`) and `message` (string). It SHALL NOT describe a `{"detail": ...}` validation error, because the service never returns one.

#### Scenario: Error statuses listed
- **WHEN** the OpenAPI document is fetched
- **THEN** `POST /application` lists 200, 201, 401, 422 and 503; `PATCH /application/{application_id}` lists 200, 401, 404, 422 and 503; `DELETE /application/{application_id}` lists 200, 401, 404 and 503; `POST /resume` lists 201, 401, 404, 422, 500, 502 and 503; `GET /applications` lists 200 and 503; `GET /application/{application_id}` lists 200, 404 and 503; `GET /application/{application_id}/resume.pdf` lists 200, 404 and 503; and `GET /resume/base.pdf` lists 200 and 500

#### Scenario: PDF responses
- **WHEN** the OpenAPI document is fetched
- **THEN** the 200 responses of `GET /application/{application_id}/resume.pdf` and `GET /resume/base.pdf` are described as `application/pdf`

#### Scenario: No FastAPI validation error shape
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains no `HTTPValidationError` or `ValidationError` schema, and every 4xx and 5xx response refers to the `{ok, message}` error shape

### Requirement: API key entry through an authorize control
The OpenAPI document SHALL declare `X-API-Key` as an API-key security scheme sent in a header, applied to every endpoint that requires it and to no health endpoint or viewer read, so the reference page offers a single control for entering the key once for all requests.

#### Scenario: Security scheme declared
- **WHEN** the OpenAPI document is fetched
- **THEN** it declares an `apiKey` scheme in `header` named `X-API-Key`, required by the three application write operations and `POST /resume`, and not by `GET /health`, `GET /healthz` or the four viewer read operations

#### Scenario: Key not a per-request field
- **WHEN** the OpenAPI document is fetched
- **THEN** no operation lists `X-API-Key` as an ordinary header parameter
