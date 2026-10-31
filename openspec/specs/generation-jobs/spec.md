# generation-jobs Specification

## Purpose

Runs resume and cover letter generation in the background and records each run's state and result per application, so clients whose connections drop before a run finishes can poll the public status endpoints for the outcome.

## Requirements

### Requirement: Background generation runs
After `POST /resume` or `POST /cover-letter` passes its synchronous checks, the system SHALL start the run in the background and respond 202 without waiting for it to finish. The run SHALL continue after the client disconnects.

#### Scenario: Client disconnects during a run
- **WHEN** a client requests a resume for an application with posting text and closes its connection after 202 arrives
- **THEN** the run continues, and the resume is saved and recorded on the job when it finishes

#### Scenario: Response before the run finishes
- **WHEN** an authenticated client requests a cover letter whose run takes 3 minutes
- **THEN** the system responds 202 without waiting for the run

### Requirement: Accepted response
The 202 response SHALL be exactly `{"ok": true, "application_id": "<uuid>", "status": "running", "started_at": "<timestamp>"}`. `application_id` SHALL be the lowercase ID. `started_at` SHALL be the job's start time as an ISO 8601 UTC timestamp ending in `Z`.

#### Scenario: New run accepted
- **WHEN** an authenticated client posts `{"application_id": "<id>"}` to `POST /resume` and no resume job for `<id>` is running
- **THEN** the system responds 202 with `ok` true, `application_id` `<id>`, `status` `running` and `started_at`, and no other keys

### Requirement: One running job per application and kind
The system SHALL run at most one job per application and kind, where kind is `resume` or `cover_letter`. A POST for an application and kind that already has a running job SHALL start no run and SHALL respond 202 with that job's `started_at`. Resume and cover letter jobs for one application SHALL be able to run at the same time.

#### Scenario: Retry while running
- **WHEN** a client posts `POST /resume` for `<id>` again while the first resume run for `<id>` is still running
- **THEN** the system responds 202 with the first job's `started_at`, and only one Claude run takes place

#### Scenario: Retry over both ports
- **WHEN** a resume job for `<id>` started from the public port is running and `POST /resume` for `<id>` arrives on the docs port
- **THEN** no second run starts

#### Scenario: Different kinds run together
- **WHEN** a resume job for `<id>` is running and a cover letter is requested for `<id>`
- **THEN** the cover letter job starts, and both run

#### Scenario: Rerun after finishing
- **WHEN** a resume job for `<id>` is `done` or `failed` and a resume is requested again
- **THEN** a new run starts and replaces the job record with a running one, whose `saved_path`, result, `error` and `finished_at` are null

### Requirement: Job records
The application store SHALL hold at most one job record per application and kind, in the same private SQLite file as the applications. A record SHALL hold `status` (`running`, `done` or `failed`), `started_at`, `finished_at`, `saved_path`, `error`, and the result: `match` for a resume, `text` for a cover letter. The table SHALL be created on startup without changing any application row.

#### Scenario: Existing store upgraded
- **WHEN** the service starts against a store created before job records existed
- **THEN** it starts normally, every application row and report is unchanged, and no application has a job record

#### Scenario: Successful run recorded
- **WHEN** a resume run for `<id>` finishes and its file is saved
- **THEN** the job record has `status` `done`, `finished_at`, the absolute `saved_path` and the `match` object `POST /resume` previously returned, and `error` null

#### Scenario: Cover letter result recorded
- **WHEN** a cover letter run for `<id>` finishes and its file is saved
- **THEN** the job record has `status` `done`, `finished_at`, the absolute `saved_path` and the letter's plain `text`

### Requirement: Failed runs recorded without details
When a run fails, the system SHALL mark the job `failed` with `finished_at` and a fixed generic `error`. For generation failures, the error SHALL be "Resume generation failed" or "Cover letter generation failed". For file write failures, it SHALL be "Storage service unavailable". It SHALL NOT hold exception text, Claude or TeX output, posting or letter text, paths, or secrets. The details SHALL be logged server-side with the `application_id`.

#### Scenario: Tailoring fails
- **WHEN** the final gate rejects a tailored resume for `<id>`
- **THEN** the resume job is `failed` with `error` "Resume generation failed", `saved_path` and `match` null, and the previously saved resume is unchanged

#### Scenario: Output directory unwritable
- **WHEN** writing a cover letter file for `<id>` fails
- **THEN** the cover letter job is `failed` with `error` "Storage service unavailable", and the error contains no path

### Requirement: Job records removed with their application
Deleting an application SHALL delete its job records in the same transaction. A run still in progress for a deleted application SHALL NOT recreate a record when it finishes. Its saved file, if any, is kept like other generated files.

#### Scenario: Deleted while idle
- **WHEN** an application with `done` resume and cover letter jobs is deleted
- **THEN** the store holds no job record for its ID

#### Scenario: Deleted while running
- **WHEN** an application is deleted while its resume job is running and the run then finishes
- **THEN** the store still holds no job record for its ID, and the status endpoint answers 404

### Requirement: Interrupted jobs failed on startup
On startup, before serving requests, the system SHALL mark every job still `running` as `failed`, with `finished_at` set to the startup time and `error` "Interrupted by a service restart". Jobs that are `done` or `failed` SHALL be left unchanged.

#### Scenario: Restart during a run
- **WHEN** the service restarts while a resume job for `<id>` is running
- **THEN** after the restart, `GET /resume/<id>/status` reports `failed` with `error` "Interrupted by a service restart"
- **AND** a new `POST /resume` for `<id>` starts a new run

### Requirement: Resume status endpoint
`GET /resume/{application_id}/status` SHALL respond 200 with exactly `{"ok": true, "application_id", "status", "started_at", "finished_at", "saved_path", "match", "error"}`. `finished_at`, `saved_path`, `match` and `error` SHALL be null when they do not apply. `saved_path` and `match` SHALL be set only when `status` is `done`, and `error` only when it is `failed`. `saved_path` SHALL be the saved PDF's file name only, never a directory or an absolute path.

#### Scenario: Running
- **WHEN** an authenticated client reads the status while the resume job for `<id>` is running
- **THEN** it gets 200 with `status` `running`, `started_at` set, and `finished_at`, `saved_path`, `match` and `error` null

#### Scenario: Done
- **WHEN** the resume job for `<id>` finished and saved the base resume unscored
- **THEN** it gets 200 with `status` `done`, `saved_path` `SUNIL BELDE.pdf`, and `match` `{"status": "no_job_description", "threshold": 70, "base_score": null, "tailored_score": null, "added_terms": []}`

#### Scenario: Failed
- **WHEN** the resume job for `<id>` failed
- **THEN** it gets 200 with `status` `failed`, `error` set, and `saved_path` and `match` null

### Requirement: Cover letter status endpoint
`GET /cover-letter/{application_id}/status` SHALL respond 200 with exactly `{"ok": true, "application_id", "status", "started_at", "finished_at", "saved_path", "text", "error"}`, with the same null rules as the resume status endpoint, where `text` takes the place of `match`. `saved_path` SHALL be the saved PDF's file name only, never a directory or an absolute path.

#### Scenario: Running
- **WHEN** an authenticated client reads the status while the cover letter job for `<id>` is running
- **THEN** it gets 200 with `status` `running`, and `finished_at`, `saved_path`, `text` and `error` null

#### Scenario: Done
- **WHEN** the cover letter job for `<id>` has finished
- **THEN** the status endpoint gives 200 with `status` `done`, `saved_path` `SUNIL BELDE - Cover Letter.pdf` and the letter's `text`

#### Scenario: Failed
- **WHEN** the cover letter job for `<id>` failed
- **THEN** the status endpoint gives 200 with `status` `failed`, `error` "Cover letter generation failed", and `saved_path` and `text` null

### Requirement: Status endpoints on the public port
Both status endpoints SHALL be served on the public port and on the docs port. They SHALL return only the fields listed above: no posting text, application fields other than the ID, scores breakdown, added-term evidence or full report. The viewer reads SHALL stay docs-port only.

#### Scenario: Public listener
- **WHEN** an authenticated client calls `GET /resume/<id>/status` on the public port
- **THEN** it gets the job status, while `GET /application/<id>` on the same port still answers 404

### Requirement: Status endpoint authentication and lookup
Both status endpoints SHALL check `X-API-Key` first and respond 401 `{"ok": false, "message"}` when it is missing or wrong, before reading the store. With a valid key, an ID that is not a hyphenated UUID, names no application, or has no job of that kind SHALL get 404 "Application not found" or "No job for this application" respectively. A store failure SHALL get 503.

#### Scenario: Missing key on unknown ID
- **WHEN** a client without a valid key reads the status of an ID that names no application
- **THEN** it gets 401, not 404

#### Scenario: Never generated
- **WHEN** an authenticated client reads the cover letter status of an existing application that never had a cover letter requested
- **THEN** it gets 404 with `ok` false

#### Scenario: Not a UUID
- **WHEN** an authenticated client reads `GET /resume/42/status`
- **THEN** it gets 404 and the raw value is not logged

#### Scenario: Store unavailable
- **WHEN** the store cannot be read
- **THEN** it gets 503 with `ok` false and a generic message

### Requirement: Status reads change nothing
Reading a status SHALL NOT start, retry or change any job, application or file.

#### Scenario: Read a failed job
- **WHEN** a client reads the status of a failed job
- **THEN** the job stays `failed` and no run starts

### Requirement: Job outcome logging
Each finished run SHALL emit one structured log line with event `resume_job` or `cover_letter_job`, the `application_id`, the outcome (`done` or `failed`) and the duration. A resume job SHALL also log the match status and scores, and both kinds SHALL log the Claude runs' turns and cost when there were runs. The line SHALL NOT contain the API key, the saved path, the company, or posting, resume or letter text.

#### Scenario: Tailored resume log
- **WHEN** a resume job for `<id>` finishes with a tailored resume
- **THEN** one `resume_job` line records `application_id` `<id>`, outcome `done`, the duration, match status `tailored`, both scores, the turns, the cost and the judge's approved and rejected counts

#### Scenario: Failed letter log
- **WHEN** a cover letter job fails at the final gate
- **THEN** one `cover_letter_job` line records outcome `failed`, and a separate error line names the stage and failed checks without quoting text

### Requirement: Status request logging
Each status request SHALL emit one log line with event `resume_request` or `cover_letter_request`, as for the POST, with the method, HTTP status, duration and, when the ID is well formed, the `application_id`.

#### Scenario: Status read logged
- **WHEN** a client reads `GET /cover-letter/<id>/status`
- **THEN** one `cover_letter_request` line records method `GET`, status 200, the duration and `application_id` `<id>`

### Requirement: Job records keep the full saved path
The job record SHALL continue to store the absolute path of the saved PDF. Only the status responses SHALL reduce it to the file name. Reducing it SHALL NOT change the stored record.

#### Scenario: Stored path unchanged by a status read
- **WHEN** a resume job for `<id>` is `done` and a client reads `GET /resume/<id>/status`
- **THEN** the response's `saved_path` is `SUNIL BELDE.pdf`, and the stored job record still holds the absolute path `<OUTPUT_DIR>/<company folder>/<id>/SUNIL BELDE.pdf`
