# Spec Delta

## MODIFIED Requirements

### Requirement: Job creation response
On success, `POST /jobs` SHALL respond 201 with a JSON body containing `job_id`, `url`, `expires_at` and `key`, where `url` is a signed download link for the stored file served by this service under the configured public base URL, and `key` is its storage key.

#### Scenario: Successful job
- **WHEN** an authenticated client posts a valid job posting
- **THEN** the system responds 201 with `job_id`, `url`, `expires_at` (UTC, ISO 8601) and `key`
- **AND** `url` starts with the configured public base URL
- **AND** opening `url` in a browser on a tailnet device downloads the generated PDF before expiry

## REMOVED Requirements

### Requirement: Storage failure handling
**Reason**: Its scenario is about R2 being unavailable, and R2 is no longer used.
**Migration**: Replaced by "Local storage failure handling", which keeps the same 502 behavior for local disk errors.

### Requirement: Health endpoint
**Reason**: It mentions Cloud Run and has a scenario for the Cloud Run URL, and the service no longer runs on Cloud Run.
**Migration**: Replaced by "Health endpoints". The same `/healthz` and `/health` paths return the same response.

## ADDED Requirements

### Requirement: Local storage failure handling
When storing the file or signing its link fails, the system SHALL respond 502 with a generic message that exposes no internal details, and SHALL log the failure details server-side.

#### Scenario: Output directory unwritable
- **WHEN** writing the file to the output directory raises an error, such as a full disk or a permission error
- **THEN** the system responds 502 with a generic error message
- **AND** the response body contains no filesystem path, secret or exception text

### Requirement: Health endpoints
The system SHALL expose `GET /healthz` and `GET /health`, each returning 200 `{"status": "ok"}` without authentication and without touching storage.

#### Scenario: Health check
- **WHEN** any client sends `GET /healthz` or `GET /health`
- **THEN** the system responds 200 `{"status": "ok"}` and makes no storage call

### Requirement: Signed file download endpoint
The system SHALL serve stored files at `GET /files/{key}` without requiring the API key, returning the file only when the request carries an unexpired, valid signature for that key, and SHALL respond 403 for missing, expired or invalid signatures and 404 for a valid signature whose file no longer exists.

#### Scenario: Valid link
- **WHEN** a client opens a `url` returned by `POST /jobs` before it expires
- **THEN** the system responds 200 with the file bytes and its stored Content-Type

#### Scenario: Missing signature
- **WHEN** a client requests `GET /files/{key}` with no signature parameters
- **THEN** the system responds 403

#### Scenario: File removed by retention
- **WHEN** a client uses a validly signed, unexpired link whose file has been deleted
- **THEN** the system responds 404

#### Scenario: Download is not a job request
- **WHEN** a client downloads a file
- **THEN** no `job_request` log line is emitted and the signature is not logged
