## MODIFIED Requirements

### Requirement: API key authentication on application recording
The system SHALL require the `X-API-Key` header on `POST /application`, `PATCH /application/{application_id}` and `DELETE /application/{application_id}` to equal the configured API key, and SHALL respond 401 with `{"ok": false, "message": ...}` otherwise, before reading the body, looking up the application ID or touching the application store.

#### Scenario: Missing key
- **WHEN** a client sends `POST /application` without `X-API-Key`
- **THEN** the system responds 401 with `ok` false and a `message`
- **AND** no row is created

#### Scenario: Wrong key with malformed body
- **WHEN** a client sends `POST /application` with a wrong `X-API-Key` and a body that is not JSON
- **THEN** the system responds 401, not a validation error

#### Scenario: Wrong key on update
- **WHEN** a client sends `PATCH /application/<id>` for an existing row with a wrong `X-API-Key` and a valid body
- **THEN** the system responds 401 and the row is unchanged

#### Scenario: Wrong key on delete
- **WHEN** a client sends `DELETE /application/<id>` for an existing row with a wrong `X-API-Key`
- **THEN** the system responds 401 and the row still exists

#### Scenario: Unknown ID does not leak without key
- **WHEN** a client without a valid key sends `PATCH` or `DELETE` to an ID that does not exist or is not a UUID
- **THEN** the system responds 401, not 404

### Requirement: Application recording response
For a `job_link` not yet stored, `POST /application` SHALL create a row and respond 201 with exactly `{"ok": true, "application_id": "<uuid>"}`, where `application_id` is the new row's ID as a lowercase, hyphenated UUID string.

#### Scenario: New application
- **WHEN** an authenticated client posts a valid body whose `job_link` is not in the store
- **THEN** the system responds 201 with `ok` true and a UUID string `application_id`
- **AND** the body has no other keys

### Requirement: Per-request application logging
The system SHALL emit exactly one structured log line per `POST /application`, `PATCH /application/{application_id}` or `DELETE /application/{application_id}` request with event `application_request`, the HTTP `method`, HTTP status, duration and, when known, `application_id` and (for `POST`) whether it was a duplicate. `application_id` SHALL be logged only as a lowercase UUID string, and a path value that is not a UUID SHALL NOT be logged. It SHALL NOT log the API key or any request body field.

#### Scenario: New application log
- **WHEN** a new application is recorded
- **THEN** one log line records method `POST`, status 201, the `application_id`, `duplicate` false and the duration

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records the status and duration, with no key or body content

#### Scenario: Update log
- **WHEN** application `<id>` is updated to status `applied`
- **THEN** one log line records method `PATCH`, status 200, `application_id` `<id>` and the duration
- **AND** the line does not contain `applied` or any other body value

#### Scenario: Delete of unknown ID log
- **WHEN** an authenticated client deletes an ID that does not exist
- **THEN** one log line records method `DELETE` and status 404

#### Scenario: Job requests unaffected
- **WHEN** a client calls any application endpoint
- **THEN** no `resume_request` log line is emitted
- **AND** a `POST /resume` request emits no `application_request` log line

#### Scenario: Malformed path ID not logged
- **WHEN** an authenticated client sends `DELETE /application/not-a-uuid`
- **THEN** the log line records method `DELETE` and status 404, and does not contain `not-a-uuid`

### Requirement: Default status on recording
A row created by `POST /application` SHALL have status `verified`. A duplicate `POST` SHALL NOT change the existing row's status, and the `POST` response body SHALL remain exactly `{"ok": true, "application_id": "<uuid>"}`.

#### Scenario: New row is verified
- **WHEN** a new application is recorded
- **THEN** its status is `verified`

#### Scenario: Duplicate keeps advanced status
- **WHEN** an application's status was updated to `interviewing` and the same `job_link` is posted again
- **THEN** the response is 200 with the existing ID and the status is still `interviewing`

### Requirement: Application update response
A successful update SHALL respond 200 with exactly `{"ok": true, "application_id": "<uuid>", "status": "<status after the update>"}`, where `application_id` is the row's ID in lowercase.

#### Scenario: Update response shape
- **WHEN** an authenticated client sends `{"salary": "$150k"}` to application `<id>`, whose status is `applied`
- **THEN** the response is 200 with body `{"ok": true, "application_id": "<id>", "status": "applied"}` and no other keys

### Requirement: Application delete endpoint
`DELETE /application/{application_id}` SHALL permanently remove the row and respond 200 with exactly `{"ok": true, "application_id": "<uuid>"}`, where `application_id` is the removed row's ID in lowercase. Any request body SHALL be ignored.

#### Scenario: Delete existing
- **WHEN** an authenticated client deletes application `<id>`
- **THEN** the response is 200 with body `{"ok": true, "application_id": "<id>"}` and no other keys
- **AND** a later `PATCH` or `DELETE` of `<id>` responds 404

#### Scenario: Re-record after delete
- **WHEN** application `<id>` with a given `job_link` is deleted and the same `job_link` is posted again
- **THEN** the response is 201 with a new `application_id` different from `<id>`, and the new row's status is `verified`

## REMOVED Requirements

### Requirement: Unknown application ID
**Reason**: It defined unknown IDs in terms of positive base-10 integers, which are no longer IDs.
**Migration**: Replaced by "Unknown application ID in path". Old integer IDs now respond 404; clients must use the UUID returned by `POST /application`.

## ADDED Requirements

### Requirement: Unknown application ID in path
`application_id` in the path SHALL be matched as a hyphenated UUID in any letter case. When it does not identify a stored row, because it was never assigned, was deleted, or is not a UUID (including an integer), `PATCH` and `DELETE` SHALL respond 404 with `{"ok": false, "message": "Application not found"}` and change nothing. An authenticated request for an unknown ID SHALL be reported as 404 even when its body is also invalid.

#### Scenario: Never assigned
- **WHEN** an authenticated client sends `PATCH /application/<random uuid>` with `{"status": "applied"}` and no such row exists
- **THEN** the system responds 404 with `ok` false and `message` "Application not found", and no row is created

#### Scenario: Not a UUID
- **WHEN** an authenticated client sends `DELETE /application/abc`, `/application/1`, `/application/0` or `/application/-1`
- **THEN** the system responds 404 with `ok` false and a `message`, not a framework validation error

#### Scenario: Upper case accepted
- **WHEN** an authenticated client sends `PATCH /application/<id in upper case>` for an existing row
- **THEN** the row is updated and the response carries `<id>` in lower case

#### Scenario: Unknown ID with bad body
- **WHEN** an authenticated client sends `PATCH /application/<random uuid>` with a body that is not JSON and no such row exists
- **THEN** the system responds 404

#### Scenario: Delete twice
- **WHEN** an authenticated client deletes the same existing ID twice
- **THEN** the first response is 200 and the second is 404
