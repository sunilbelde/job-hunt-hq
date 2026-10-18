# Spec Delta

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
- **WHEN** a client sends `PATCH /application/1` with a wrong `X-API-Key` and a valid body
- **THEN** the system responds 401 and row 1 is unchanged

#### Scenario: Wrong key on delete
- **WHEN** a client sends `DELETE /application/1` with a wrong `X-API-Key`
- **THEN** the system responds 401 and row 1 still exists

#### Scenario: Unknown ID does not leak without key
- **WHEN** a client without a valid key sends `PATCH` or `DELETE` to an ID that does not exist
- **THEN** the system responds 401, not 404

### Requirement: Application store failure handling
When the application store cannot be read or written, `POST /application`, `PATCH /application/{application_id}` and `DELETE /application/{application_id}` SHALL respond 503 with `{"ok": false, "message": ...}` using a generic message that exposes no path or exception text, and SHALL log the details server-side.

#### Scenario: Store unavailable
- **WHEN** writing the row raises a database or filesystem error
- **THEN** the system responds 503 with `ok` false and a generic `message`
- **AND** the body contains no filesystem path or exception text

#### Scenario: Store unavailable on update or delete
- **WHEN** an authenticated `PATCH` or `DELETE` with a valid request hits a database error
- **THEN** the system responds 503 with `ok` false and a generic `message` containing no path or exception text

### Requirement: Per-request application logging
The system SHALL emit exactly one structured log line per `POST /application`, `PATCH /application/{application_id}` or `DELETE /application/{application_id}` request with event `application_request`, the HTTP `method`, HTTP status, duration and, when known, `application_id` and (for `POST`) whether it was a duplicate. It SHALL NOT log the API key or any request body field.

#### Scenario: New application log
- **WHEN** a new application is recorded
- **THEN** one log line records method `POST`, status 201, the `application_id`, `duplicate` false and the duration

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records the status and duration, with no key or body content

#### Scenario: Update log
- **WHEN** application 7 is updated to status `applied`
- **THEN** one log line records method `PATCH`, status 200, `application_id` 7 and the duration
- **AND** the line does not contain `applied` or any other body value

#### Scenario: Delete of unknown ID log
- **WHEN** an authenticated client deletes an ID that does not exist
- **THEN** one log line records method `DELETE` and status 404

#### Scenario: Job requests unaffected
- **WHEN** a client calls any application endpoint
- **THEN** no `job_request` log line is emitted

## ADDED Requirements

### Requirement: Application status values
Every application SHALL have a `status` that is exactly one of `verified`, `applied`, `interviewing`, `offer`, `rejected` or `withdrawn`. Matching SHALL be case-sensitive, and any other value supplied by a client SHALL be rejected with 422 naming `status`.

#### Scenario: Unknown status
- **WHEN** an update body sets `status` to "ghosted"
- **THEN** the system responds 422 naming `status`, and the row is unchanged

#### Scenario: Wrong case
- **WHEN** an update body sets `status` to "Applied"
- **THEN** the system responds 422 naming `status`

#### Scenario: Status value not echoed
- **WHEN** an update body sets `status` to "secret-ish-value"
- **THEN** the response body does not contain "secret-ish-value"

### Requirement: Default status on recording
A row created by `POST /application` SHALL have status `verified`. A duplicate `POST` SHALL NOT change the existing row's status, and the `POST` response body SHALL remain exactly `{"ok": true, "application_id": <integer>}`.

#### Scenario: New row is verified
- **WHEN** a new application is recorded
- **THEN** its status is `verified`

#### Scenario: Duplicate keeps advanced status
- **WHEN** an application's status was updated to `interviewing` and the same `job_link` is posted again
- **THEN** the response is 200 with the existing ID and the status is still `interviewing`

### Requirement: Application update endpoint
`PATCH /application/{application_id}` SHALL accept a JSON object and change only the updatable fields present in it, leaving every other stored field unchanged. Non-JSON or non-object bodies SHALL be rejected with 422 and `{"ok": false, "message": ...}` without changing the row.

#### Scenario: Status change only
- **WHEN** an authenticated client sends `{"status": "applied"}` to an existing application
- **THEN** its status becomes `applied` and every other stored field is unchanged

#### Scenario: Correct a stale salary
- **WHEN** the body is `{"salary": "$150k"}`
- **THEN** the stored `salary` becomes "$150k" and the status is unchanged

#### Scenario: Same status again
- **WHEN** the body sets `status` to the row's current status
- **THEN** the system responds 200

#### Scenario: Malformed body
- **WHEN** the body is not valid JSON, or is a JSON array, string, number or null
- **THEN** the system responds 422 with `ok` false and a `message`, and the row is unchanged

### Requirement: Updatable application fields
An update SHALL accept `status`; `company` and `role` as non-empty strings; and `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain` and `full_job_description` as a string or `null`, where `null` clears the field. No value SHALL be parsed or normalized, and unknown fields SHALL be ignored.

#### Scenario: Clear an optional field
- **WHEN** the body is `{"sponsorship": null}`
- **THEN** the stored `sponsorship` becomes null

#### Scenario: Required field cannot be emptied
- **WHEN** the body sets `company` to "" or `null`, or `status` to `null`
- **THEN** the system responds 422 naming that field, and the row is unchanged

#### Scenario: Wrong type
- **WHEN** the body sets `salary` to a number
- **THEN** the system responds 422 naming `salary`

#### Scenario: Unknown field ignored
- **WHEN** the body is `{"status": "applied", "found": true}`
- **THEN** the status is updated and `found` is not stored

#### Scenario: Nothing to update
- **WHEN** the body is `{}` or contains only unknown fields
- **THEN** the system responds 422 with a `message`, and the row is unchanged

### Requirement: Immutable application fields
`job_link`, `posting_source_type`, `verification_method` and `official_apply_url` SHALL NOT be changeable. An update body that contains any of them, with any value including the stored one, SHALL be rejected with 422 naming each such field, and no field of the row SHALL change.

#### Scenario: Changing job_link
- **WHEN** the body is `{"job_link": "https://example.com/jobs/2", "status": "applied"}`
- **THEN** the system responds 422 naming `job_link`, and neither field changes

#### Scenario: Resending the stored value
- **WHEN** the body sets `verification_method` to the row's current value
- **THEN** the system responds 422 naming `verification_method`

### Requirement: Application update response
A successful update SHALL respond 200 with exactly `{"ok": true, "application_id": <integer>, "status": "<status after the update>"}`.

#### Scenario: Update response shape
- **WHEN** an authenticated client sends `{"salary": "$150k"}` to application 7, whose status is `applied`
- **THEN** the response is 200 with body `{"ok": true, "application_id": 7, "status": "applied"}` and no other keys

### Requirement: Application delete endpoint
`DELETE /application/{application_id}` SHALL permanently remove the row and respond 200 with exactly `{"ok": true, "application_id": <integer>}`. Any request body SHALL be ignored.

#### Scenario: Delete existing
- **WHEN** an authenticated client deletes application 7
- **THEN** the response is 200 with body `{"ok": true, "application_id": 7}` and no other keys
- **AND** a later `PATCH` or `DELETE` of 7 responds 404

#### Scenario: Re-record after delete
- **WHEN** application 7 with a given `job_link` is deleted and the same `job_link` is posted again
- **THEN** the response is 201 with a new `application_id` larger than 7, and the new row's status is `verified`

### Requirement: Unknown application ID
When `application_id` in the path does not identify a stored row, because it was never assigned, was deleted, or is not a positive base-10 integer, `PATCH` and `DELETE` SHALL respond 404 with `{"ok": false, "message": "Application not found"}` and change nothing. An authenticated request for an unknown ID SHALL be reported as 404 even when its body is also invalid.

#### Scenario: Never assigned
- **WHEN** an authenticated client sends `PATCH /application/999999` with `{"status": "applied"}` and no such row exists
- **THEN** the system responds 404 with `ok` false and `message` "Application not found", and no row is created

#### Scenario: Not an integer
- **WHEN** an authenticated client sends `DELETE /application/abc`, `/application/0` or `/application/-1`
- **THEN** the system responds 404 with `ok` false and a `message`, not a framework validation error

#### Scenario: Unknown ID with bad body
- **WHEN** an authenticated client sends `PATCH /application/999999` with a body that is not JSON
- **THEN** the system responds 404

#### Scenario: Delete twice
- **WHEN** an authenticated client deletes the same existing ID twice
- **THEN** the first response is 200 and the second is 404
