# Spec Delta

## MODIFIED Requirements

### Requirement: Cover letter needs posting text
`POST /cover-letter` SHALL always tailor the letter to the stored posting and SHALL NOT fall back to a generic letter. When the application's `full_job_description` is missing, under 50 words or over the posting size limit, it SHALL respond 422 with a message saying the application has no usable posting text, on the POST itself, without starting a job, a Claude run or writing a file.

#### Scenario: No posting text
- **WHEN** a cover letter is requested for an application without `full_job_description`
- **THEN** the system responds 422 with `ok` false and a message about the missing posting text
- **AND** no job record is created or changed, no Claude run starts and no cover letter file is written or replaced

#### Scenario: Posting added later
- **WHEN** the owner adds posting text with `PATCH /application/{id}` and requests the letter again
- **THEN** the system responds 202 and the letter is generated

### Requirement: Cover letter response
When a cover letter request passes its checks, `POST /cover-letter` SHALL start a background job and respond 202 with exactly `{"ok": true, "application_id", "status": "running", "started_at"}`, as defined in `generation-jobs`. Once the job is `done`, `GET /cover-letter/{application_id}/status` SHALL return the PDF's absolute `saved_path` and `text`: the greeting, paragraphs and sign-off as plain text, paragraphs separated by a blank line, with no TeX markup.

#### Scenario: Successful request
- **WHEN** an authenticated client requests a cover letter for application `<id>` with company "Acme Corp" and usable posting text
- **THEN** the system responds 202 with `ok` true, `application_id` `<id>`, `status` `running` and `started_at`, and no other keys
- **AND** once the job is `done`, its `saved_path` is the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf`, and the file there is a one-page PDF of the same letter as its `text`

#### Scenario: Repeated requests
- **WHEN** a cover letter is requested twice for the same application, the second after the first job is `done`
- **THEN** both jobs report the same `saved_path`, and the file holds the second letter

### Requirement: Cover letter is independent of the resume
`POST /cover-letter` and its job SHALL NOT require a resume to have been generated for the application, and SHALL NOT create, replace or delete the application's resume, its stored generation report or its resume job record.

#### Scenario: No resume yet
- **WHEN** a cover letter is requested for an application that has no resume
- **THEN** the letter is generated and saved, and no resume file is created

#### Scenario: Resume left unchanged
- **WHEN** a cover letter is requested for an application whose resume was already generated
- **THEN** the resume file, the report the viewer shows and the resume job record are unchanged

### Requirement: Cover letter generation failure handling
When the Claude run fails, is not configured, runs out of time or budget, or the final gate rejects the letter, or rendering fails, the system SHALL mark the cover letter job `failed` with `error` "Cover letter generation failed". It SHALL log the stage and reason with the `application_id`, without posting or letter text, and SHALL NOT write or replace any cover letter file.

#### Scenario: Gate rejects the letter
- **WHEN** the final gate finds a number that none of the cited sources states
- **THEN** the job is `failed` with the generic `error`, and a previously saved cover letter is left unchanged
- **AND** the log names the failed checks without quoting posting or letter text

#### Scenario: Claude not configured
- **WHEN** no Claude credential is configured
- **THEN** the POST responds 202, the job becomes `failed` with the generic `error`, and the log gives the reason as not configured

### Requirement: Cover letter storage and store failures
When writing the cover letter file fails, the system SHALL mark the job `failed` with `error` "Storage service unavailable", which holds no path or exception text. When the application store cannot be read, or the job record cannot be written, `POST /cover-letter` SHALL respond 503 with a generic message and start no run. Both SHALL log the details server-side with the `application_id`.

#### Scenario: Output directory unwritable
- **WHEN** writing the cover letter to the output directory fails
- **THEN** the job is `failed` with `error` "Storage service unavailable", containing no path

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read
- **THEN** the system responds 503 with `ok` false, and no Claude run starts

### Requirement: Cover letter request logging
The system SHALL emit exactly one structured log line per `POST /cover-letter` request with event `cover_letter_request`, the method, the HTTP status, the duration and, when known, the `application_id`. The Claude run's turns and estimated cost SHALL be recorded on the job's `cover_letter_job` line. Neither line SHALL log the API key, the saved path, the company, or posting or letter text.

#### Scenario: Successful request log
- **WHEN** a cover letter job is started for application `<id>`
- **THEN** one line records event `cover_letter_request`, method `POST`, `application_id` `<id>`, status 202 and the duration
- **AND** when the job finishes, its `cover_letter_job` line records the outcome, the duration, the turns and the cost
- **AND** neither line contains a company name, path, posting text or letter text

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one `cover_letter_request` line records the status and the duration, with no key or body content

### Requirement: Cover letter generation does not block the service
While a cover letter job runs, the service SHALL keep answering health checks, status reads and other API requests.

#### Scenario: Health during generation
- **WHEN** a cover letter job is running
- **THEN** `GET /health` responds 200 without waiting for it
