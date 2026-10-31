# Spec Delta

## MODIFIED Requirements

### Requirement: Application detail
`GET /application/{application_id}` SHALL return the stored application with all its fields, and its stored generation report or `null`, without requiring the API key. The report's `saved_path` SHALL be the saved resume's file name only, never a directory or an absolute path. An unknown ID, or one that is not a UUID, SHALL get 404 `{"ok": false, "message": "Application not found"}`.

#### Scenario: With report
- **WHEN** the owner requests an application whose resume was tailored
- **THEN** the response holds the application's fields, including the posting text, and its report
- **AND** the report's `saved_path` is `SUNIL BELDE.pdf`

#### Scenario: Report saved under a since-renamed company
- **WHEN** the application's resume was generated while its company was "Acme", and the company was then renamed to "Acme Corp"
- **THEN** the report's `saved_path` is still `SUNIL BELDE.pdf`, and `GET /application/{id}/resume.pdf` still returns the resume saved under the "Acme" folder

#### Scenario: No key needed
- **WHEN** `GET /application/{id}` is sent for a stored application without `X-API-Key`, or with a wrong one
- **THEN** the response is 200 with the application

#### Scenario: Unknown ID
- **WHEN** `GET /application/not-a-uuid` is sent
- **THEN** the response is 404 `{"ok": false, "message": "Application not found"}`
