# Spec Delta

## MODIFIED Requirements

### Requirement: Cover letter response
When a cover letter request passes its checks, `POST /cover-letter` SHALL start a background job and respond 202 with exactly `{"ok": true, "application_id", "status": "running", "started_at"}`, as defined in `generation-jobs`. Once the job is `done`, `GET /cover-letter/{application_id}/status` SHALL return the PDF's file name (no folder) as `saved_path`, and `text`: the greeting, paragraphs and sign-off as plain text, paragraphs separated by a blank line, without TeX markup.

#### Scenario: Successful request
- **WHEN** an authenticated client requests a cover letter for application `<id>` with company "Acme Corp" and usable posting text
- **THEN** the system responds 202 with `ok` true, `application_id` `<id>`, `status` `running` and `started_at`, and no other keys
- **AND** once the job is `done`, its `saved_path` is `SUNIL BELDE - Cover Letter.pdf`, and the file at `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf` is a one-page PDF of the same letter as its `text`

#### Scenario: Repeated requests
- **WHEN** a cover letter is requested twice for the same application, the second after the first job is `done`
- **THEN** both jobs report the same `saved_path`, and the file holds the second letter
