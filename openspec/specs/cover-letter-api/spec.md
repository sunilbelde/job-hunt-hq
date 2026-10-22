# cover-letter-api Specification

## Purpose
Defines `POST /cover-letter`, the endpoint that writes a cover letter tailored to a recorded application's posting, only for the applications that ask for one, and saves it beside the resume.

## Requirements

### Requirement: API key authentication on cover letter requests
The system SHALL require the `X-API-Key` header on `POST /cover-letter` to equal the configured API key, and SHALL respond 401 with `{"ok": false, "message": ...}` otherwise, before reading the body, looking up the application, starting a Claude run or writing any file.

#### Scenario: Missing key
- **WHEN** a client sends `POST /cover-letter` without `X-API-Key`
- **THEN** the system responds 401 with `ok` false and a `message`, and no Claude run starts and no file is written

#### Scenario: Wrong key with malformed body
- **WHEN** a client sends `POST /cover-letter` with a wrong `X-API-Key` and a body that is not JSON
- **THEN** the system responds 401, not a validation error

#### Scenario: Unknown ID does not leak without key
- **WHEN** a client without a valid key sends an `application_id` that names no row
- **THEN** the system responds 401, not 404

### Requirement: Cover letter request body
`POST /cover-letter` SHALL take a JSON object with a string `application_id`, validated exactly as for `POST /resume`. Extra fields SHALL be ignored. A body that is not JSON, not an object, or whose `application_id` is missing or not a string SHALL get a 422 naming `application_id` but never its value. A string that is not a hyphenated UUID or names no stored application SHALL get a 404.

#### Scenario: Valid body
- **WHEN** an authenticated client posts `{"application_id": "<id>", "note": "x"}` and `<id>` exists with usable posting text
- **THEN** the extra field is ignored and the letter is generated

#### Scenario: Non-string ID
- **WHEN** an authenticated client posts `{"application_id": 7}`
- **THEN** the system responds 422 naming `application_id`, and no file is written

#### Scenario: Unknown or malformed ID
- **WHEN** an authenticated client posts an `application_id` that is not a UUID, or a UUID that names no row
- **THEN** the system responds 404 with `ok` false, and no file is written

### Requirement: Cover letter needs posting text
`POST /cover-letter` SHALL always tailor the letter to the stored posting and SHALL NOT fall back to a generic letter. When the application's `full_job_description` is missing, under 50 words or over the posting size limit, it SHALL respond 422 with a message saying the application has no usable posting text, without starting a Claude run or writing a file.

#### Scenario: No posting text
- **WHEN** a cover letter is requested for an application without `full_job_description`
- **THEN** the system responds 422 with `ok` false and a message about the missing posting text
- **AND** no Claude run starts and no cover letter file is written or replaced

#### Scenario: Posting added later
- **WHEN** the owner adds posting text with `PATCH /application/{id}` and requests the letter again
- **THEN** the letter is generated

### Requirement: Cover letter response
On success, `POST /cover-letter` SHALL respond 201 with exactly `{"ok": true, "application_id": "<uuid>", "saved_path": "<string>", "text": "<string>"}`. `application_id` SHALL be the requested ID in lowercase, `saved_path` the absolute path of the saved PDF, and `text` the letter's greeting, paragraphs and sign-off as plain text with paragraphs separated by a blank line and no TeX markup.

#### Scenario: Successful request
- **WHEN** an authenticated client requests a cover letter for application `<id>` with company "Acme Corp" and usable posting text
- **THEN** the system responds 201 with `ok` true, `application_id` `<id>`, `saved_path` equal to the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf`, and `text`, and no other keys
- **AND** the file at `saved_path` is a one-page PDF of the same letter as `text`

#### Scenario: Repeated requests
- **WHEN** a cover letter is requested twice for the same application
- **THEN** both respond 201 with the same `saved_path`, and the file holds the second letter

### Requirement: Cover letter is independent of the resume
`POST /cover-letter` SHALL NOT require a resume to have been generated for the application, and SHALL NOT create, replace or delete the application's resume or its stored generation report.

#### Scenario: No resume yet
- **WHEN** a cover letter is requested for an application that has no resume
- **THEN** the letter is generated and saved, and no resume file is created

#### Scenario: Resume left unchanged
- **WHEN** a cover letter is requested for an application whose resume was already generated
- **THEN** the resume file and the report the viewer shows are unchanged

### Requirement: Cover letter request leaves the application unchanged
Generating a cover letter SHALL NOT change the stored application, its status included, and SHALL work for any status.

#### Scenario: Applied application
- **WHEN** a cover letter is requested for an application with status `applied`
- **THEN** the letter is generated and the status is still `applied`

### Requirement: Cover letter generation failure handling
When the Claude run fails, is not configured, runs out of time or budget, or the final gate rejects the letter, or rendering fails, the system SHALL respond 500 with `{"ok": false, "message": "Cover letter generation failed"}`. It SHALL log the stage and reason with the `application_id`, without posting or letter text, and SHALL NOT write or replace any cover letter file.

#### Scenario: Gate rejects the letter
- **WHEN** the final gate finds a number that none of the cited sources states
- **THEN** the system responds 500 with the generic message, and a previously saved cover letter is left unchanged
- **AND** the log names the failed checks without quoting posting or letter text

#### Scenario: Claude not configured
- **WHEN** no Claude credential is configured
- **THEN** the system responds 500 with the generic message, and the log gives the reason as not configured

### Requirement: Cover letter storage and store failures
When writing the cover letter file fails, `POST /cover-letter` SHALL respond 502 with a generic message that exposes no path or exception text. When the application store cannot be read, it SHALL respond 503 the same way. Both SHALL log the details server-side with the `application_id`.

#### Scenario: Output directory unwritable
- **WHEN** writing the cover letter to the output directory fails
- **THEN** the system responds 502 with `ok` false and a generic `message` containing no path

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read
- **THEN** the system responds 503 with `ok` false, and no Claude run starts

### Requirement: Cover letter request logging
The system SHALL emit exactly one structured log line per `POST /cover-letter` request with event `cover_letter_request`, the HTTP status, the duration and, when known, the `application_id`. When a Claude run happened, the line SHALL also record its turns and estimated cost. It SHALL NOT log the API key, the saved path, the company, or posting or letter text.

#### Scenario: Successful request log
- **WHEN** a cover letter is generated for application `<id>`
- **THEN** one line records event `cover_letter_request`, `application_id` `<id>`, status 201, the duration, the turns and the cost
- **AND** the line contains no company name, path, posting text or letter text

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one `cover_letter_request` line records the status and the duration, with no key or body content

### Requirement: Cover letter generation does not block the service
While a cover letter is generated, the service SHALL keep answering health checks and other API requests.

#### Scenario: Health during generation
- **WHEN** a `POST /cover-letter` request is in progress
- **THEN** `GET /health` responds 200 without waiting for it
