## MODIFIED Requirements

### Requirement: Job creation response
On success, `POST /resume` SHALL respond 201 with exactly `{"ok": true, "application_id": "<uuid>", "saved_path": "<string>"}`, where `application_id` is the requested ID in lowercase and `saved_path` is the absolute filesystem path of the saved resume file.

#### Scenario: Successful job
- **WHEN** an authenticated client posts `{"application_id": "<id>"}` and application `<id>` exists with company "Acme Corp"
- **THEN** the system responds 201 with `ok` true, `application_id` `<id>` and `saved_path` equal to the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf`, and no other keys
- **AND** the file at `saved_path` is the generated PDF

#### Scenario: Repeated requests for one application
- **WHEN** an authenticated client requests a resume for the same application twice
- **THEN** both respond 201 with the same `saved_path`
- **AND** the file at that path holds the second render

### Requirement: Per-request structured logging
The system SHALL emit exactly one structured log line per `POST /resume` request, with event `resume_request`, HTTP status, duration and, when known, `application_id`, logged only as a lowercase UUID string. It SHALL NOT log secrets, the API key, the saved path, or any request body content other than a well-formed `application_id`.

#### Scenario: Successful request log
- **WHEN** a resume is generated for application `<id>`
- **THEN** one log line records event `resume_request`, `application_id` `<id>`, status 201 and the duration
- **AND** the line does not contain the company name or the saved path

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records event `resume_request`, the status and the duration, with no key or body content

#### Scenario: Unknown application log
- **WHEN** an authenticated client requests a resume for a UUID that names no row
- **THEN** one log line records event `resume_request`, status 404 and the requested `application_id`

#### Scenario: No job_request event
- **WHEN** any request is handled
- **THEN** no `job_request` log line is emitted

## REMOVED Requirements

### Requirement: Resume request body
**Reason**: It required `application_id` to be a JSON integer; IDs are now UUID strings.
**Migration**: Replaced by "Resume request body with UUID". Send `{"application_id": "<uuid>"}` using the string returned by `POST /application`.

### Requirement: Unknown application on resume request
**Reason**: It described unknown IDs as integers that are zero, negative or unassigned.
**Migration**: Replaced by "Unknown application ID on resume request".

## ADDED Requirements

### Requirement: Resume request body with UUID
The system SHALL accept as the `POST /resume` body only a JSON object whose `application_id` is a JSON string, and SHALL ignore other fields. Non-JSON or non-object bodies, or a missing or non-string `application_id`, SHALL get 422 with `{"ok": false, "message": ...}` that does not echo the submitted value, with no lookup, generation or file write.

#### Scenario: Minimal valid body
- **WHEN** an authenticated client sends `{"application_id": "<id>"}` and application `<id>` exists
- **THEN** the system accepts it for processing

#### Scenario: Extra fields ignored
- **WHEN** the body is `{"application_id": "<id>", "company": "Other Co", "full_job_description": "x"}`
- **THEN** the request is processed using application `<id>`'s stored data, and the file is saved under its stored company, not "Other Co"

#### Scenario: Malformed JSON
- **WHEN** an authenticated client sends a body that is not valid JSON
- **THEN** the system responds 422 with `ok` false and a `message`, and no file is written

#### Scenario: Non-object JSON
- **WHEN** an authenticated client sends a JSON array, string, number or null
- **THEN** the system responds 422 with `ok` false and a `message`, and no file is written

#### Scenario: Missing application_id
- **WHEN** the body is `{}`
- **THEN** the system responds 422 naming `application_id`, and no file is written

#### Scenario: Not a string
- **WHEN** `application_id` is `7`, `7.5`, `true`, `null` or an object
- **THEN** the system responds 422 naming `application_id`
- **AND** the response body does not echo the submitted value

### Requirement: Unknown application ID on resume request
When `application_id` is a string that names no stored row, because it was never assigned, was deleted, or is not a hyphenated UUID, `POST /resume` SHALL respond 404 with `{"ok": false, "message": "Application not found"}` and SHALL NOT generate or write anything. UUIDs SHALL be matched in any letter case.

#### Scenario: Never assigned
- **WHEN** an authenticated client sends a random UUID that no row has
- **THEN** the system responds 404 with `ok` false and `message` "Application not found"
- **AND** no file or folder is created

#### Scenario: Deleted application
- **WHEN** application `<id>` is deleted and a client then requests a resume for `<id>`
- **THEN** the system responds 404

#### Scenario: Not a UUID
- **WHEN** `application_id` is `"7"`, `""` or `"not-a-uuid"`
- **THEN** the system responds 404, not 422, and the log line does not contain the value

#### Scenario: Upper case accepted
- **WHEN** `application_id` is an existing row's ID in upper case
- **THEN** the system responds 201 with `application_id` in lower case
