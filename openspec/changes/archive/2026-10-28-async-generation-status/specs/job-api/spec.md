# Spec Delta

## MODIFIED Requirements

### Requirement: Job creation response
When a resume request passes its checks, `POST /resume` SHALL start a background resume job and respond 202 with exactly `{"ok": true, "application_id": "<uuid>", "status": "running", "started_at": "<timestamp>"}`, as defined in `generation-jobs`. The saved path and match SHALL be read from `GET /resume/{application_id}/status`. Generation SHALL NOT write a cover letter; cover letters come only from `POST /cover-letter`.

#### Scenario: Successful job
- **WHEN** an authenticated client posts `{"application_id": "<id>"}` and application `<id>` exists with company "Acme Corp"
- **THEN** the system responds 202 with `ok` true, `application_id` `<id>`, `status` `running` and `started_at`, and no other keys
- **AND** once the job is `done`, its `saved_path` is the absolute path of `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` and the file there is the generated PDF

#### Scenario: Cover letter beside the resume
- **WHEN** a resume is generated for any application
- **THEN** no cover letter file beside the resume is created, replaced or deleted, and the resume job record has no `text`

#### Scenario: Repeated requests for one application
- **WHEN** an authenticated client requests a resume for the same application twice, the second after the first job is `done`
- **THEN** both jobs report the same `saved_path`
- **AND** the file at `saved_path` holds the second render

#### Scenario: Existing clients unaffected
- **WHEN** a client that reads `application_id`, `saved_path` and `match` requests a resume and its job finishes
- **THEN** `GET /resume/{application_id}/status` returns those fields with the same names, types and values `POST /resume` returned before this change
- **AND** the POST response itself is never 201 and never holds `saved_path` or `match`

### Requirement: Per-request structured logging
The system SHALL emit exactly one structured log line per `POST /resume` request, with event `resume_request`, method, HTTP status, duration and, when known, `application_id`, logged only as a lowercase UUID string. It SHALL NOT log secrets, the API key, the saved path, posting or resume text, or any request body content other than a well-formed `application_id`. The run's outcome is logged by the job's own `resume_job` line.

#### Scenario: Successful request log
- **WHEN** a resume job is started for application `<id>`
- **THEN** one log line records event `resume_request`, method `POST`, `application_id` `<id>`, status 202 and the duration
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

### Requirement: Generation failure handling
When PDF rendering fails or exceeds its time limit, or tailoring fails because Claude is not configured, unavailable or over a limit, because the judge's output is unusable, or because content fails a check, the system SHALL mark the resume job `failed` with `error` "Resume generation failed", exposing no TeX, Claude or check output, posting text or paths. It SHALL log the details server-side with the `application_id`, and SHALL NOT write or replace any resume file.

#### Scenario: Render error
- **WHEN** the TeX compilation fails
- **THEN** the resume job is `failed` with the generic `error`
- **AND** no resume file is written, and a previously saved resume for that application is left unchanged
- **AND** the failure details are logged with the `application_id`

#### Scenario: Claude not configured
- **WHEN** no Claude credential is configured and a resume is requested for an application with usable posting text
- **THEN** the POST responds 202, the job becomes `failed` with `error` "Resume generation failed", and the log gives the reason as not configured

#### Scenario: Claude run fails
- **WHEN** the analysis, judge or tailoring run exits with an error, or the runs use up the time limit or reach the spend cap
- **THEN** the job is `failed` with the generic `error`, and no resume file is written or replaced

#### Scenario: Content fails a check
- **WHEN** the final gate rejects the tailored content, for example because it does not fit on one page or names a skill the base resume lacks
- **THEN** the job is `failed` with the generic `error`, and a previously saved resume for that application is left unchanged
- **AND** the log names the failed checks without quoting posting or resume text

### Requirement: Local storage failure handling
When writing the resume file or creating its folders fails, the system SHALL mark the resume job `failed` with `error` "Storage service unavailable", exposing no internal details, and SHALL log the failure details server-side with the `application_id`.

#### Scenario: Output directory unwritable
- **WHEN** writing the file to the output directory raises an error, such as a full disk or a permission error
- **THEN** the resume job is `failed` with `error` "Storage service unavailable"
- **AND** the job record contains no filesystem path, secret or exception text

### Requirement: Unknown application ID on resume request
When `application_id` is a string that names no stored row, because it was never assigned, was deleted, or is not a hyphenated UUID, `POST /resume` SHALL respond 404 with `{"ok": false, "message": "Application not found"}` and SHALL NOT start a job, generate or write anything. UUIDs SHALL be matched in any letter case.

#### Scenario: Never assigned
- **WHEN** an authenticated client sends a random UUID that no row has
- **THEN** the system responds 404 with `ok` false and `message` "Application not found"
- **AND** no file, folder or job record is created

#### Scenario: Deleted application
- **WHEN** application `<id>` is deleted and a client then requests a resume for `<id>`
- **THEN** the system responds 404

#### Scenario: Not a UUID
- **WHEN** `application_id` is `"7"`, `""` or `"not-a-uuid"`
- **THEN** the system responds 404, not 422, and the log line does not contain the value

#### Scenario: Upper case accepted
- **WHEN** `application_id` is an existing row's ID in upper case
- **THEN** the system responds 202 with `application_id` in lower case

### Requirement: Generation uses the stored application
The system SHALL generate the resume from the application row as stored when the job starts. It SHALL NOT require any input besides `application_id`, and SHALL accept a row whose optional fields, including `full_job_description`, are null.

#### Scenario: Updated details are used
- **WHEN** application 7's `role` is changed with `PATCH` and a resume is then requested for 7
- **THEN** generation receives the updated `role`

#### Scenario: Updated posting text is used
- **WHEN** application 7's `full_job_description` is changed with `PATCH` and a resume is then requested for 7
- **THEN** the resume is scored against the new posting text

#### Scenario: No job description stored
- **WHEN** application 7 was recorded without `full_job_description`
- **THEN** a resume request for 7 responds 202, and the job finishes `done` with the base resume and `match.status` `no_job_description`

### Requirement: Resume generation leaves the application unchanged
A resume request and its job SHALL NOT modify the application row, including its `status` and `updated_at`, and SHALL be allowed for an application in any status.

#### Scenario: Status unchanged
- **WHEN** a resume is generated for an application with status `verified`
- **THEN** its status is still `verified` and its `updated_at` is unchanged

#### Scenario: Closed application
- **WHEN** a resume is requested for an application with status `rejected` or `withdrawn`
- **THEN** the system responds 202 and the job runs

### Requirement: Application store failure on resume request
When the application store cannot be read, or the job record cannot be written, `POST /resume` SHALL respond 503 with `{"ok": false, "message": ...}` using a generic message that exposes no path or exception text, SHALL log the details server-side, and SHALL NOT start a run or write anything.

#### Scenario: Store unavailable
- **WHEN** reading the application row raises a database or filesystem error
- **THEN** the system responds 503 with `ok` false and a generic `message`
- **AND** the body contains no filesystem path or exception text, and no file is written

#### Scenario: Job record not writable
- **WHEN** the application exists but its job record cannot be written
- **THEN** the system responds 503 and no Claude run starts

### Requirement: Match result in the response
A done resume job's `match` SHALL hold `status`, `threshold`, `base_score`, `tailored_score` and `added_terms`. `status` SHALL be `no_job_description` (posting text unusable, base resume saved unscored), `base_meets_threshold` (base resume met the threshold) or `tailored` (tailored resume saved). `threshold` SHALL be 70. Scores SHALL be integers from 0 to 100, or null when not computed. `added_terms` SHALL list the judge-approved posting keywords the tailored resume uses, empty unless tailored.

#### Scenario: Not scored
- **WHEN** a resume is generated for an application without posting text
- **THEN** `match` is `{"status": "no_job_description", "threshold": 70, "base_score": null, "tailored_score": null, "added_terms": []}`

#### Scenario: Base resume kept
- **WHEN** the base resume scores 82 against the posting
- **THEN** `match` is `{"status": "base_meets_threshold", "threshold": 70, "base_score": 82, "tailored_score": null, "added_terms": []}` and the saved file is the base resume

#### Scenario: Tailored
- **WHEN** the base resume scores 58, the tailored resume scores 77 and uses the approved keyword "testing"
- **THEN** `match` is `{"status": "tailored", "threshold": 70, "base_score": 58, "tailored_score": 77, "added_terms": ["testing"]}` and the saved file is the tailored resume

### Requirement: Match details in the request log
When a resume job reaches scoring, its `resume_job` line SHALL also record the match status, the base and tailored scores, the Claude runs' total number of turns and estimated cost and, when the resume was tailored, how many keywords the judge approved and rejected.

#### Scenario: Tailored request log
- **WHEN** a resume is tailored for application `<id>`
- **THEN** its `resume_job` line records match status `tailored`, the base score, the tailored score, the number of Claude turns, the estimated cost and the judge's approved and rejected counts
- **AND** the line contains no posting text, resume text, keywords or skill names

#### Scenario: Failed tailoring log
- **WHEN** tailoring fails for application `<id>`
- **THEN** its `resume_job` line has outcome `failed`, and the stage and reason are logged with the `application_id` without posting or resume text

### Requirement: Resume generation does not block the service
While a resume job runs, which can take several minutes, the service SHALL keep answering health checks, status reads and other API requests.

#### Scenario: Health during a long generation
- **WHEN** a resume job is running
- **THEN** `GET /health` responds 200 without waiting for it

#### Scenario: Status during a long generation
- **WHEN** a resume job is running
- **THEN** `GET /resume/{application_id}/status` responds 200 with `status` `running` without waiting for it
