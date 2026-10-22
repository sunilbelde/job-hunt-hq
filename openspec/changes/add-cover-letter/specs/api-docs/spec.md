# Spec Delta

## MODIFIED Requirements

### Requirement: Documented endpoint coverage
The OpenAPI document SHALL describe `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume`, `POST /cover-letter`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf` and `GET /resume/base.pdf`, each with a summary, a description and a tag that groups it with related endpoints, and SHALL describe no other operations.

#### Scenario: All endpoints listed
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains exactly those eleven operations, each with a non-empty summary, description and tag

#### Scenario: Health alias
- **WHEN** the OpenAPI document is fetched
- **THEN** `GET /healthz` and `GET /health` are both present, and their descriptions say they are equivalent

#### Scenario: Viewer page not an operation
- **WHEN** the OpenAPI document is fetched
- **THEN** it does not list `/viewer`

#### Scenario: Cover letter description
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /cover-letter` description says it always tailors to the posting, needs posting text, saves the PDF beside the resume, returns the letter's text, and needs a client timeout of at least 10 minutes

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
- **THEN** `POST /application` lists 200, 201, 401, 422 and 503; `PATCH /application/{application_id}` lists 200, 401, 404, 422 and 503; `DELETE /application/{application_id}` lists 200, 401, 404 and 503; `POST /resume` lists 201, 401, 404, 422, 500, 502 and 503; `POST /cover-letter` lists 201, 401, 404, 422, 500, 502 and 503; `GET /applications` lists 200 and 503; `GET /application/{application_id}` lists 200, 404 and 503; `GET /application/{application_id}/resume.pdf` lists 200, 404 and 503; and `GET /resume/base.pdf` lists 200 and 500

#### Scenario: Response shapes
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /resume` 201 response lists exactly `ok`, `application_id`, `saved_path` and `match`, and the `POST /cover-letter` 201 response lists exactly `ok`, `application_id`, `saved_path` and `text`

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
- **THEN** it declares an `apiKey` scheme in `header` named `X-API-Key`, required by the three application write operations, `POST /resume` and `POST /cover-letter`, and not by `GET /health`, `GET /healthz` or the four viewer read operations

#### Scenario: Key not a per-request field
- **WHEN** the OpenAPI document is fetched
- **THEN** no operation lists `X-API-Key` as an ordinary header parameter
