## ADDED Requirements

### Requirement: Viewer opens without an API key
The viewer SHALL load and show the application list as soon as the page opens, without asking for an API key, and SHALL send no `X-API-Key` header and no key in any URL, cookie or browser storage. Reloading the page SHALL show the data again without any prompt.

#### Scenario: Opens straight to the list
- **WHEN** the owner opens `/viewer` on a listener with API docs enabled
- **THEN** the page lists the applications without showing a key prompt

#### Scenario: Reload
- **WHEN** the owner views an application and reloads the page
- **THEN** the page lists the applications again without asking for anything

#### Scenario: No key sent
- **WHEN** the page requests a list, an application or a PDF
- **THEN** the request carries no `X-API-Key` header and its URL contains no key

## MODIFIED Requirements

### Requirement: Application list
`GET /applications` SHALL return every stored application, most recently generated first and then most recently recorded, each with its ID, company, role, status, recorded time and, when it has a report, the generation time, match status, base score and generated score. It SHALL NOT include posting text. It SHALL NOT require the API key, and SHALL ignore an `X-API-Key` header if one is sent.

#### Scenario: Listed with report summary
- **WHEN** the store holds an application with a stored report and one without
- **THEN** both are returned; the first carries its generation time, match status and scores, and the second carries `report` `null`

#### Scenario: Missing key
- **WHEN** `GET /applications` is sent without `X-API-Key`, or with a wrong one
- **THEN** the response is 200 with the applications

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read
- **THEN** the response is 503 `{"ok": false, "message": "Application store unavailable"}`

### Requirement: Application detail
`GET /application/{application_id}` SHALL return the stored application with all its fields, and its stored generation report or `null`, without requiring the API key. An unknown ID, or one that is not a UUID, SHALL get 404 `{"ok": false, "message": "Application not found"}`.

#### Scenario: With report
- **WHEN** the owner requests an application whose resume was tailored
- **THEN** the response holds the application's fields, including the posting text, and its report

#### Scenario: No key needed
- **WHEN** `GET /application/{id}` is sent for a stored application without `X-API-Key`, or with a wrong one
- **THEN** the response is 200 with the application

#### Scenario: Unknown ID
- **WHEN** `GET /application/not-a-uuid` is sent
- **THEN** the response is 404 `{"ok": false, "message": "Application not found"}`

### Requirement: Generated resume PDF
`GET /application/{application_id}/resume.pdf` SHALL return the application's saved resume as `application/pdf`, without requiring the API key, read from the path stored in its report or, without a report, from its resume path for the current company. It SHALL answer 404 `{"ok": false, "message": "Resume not found"}` when no file exists there or the path is outside `OUTPUT_DIR`.

#### Scenario: Saved resume returned
- **WHEN** an application has a saved resume and the owner requests its PDF without a key
- **THEN** the response is 200 `application/pdf` with exactly the saved file's bytes

#### Scenario: Company renamed after generation
- **WHEN** the application's company was changed after its resume was generated
- **THEN** the PDF returned is the one saved at generation time

#### Scenario: Never generated
- **WHEN** the application exists but no resume was ever saved for it
- **THEN** the response is 404 `{"ok": false, "message": "Resume not found"}`

#### Scenario: Not cached by the browser
- **WHEN** a PDF response is sent
- **THEN** it carries `Cache-Control: no-store`

### Requirement: Base resume PDF
`GET /resume/base.pdf` SHALL return the base resume as rendered from the bundled template, as `application/pdf` with `Cache-Control: no-store`, without requiring the API key. A render failure SHALL get 500 `{"ok": false, "message": "Resume generation failed"}`.

#### Scenario: Base returned
- **WHEN** the owner requests `GET /resume/base.pdf` without a key
- **THEN** the response is 200 `application/pdf` with the same PDF `POST /resume` saves when it keeps the base resume

#### Scenario: Template changed
- **WHEN** the bundled template files change while the service runs
- **THEN** the next request returns a PDF rendered from the changed files

## REMOVED Requirements

### Requirement: API key entered once and kept in memory
**Reason**: The viewer and its reads are served only on the tailnet-only docs listener, so the key prompt on every load added friction without meaningful protection.
**Migration**: None needed; open `/viewer` and it loads directly. Restrict `tcp:8444` in the tailnet policy file if others share the tailnet.
