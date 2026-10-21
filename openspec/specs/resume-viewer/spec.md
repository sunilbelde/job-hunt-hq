# resume-viewer Specification

## Purpose

A read-only page, served only on the owner's tailnet, for reviewing each application's generated resume against the base resume: the two PDFs side by side, the application details, the scores and what tailoring added or left as gaps.

## Requirements

### Requirement: Viewer page served where docs are enabled
When API docs are enabled, the system SHALL serve the viewer at `GET /viewer` as one HTML page, without requiring the API key to load it. When API docs are disabled, `/viewer` SHALL be handled as an unknown path.

#### Scenario: Page served
- **WHEN** API docs are enabled and a browser requests `GET /viewer` without `X-API-Key`
- **THEN** the system responds 200 with an HTML page that contains no application, posting or resume data

#### Scenario: Disabled
- **WHEN** API docs are disabled and a client requests `GET /viewer`
- **THEN** the system responds 404

### Requirement: Self-contained page
The viewer page SHALL load no script, stylesheet, font or image from any origin other than the service itself, and SHALL use no third-party UI library. Its response SHALL carry a Content-Security-Policy that forbids loading scripts, styles and frames from other origins.

#### Scenario: No external assets
- **WHEN** a browser loads `/viewer`
- **THEN** every request it makes goes to the service's own origin, apart from `blob:` URLs the page creates itself

#### Scenario: Policy header
- **WHEN** `/viewer` is fetched
- **THEN** the response has a `Content-Security-Policy` header whose `script-src`, `style-src` and `frame-src` allow no other origin

### Requirement: API key entered once and kept in memory
The viewer SHALL ask for the API key before showing any data, send it only in the `X-API-Key` header of its own requests, and keep it only in the open page's memory, never in browser storage, cookies or a URL. A 401 from any request SHALL discard the key and ask for it again.

#### Scenario: Reload forgets the key
- **WHEN** the owner enters the key, views an application and reloads the page
- **THEN** the page asks for the key again before showing any data

#### Scenario: Wrong key
- **WHEN** the owner enters a wrong key
- **THEN** the page shows that the key was rejected, shows no data and asks again

#### Scenario: Key never in a URL
- **WHEN** the page requests a list, an application or a PDF
- **THEN** the key is carried in the `X-API-Key` header and no request URL, including the PDF frames' URLs, contains it

### Requirement: Application list
`GET /applications` SHALL require the API key and return every stored application, most recently generated first and then most recently recorded, each with its ID, company, role, status, recorded time and, when it has a report, the generation time, match status, base score and generated score. It SHALL NOT include posting text.

#### Scenario: Listed with report summary
- **WHEN** the store holds an application with a stored report and one without
- **THEN** both are returned; the first carries its generation time, match status and scores, and the second carries `report` `null`

#### Scenario: Missing key
- **WHEN** `GET /applications` is sent without a valid `X-API-Key`
- **THEN** the response is 401 `{"ok": false, "message": "Invalid or missing API key"}`

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read
- **THEN** the response is 503 `{"ok": false, "message": "Application store unavailable"}`

### Requirement: Application detail
`GET /application/{application_id}` SHALL require the API key and return the stored application with all its fields, and its stored generation report or `null`. An unknown ID, or one that is not a UUID, SHALL get 404 `{"ok": false, "message": "Application not found"}`.

#### Scenario: With report
- **WHEN** the owner requests an application whose resume was tailored
- **THEN** the response holds the application's fields, including the posting text, and its report

#### Scenario: Unknown ID
- **WHEN** `GET /application/not-a-uuid` is sent with a valid key
- **THEN** the response is 404 `{"ok": false, "message": "Application not found"}`

### Requirement: Generated resume PDF
`GET /application/{application_id}/resume.pdf` SHALL require the API key and return the application's saved resume as `application/pdf`, read from the path stored in its report or, without a report, from its resume path for the current company. It SHALL answer 404 `{"ok": false, "message": "Resume not found"}` when no file exists there or the path is outside `OUTPUT_DIR`.

#### Scenario: Saved resume returned
- **WHEN** an application has a saved resume and the owner requests its PDF with a valid key
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
`GET /resume/base.pdf` SHALL require the API key and return the base resume as rendered from the bundled template, as `application/pdf` with `Cache-Control: no-store`. A render failure SHALL get 500 `{"ok": false, "message": "Resume generation failed"}`.

#### Scenario: Base returned
- **WHEN** the owner requests `GET /resume/base.pdf` with a valid key
- **THEN** the response is 200 `application/pdf` with the same PDF `POST /resume` saves when it keeps the base resume

#### Scenario: Template changed
- **WHEN** the bundled template files change while the service runs
- **THEN** the next request returns a PDF rendered from the changed files

### Requirement: Side-by-side resume view
For a selected application, the viewer SHALL show the base resume PDF and the generated resume PDF next to each other, each rendered inline by the browser's own PDF viewer, labelled "Base" and "Generated", without the owner downloading a file or opening another application. On a screen too narrow for two columns it SHALL stack them, base first.

#### Scenario: Tailored application
- **WHEN** the owner selects an application whose resume was tailored
- **THEN** the base PDF and the tailored PDF are shown side by side in the page

#### Scenario: Base kept
- **WHEN** the selected application's match status is `base_meets_threshold` or `no_job_description`
- **THEN** both panes are shown and the page states that the generated resume is the base resume unchanged

#### Scenario: Nothing generated
- **WHEN** the selected application has no saved resume
- **THEN** the base PDF is shown and the generated pane says no resume has been generated

#### Scenario: Narrow screen
- **WHEN** the page is narrower than two readable PDF columns
- **THEN** the base PDF is shown above the generated PDF

### Requirement: Application details shown
For the selected application, the viewer SHALL show its company, role, status, location, work type, salary, posting date, sponsorship, why it fits, the job link and careers URL as links, when it was recorded and last updated, and the posting text, which SHALL be collapsed until the owner expands it. Empty fields SHALL be omitted.

#### Scenario: Details present
- **WHEN** the owner selects an application with a location, salary and posting text
- **THEN** the page shows them, with the posting text collapsed

#### Scenario: Posting text shown as text
- **WHEN** the stored posting text contains HTML markup or script
- **THEN** the page shows it as literal text and runs nothing from it

### Requirement: Scores shown against the threshold
For an application with a scored report, the viewer SHALL show the threshold and, for the base and the generated resume, the match score with its keyword coverage and requirement coverage as percentages. For `no_job_description` it SHALL state that the posting could not be scored.

#### Scenario: Tailored scores
- **WHEN** the report has base score 58 and tailored score 81 with threshold 70
- **THEN** the page shows 58 for the base and 81 for the generated resume, each with its coverage, and marks which one is at or above 70

#### Scenario: Base kept
- **WHEN** the report's status is `base_meets_threshold` with base score 76
- **THEN** the page shows 76 for both base and generated

#### Scenario: Unscored
- **WHEN** the report's status is `no_job_description`
- **THEN** the page shows no score and says the posting text was missing or too short to score

### Requirement: Additions shown
For a tailored application, the viewer SHALL list what the generated resume added over the base: the keywords it added, and each posting requirement whose assessment improved from the base to the generated resume, with both statuses.

#### Scenario: Added keywords and improved requirements
- **WHEN** the report lists added keywords `Kubernetes` and `Airflow`, and requirement R3 went from `missing` to `met`
- **THEN** the page lists both keywords under what was added, and R3's text with `missing` → `met`

#### Scenario: Nothing added
- **WHEN** the generated resume is the base resume
- **THEN** the page says nothing was added

### Requirement: Gaps shown
For a scored application, the viewer SHALL list the gaps the generated resume still has: the posting keywords it does not cover with their importance, the requirements it assesses as `partial` or `missing` with their importance, and the keywords the judge rejected with the reason.

#### Scenario: Remaining gaps
- **WHEN** the generated resume lacks the required keyword `Go`, assesses R2 as `partial`, and the judge rejected `Rust` for lack of evidence
- **THEN** the page lists `Go` (required), R2's text as partial, and `Rust` with its rejection reason

#### Scenario: Requirement evidence
- **WHEN** the owner opens a requirement in the comparison
- **THEN** the page shows its base and generated statuses and the quoted evidence for each

### Requirement: Legacy applications without a report
An application whose resume was generated before reports were stored SHALL be listed and viewable. The viewer SHALL show its details and its saved PDF beside the base, and SHALL state that no scoring report exists and that generating the resume again creates one.

#### Scenario: Old resume
- **WHEN** an application has a saved resume but no report
- **THEN** the page shows its details, the base and saved PDFs side by side, and a note that no report exists

### Requirement: Viewer reads never change data
The viewer page and its read endpoints SHALL NOT create, change or delete any application, report or file, and SHALL NOT start resume generation.

#### Scenario: Browsing
- **WHEN** the owner loads the viewer and opens every application
- **THEN** the store and the output folder are unchanged afterwards

### Requirement: Viewer requests logged without content
Each request to `GET /applications`, `GET /application/{application_id}` and `GET /application/{application_id}/resume.pdf` SHALL emit one `application_request` log line with the method, status, duration and, when known, the application ID, and `GET /resume/base.pdf` one `resume_request` line. No log line SHALL contain the API key, posting text, keywords, requirement text or resume content. Loading `/viewer` itself SHALL emit no structured request line.

#### Scenario: Detail request logged
- **WHEN** the owner opens an application in the viewer
- **THEN** one `application_request` line with method `GET` and its application ID is logged, without any of its fields' values

#### Scenario: Page load
- **WHEN** a browser loads `/viewer`
- **THEN** no `application_request` or `resume_request` line is emitted for it
