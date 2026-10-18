# job-api Specification

## Purpose

Defines the HTTP interface through which clients submit JSON jobs and receive a link to the generated output file, plus the liveness endpoint used by the hosting platform.

## Requirements

### Requirement: API key authentication on job submission
The system SHALL require the `X-API-Key` header on `POST /resume` to equal the configured API key, and SHALL respond 401 with `{"ok": false, "message": ...}` otherwise, before reading the body, looking up the application, generating output, or writing any file.

#### Scenario: Missing key
- **WHEN** a client sends `POST /resume` without `X-API-Key`
- **THEN** the system responds 401 with `ok` false and a `message`
- **AND** no file is generated or written

#### Scenario: Wrong key
- **WHEN** a client sends `POST /resume` with an `X-API-Key` that does not match
- **THEN** the system responds 401 with `ok` false and a `message`
- **AND** no file is generated or written

#### Scenario: Wrong key with malformed body
- **WHEN** a client sends `POST /resume` with a wrong `X-API-Key` and a body that is not JSON
- **THEN** the system responds 401, not a validation error

#### Scenario: Unknown ID does not leak without key
- **WHEN** a client without a valid key sends `POST /resume` with an `application_id` that names no row
- **THEN** the system responds 401, not 404

### Requirement: Job creation response
On success, `POST /resume` SHALL respond 201 with exactly `{"ok": true, "application_id": "<uuid>", "saved_path": "<string>", "cover_letter_path": "<string>"}`, where `application_id` is the requested ID in lowercase, `saved_path` is the absolute filesystem path of the saved resume file, and `cover_letter_path` is the absolute filesystem path of the application's cover letter file, in the same folder as the resume.

#### Scenario: Successful job
- **WHEN** an authenticated client posts `{"application_id": "<id>"}` and application `<id>` exists with company "Acme Corp"
- **THEN** the system responds 201 with `ok` true, `application_id` `<id>`, `saved_path` equal to the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` and `cover_letter_path` equal to the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf`, and no other keys
- **AND** the file at `saved_path` is the generated PDF

#### Scenario: Cover letter beside the resume
- **WHEN** a resume is generated for any application
- **THEN** `cover_letter_path` and `saved_path` have the same parent folder

#### Scenario: Repeated requests for one application
- **WHEN** an authenticated client requests a resume for the same application twice
- **THEN** both respond 201 with the same `saved_path` and the same `cover_letter_path`
- **AND** the file at `saved_path` holds the second render

#### Scenario: Existing clients unaffected
- **WHEN** a client that reads only `ok`, `application_id` and `saved_path` requests a resume
- **THEN** those fields have the same names, types and values as before this change

### Requirement: Stubbed output generation
For this release the system SHALL produce a PDF by rendering the baseline resume, without altering it based on the application, via a generation interface that accepts the stored application and returns content bytes, a content type and a file extension.

#### Scenario: Stub output content
- **WHEN** a resume is generated for an existing application
- **THEN** the saved file is a valid PDF whose content matches the baseline resume

### Requirement: Per-request structured logging
The system SHALL emit exactly one structured log line per `POST /resume` request, with event `resume_request`, HTTP status, duration and, when known, `application_id`, logged only as a lowercase UUID string. It SHALL NOT log secrets, the API key, the saved path, the cover letter path, or any request body content other than a well-formed `application_id`.

#### Scenario: Successful request log
- **WHEN** a resume is generated for application `<id>`
- **THEN** one log line records event `resume_request`, `application_id` `<id>`, status 201 and the duration
- **AND** the line does not contain the company name, the saved path or the cover letter path

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records event `resume_request`, the status and the duration, with no key or body content

#### Scenario: Unknown application log
- **WHEN** an authenticated client requests a resume for a UUID that names no row
- **THEN** one log line records event `resume_request`, status 404 and the requested `application_id`

#### Scenario: No job_request event
- **WHEN** any request is handled
- **THEN** no `job_request` log line is emitted

### Requirement: Render failure handling
When PDF rendering fails or exceeds its time limit, the system SHALL respond 500 with `{"ok": false, "message": ...}` using a generic message that exposes no TeX output or paths, SHALL log the details server-side with the `application_id`, and SHALL NOT write or replace any resume file.

#### Scenario: Render error
- **WHEN** the TeX compilation fails
- **THEN** the system responds 500 with `ok` false and a generic `message`
- **AND** no resume file is written, and a previously saved resume for that application is left unchanged
- **AND** the failure details are logged with the `application_id`

### Requirement: Local storage failure handling
When writing the resume file or creating its folders fails, the system SHALL respond 502 with `{"ok": false, "message": ...}` using a generic message that exposes no internal details, and SHALL log the failure details server-side with the `application_id`.

#### Scenario: Output directory unwritable
- **WHEN** writing the file to the output directory raises an error, such as a full disk or a permission error
- **THEN** the system responds 502 with `ok` false and a generic `message`
- **AND** the response body contains no filesystem path, secret or exception text

### Requirement: Health endpoints
The system SHALL expose `GET /healthz` and `GET /health`, each returning 200 `{"status": "ok"}` without authentication and without touching storage.

#### Scenario: Health check
- **WHEN** any client sends `GET /healthz` or `GET /health`
- **THEN** the system responds 200 `{"status": "ok"}` and makes no storage call

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

### Requirement: Generation uses the stored application
The system SHALL generate the resume from the application row as stored at request time. It SHALL NOT require any input besides `application_id`, and SHALL accept a row whose optional fields, including `full_job_description`, are null.

#### Scenario: Updated details are used
- **WHEN** application 7's `role` is changed with `PATCH` and a resume is then requested for 7
- **THEN** generation receives the updated `role`

#### Scenario: No job description stored
- **WHEN** application 7 was recorded without `full_job_description`
- **THEN** a resume request for 7 responds 201

### Requirement: Resume generation leaves the application unchanged
A `POST /resume` request SHALL NOT modify the application row, including its `status` and `updated_at`, and SHALL be allowed for an application in any status.

#### Scenario: Status unchanged
- **WHEN** a resume is generated for an application with status `verified`
- **THEN** its status is still `verified` and its `updated_at` is unchanged

#### Scenario: Closed application
- **WHEN** a resume is requested for an application with status `rejected` or `withdrawn`
- **THEN** the system responds 201

### Requirement: Application store failure on resume request
When the application store cannot be read, `POST /resume` SHALL respond 503 with `{"ok": false, "message": ...}` using a generic message that exposes no path or exception text, SHALL log the details server-side, and SHALL NOT generate or write anything.

#### Scenario: Store unavailable
- **WHEN** reading the application row raises a database or filesystem error
- **THEN** the system responds 503 with `ok` false and a generic `message`
- **AND** the body contains no filesystem path or exception text, and no file is written

### Requirement: Legacy jobs path removed
The system SHALL NOT serve `POST /jobs`. A request to it SHALL be handled as an unknown path, generating and writing nothing and emitting no `resume_request` log line.

#### Scenario: Old client
- **WHEN** a client with a valid `X-API-Key` sends a job posting to `POST /jobs`
- **THEN** the system responds 404 and no file is generated or written
