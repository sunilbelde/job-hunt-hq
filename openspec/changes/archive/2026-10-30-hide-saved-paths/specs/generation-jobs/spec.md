# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Job records keep the full saved path
The job record SHALL continue to store the absolute path of the saved PDF. Only the status responses SHALL reduce it to the file name. Reducing it SHALL NOT change the stored record.

#### Scenario: Stored path unchanged by a status read
- **WHEN** a resume job for `<id>` is `done` and a client reads `GET /resume/<id>/status`
- **THEN** the response's `saved_path` is `SUNIL BELDE.pdf`, and the stored job record still holds the absolute path `<OUTPUT_DIR>/<company folder>/<id>/SUNIL BELDE.pdf`
