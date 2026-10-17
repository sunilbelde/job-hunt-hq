# Spec Delta

## Purpose

Defines the HTTP interface through which clients submit JSON jobs and receive a link to the generated output file, plus the liveness endpoint used by the hosting platform.

## ADDED Requirements

### Requirement: API key authentication on job submission
The system SHALL require the `X-API-Key` header on `POST /jobs` to equal the configured API key, and SHALL respond 401 otherwise, before reading the body, generating output, or touching storage.

#### Scenario: Missing key
- **WHEN** a client sends `POST /jobs` without `X-API-Key`
- **THEN** the system responds 401 and no file is generated or stored

#### Scenario: Wrong key
- **WHEN** a client sends `POST /jobs` with an `X-API-Key` that does not match
- **THEN** the system responds 401 and no file is generated or stored

### Requirement: JSON object body validation
The system SHALL accept only a JSON object as the `POST /jobs` body and SHALL reject non-JSON or non-object bodies with a 4xx status (400 or 422) without generating or storing anything.

#### Scenario: Malformed JSON
- **WHEN** an authenticated client sends a body that is not valid JSON
- **THEN** the system responds 4xx and no file is stored

#### Scenario: Non-object JSON
- **WHEN** an authenticated client sends a JSON array, string, number or null
- **THEN** the system responds 4xx and no file is stored

#### Scenario: Arbitrary object accepted
- **WHEN** an authenticated client sends any JSON object, including an empty one
- **THEN** the system accepts it for processing

### Requirement: Job creation response
On success, `POST /jobs` SHALL respond 201 with a JSON body containing `job_id`, `url`, `expires_at` and `key`, where `url` is a pre-signed download link for the stored file and `key` is its object key.

#### Scenario: Successful job
- **WHEN** an authenticated client posts a valid JSON object
- **THEN** the system responds 201 with `job_id`, `url`, `expires_at` (UTC, ISO 8601) and `key`
- **AND** opening `url` in a browser downloads the generated file before expiry

### Requirement: Stubbed output generation
For this release the system SHALL produce a JSON file containing the received payload, a UTC timestamp and the job id, via a generation interface returning content bytes, a content type and a file extension.

#### Scenario: Stub output content
- **WHEN** a job is processed
- **THEN** the stored file is `application/json` with extension `json` and contains the payload, a UTC timestamp and the job id

### Requirement: Storage failure handling
When storage upload or URL signing fails, the system SHALL respond 502 with a generic message that exposes no internal details, and SHALL log the failure details server-side.

#### Scenario: R2 unavailable
- **WHEN** the upload to R2 raises an error
- **THEN** the system responds 502 with a generic error message
- **AND** the response body contains no endpoint, bucket, credential or exception text

### Requirement: Per-request structured logging
The system SHALL emit exactly one structured log line per `POST /jobs` request including job id, HTTP status and duration, and SHALL NOT log secrets, the API key, or the full request payload.

#### Scenario: Successful request log
- **WHEN** a job completes
- **THEN** one log line records job id, status 201 and duration

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records the status and duration, with no key or payload content

### Requirement: Health endpoint
The system SHALL expose `GET /healthz` and `GET /health`, each returning 200 `{"status": "ok"}` without authentication and without contacting R2. The `/health` alias exists because Cloud Run's front end intercepts `/healthz` on its public URLs.

#### Scenario: Health check
- **WHEN** any client sends `GET /healthz` or `GET /health`
- **THEN** the system responds 200 `{"status": "ok"}` and makes no storage call

#### Scenario: Health check on Cloud Run
- **WHEN** a client sends `GET /health` to the deployed Cloud Run URL
- **THEN** the system responds 200 `{"status": "ok"}`
