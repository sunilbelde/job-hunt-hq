# Spec Delta

## MODIFIED Requirements

### Requirement: Job creation response
On success, `POST /resume` SHALL respond 201 with exactly `{"ok": true, "application_id": "<uuid>", "saved_path": "<string>", "match": {...}}`, where `application_id` is the requested ID in lowercase, `saved_path` is the absolute filesystem path of the saved resume file, and `match` describes how the resume was chosen. It SHALL NOT return a cover letter path; cover letters come only from `POST /cover-letter`.

#### Scenario: Successful job
- **WHEN** an authenticated client posts `{"application_id": "<id>"}` and application `<id>` exists with company "Acme Corp"
- **THEN** the system responds 201 with `ok` true, `application_id` `<id>`, `saved_path` equal to the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` and a `match` object, and no other keys
- **AND** the file at `saved_path` is the generated PDF

#### Scenario: Cover letter beside the resume
- **WHEN** a resume is generated for any application
- **THEN** the response has no `cover_letter_path` key, and no cover letter file beside the resume is created, replaced or deleted

#### Scenario: Repeated requests for one application
- **WHEN** an authenticated client requests a resume for the same application twice
- **THEN** both respond 201 with the same `saved_path`
- **AND** the file at `saved_path` holds the second render

#### Scenario: Existing clients unaffected
- **WHEN** a client that reads only `ok`, `application_id`, `saved_path` and `match` requests a resume
- **THEN** those fields have the same names, types and values as before this change

### Requirement: Per-request structured logging
The system SHALL emit exactly one structured log line per `POST /resume` request, with event `resume_request`, HTTP status, duration and, when known, `application_id`, logged only as a lowercase UUID string. It SHALL NOT log secrets, the API key, the saved path, posting or resume text, or any request body content other than a well-formed `application_id`.

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
