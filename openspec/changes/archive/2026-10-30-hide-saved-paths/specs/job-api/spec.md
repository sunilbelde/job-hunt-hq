# Spec Delta

## MODIFIED Requirements

### Requirement: Job creation response
When a resume request passes its checks, `POST /resume` SHALL start a background resume job and respond 202 with exactly `{"ok": true, "application_id": "<uuid>", "status": "running", "started_at": "<timestamp>"}`, as defined in `generation-jobs`. The saved file name and match SHALL be read from `GET /resume/{application_id}/status`. Generation SHALL NOT write a cover letter; cover letters come only from `POST /cover-letter`.

#### Scenario: Successful job
- **WHEN** an authenticated client posts `{"application_id": "<id>"}` and application `<id>` exists with company "Acme Corp"
- **THEN** the system responds 202 with `ok` true, `application_id` `<id>`, `status` `running` and `started_at`, and no other keys
- **AND** once the job is `done`, its `saved_path` is `SUNIL BELDE.pdf` and the file at `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` is the generated PDF

#### Scenario: Cover letter beside the resume
- **WHEN** a resume is generated for any application
- **THEN** no cover letter file beside the resume is created, replaced or deleted, and the resume job record has no `text`

#### Scenario: Repeated requests for one application
- **WHEN** an authenticated client requests a resume for the same application twice, the second after the first job is `done`
- **THEN** both jobs report the same `saved_path`
- **AND** the file at `<OUTPUT_DIR>/<company folder>/<id>/SUNIL BELDE.pdf` holds the second render

#### Scenario: Existing clients unaffected
- **WHEN** a client that reads `application_id`, `saved_path` and `match` requests a resume and its job finishes
- **THEN** `GET /resume/{application_id}/status` returns those fields with the same names and types, with `saved_path` a string holding the file name
- **AND** the POST response itself is never 201 and never holds `saved_path` or `match`
