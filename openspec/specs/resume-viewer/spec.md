# resume-viewer Specification

## Purpose

A page, served only on the owner's tailnet, for reviewing each application's generated resume against the base resume (the two PDFs side by side, the application details, the scores and what tailoring added or left as gaps) and its generated cover letter against the base cover letter, and for changing an application's status or deleting it.

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
The viewer page and its read endpoints, the cover letter reads included, SHALL NOT create, change or delete any application, report or file, and SHALL NOT start resume or cover letter generation. Only the viewer write endpoints, sent when the owner changes a status or confirms a delete, SHALL change stored data, and they SHALL NOT create or remove any file or start generation.

#### Scenario: Browsing
- **WHEN** the owner loads the viewer and opens every application without changing a status or deleting
- **THEN** the store and the output folder are unchanged afterwards

#### Scenario: Browsing cover letters
- **WHEN** the owner opens the cover letter view of every application
- **THEN** the store, the output folder and `data/COVER_LETTER.pdf` are unchanged, and no Claude run starts

#### Scenario: Writes touch only the store
- **WHEN** the owner changes a status and deletes an application from the viewer
- **THEN** the output folder is unchanged, and no Claude run starts

### Requirement: Viewer requests logged without content
Each request to `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `PATCH /viewer/application/{application_id}` and `DELETE /viewer/application/{application_id}` SHALL emit one `application_request` log line with the method, status, duration and, when known, the application ID. `GET /resume/base.pdf` SHALL emit one `resume_request` line and `GET /cover-letter/base.pdf` one `cover_letter_request` line. No log line SHALL contain the API key, posting text, keywords, requirement text, resume content, letter content or the status sent in a write. Loading `/viewer` itself SHALL emit no structured request line.

#### Scenario: Detail request logged
- **WHEN** the owner opens an application in the viewer
- **THEN** one `application_request` line with method `GET` and its application ID is logged, without any of its fields' values

#### Scenario: Cover letter reads logged
- **WHEN** the owner switches to the cover letter view for the first time since loading the page
- **THEN** one `application_request` line with method `GET` and the application ID and one `cover_letter_request` line for the base letter are logged, with no path, company or letter text

#### Scenario: Status write logged
- **WHEN** the owner changes an application's status to `applied` from the viewer
- **THEN** one `application_request` line with method `PATCH`, status 200 and the application ID is logged, and it does not contain `applied`

#### Scenario: Delete logged
- **WHEN** the owner deletes an application from the viewer
- **THEN** one `application_request` line with method `DELETE`, status 200 and the application ID is logged

#### Scenario: Refused write logged
- **WHEN** a viewer write is refused as cross-site, or sent for a path ID that is not a UUID
- **THEN** one `application_request` line with its method and status is logged, without the path ID

#### Scenario: Page load
- **WHEN** a browser loads `/viewer`
- **THEN** no `application_request`, `resume_request` or `cover_letter_request` line is emitted for it

### Requirement: Generated cover letter PDF
`GET /application/{application_id}/cover-letter.pdf` SHALL return the application's saved cover letter as `application/pdf` with `Cache-Control: no-store`, without requiring the API key. It SHALL look first at the cover letter path for the current company and then beside the resume path stored in its report. It SHALL answer 404 `{"ok": false, "message": "Cover letter not found"}` when no file exists at either or the path is outside `OUTPUT_DIR`.

#### Scenario: Saved letter returned
- **WHEN** an application has a saved cover letter and the owner requests its PDF without a key
- **THEN** the response is 200 `application/pdf` with exactly the saved file's bytes and `Cache-Control: no-store`

#### Scenario: Company renamed after the resume and letter were generated
- **WHEN** the application's company was changed after its resume and cover letter were generated
- **THEN** the PDF returned is the letter saved beside the resume its report points to

#### Scenario: No letter generated
- **WHEN** the application exists but no cover letter was ever saved for it
- **THEN** the response is 404 `{"ok": false, "message": "Cover letter not found"}`

#### Scenario: Unknown application
- **WHEN** `GET /application/not-a-uuid/cover-letter.pdf` is sent
- **THEN** the response is 404 `{"ok": false, "message": "Application not found"}`

#### Scenario: Path outside the output folder
- **WHEN** the report's saved path, or a link at the letter's path, resolves outside `OUTPUT_DIR`
- **THEN** no file outside `OUTPUT_DIR` is returned, and the response is 404 `Cover letter not found` unless the other location holds the letter

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read
- **THEN** the response is 503 `{"ok": false, "message": "Application store unavailable"}`

### Requirement: Base cover letter PDF
`GET /cover-letter/base.pdf` SHALL return the committed base cover letter `data/COVER_LETTER.pdf` byte for byte as `application/pdf` with `Cache-Control: no-store`, without requiring the API key, reading the file again on each request. When the file is missing or cannot be read it SHALL answer 404 `{"ok": false, "message": "Base cover letter not found"}`.

#### Scenario: Base letter returned
- **WHEN** the owner requests `GET /cover-letter/base.pdf` without a key
- **THEN** the response is 200 `application/pdf` with exactly the bytes of `data/COVER_LETTER.pdf`

#### Scenario: Owner re-renders the base letter
- **WHEN** the owner edits `data/COVER_LETTER.md` and re-renders `data/COVER_LETTER.pdf` while the service runs
- **THEN** the next request returns the re-rendered PDF

#### Scenario: Base letter missing
- **WHEN** `data/COVER_LETTER.pdf` does not exist
- **THEN** the response is 404 `{"ok": false, "message": "Base cover letter not found"}`

#### Scenario: Not served without docs
- **WHEN** API docs are disabled and a client requests `GET /cover-letter/base.pdf` or `GET /application/{id}/cover-letter.pdf`
- **THEN** the system responds 404

### Requirement: Resume and cover letter switch
For a selected application, the viewer SHALL offer a switch between "Resume" and "Cover letter", showing the resume panes when an application is first selected. The switch SHALL change only the document panes; the details, scores, additions and gaps SHALL stay as they are.

#### Scenario: Default view
- **WHEN** the owner selects an application
- **THEN** the resume panes are shown and the switch shows "Resume" as selected

#### Scenario: Switching to the letter
- **WHEN** the owner chooses "Cover letter"
- **THEN** the panes show the cover letters, and the details and score cards are unchanged

#### Scenario: Selecting another application
- **WHEN** the owner, viewing cover letters, selects another application
- **THEN** that application's resume panes are shown

### Requirement: Side-by-side cover letter view
In the cover letter view, the viewer SHALL show the base cover letter and the application's saved cover letter next to each other, rendered inline by the browser's own PDF viewer and labelled "Base" and "Generated". On a screen too narrow for two columns it SHALL stack them, base first. It SHALL fetch the letters only when the owner first switches to the cover letter view for that application.

#### Scenario: Letter generated
- **WHEN** the owner switches to the cover letter view for an application with a saved letter
- **THEN** the base letter and the generated letter are shown side by side in the page

#### Scenario: No letter generated
- **WHEN** the owner switches to the cover letter view for an application without a saved letter
- **THEN** the base letter is shown and the generated pane says no cover letter has been generated for this application

#### Scenario: Base letter missing
- **WHEN** the base letter is not available
- **THEN** the base pane says the base cover letter is unavailable, and the generated letter is still shown

#### Scenario: Resume view only
- **WHEN** the owner selects an application and never switches to the cover letter view
- **THEN** the page requests neither cover letter PDF

#### Scenario: Narrow screen
- **WHEN** the page is narrower than two readable PDF columns
- **THEN** the base letter is shown above the generated letter

### Requirement: Viewer status update endpoint
Where the viewer is served, `PATCH /viewer/application/{application_id}` SHALL set the application's status from a JSON object body `{"status": "<status>"}`, without requiring the API key, and change no other field. It SHALL respond 200 with exactly `{"ok": true, "application_id": "<uuid>", "status": "<status>"}`, the ID in lowercase. Other body fields SHALL be ignored.

#### Scenario: Status changed
- **WHEN** the viewer sends `{"status": "applied"}` without `X-API-Key` for an application whose status is `verified`
- **THEN** the response is 200 `{"ok": true, "application_id": "<id>", "status": "applied"}` and every other stored field, and the report, is unchanged

#### Scenario: Other fields ignored
- **WHEN** the body is `{"status": "offer", "company": "Other"}`
- **THEN** the status becomes `offer` and the company is unchanged

#### Scenario: Same status again
- **WHEN** the body sets the application's current status
- **THEN** the response is 200

#### Scenario: Shown by later reads
- **WHEN** the status was changed to `interviewing`
- **THEN** `GET /applications` and `GET /application/{id}` return status `interviewing`

### Requirement: Viewer status update validation
The viewer status update SHALL reject with 422 `{"ok": false, "message": ...}`, changing nothing, a body that is not JSON, not a JSON object, has no `status`, or has a `status` that is not one of the application status values. The message SHALL name `status` when the value is wrong and SHALL NOT echo the value sent.

#### Scenario: Unknown status
- **WHEN** the body is `{"status": "ghosted"}`
- **THEN** the response is 422 naming `status`, does not contain `ghosted`, and the row is unchanged

#### Scenario: Missing status
- **WHEN** the body is `{}` or `{"company": "Acme"}`
- **THEN** the response is 422 and the row is unchanged

#### Scenario: Not a JSON object
- **WHEN** the body is not valid JSON, or is a JSON array, string, number or null
- **THEN** the response is 422 and the row is unchanged

#### Scenario: Not sent as JSON
- **WHEN** the request's `Content-Type` is not `application/json`
- **THEN** the response is 422 and the row is unchanged

### Requirement: Viewer delete endpoint
Where the viewer is served, `DELETE /viewer/application/{application_id}` SHALL permanently remove the application with its report and generation job state, without requiring the API key, and respond 200 with exactly `{"ok": true, "application_id": "<uuid>"}`. It SHALL NOT delete any generated resume or cover letter file. Any request body SHALL be ignored.

#### Scenario: Deleted
- **WHEN** the viewer deletes application `<id>` without `X-API-Key`
- **THEN** the response is 200 `{"ok": true, "application_id": "<id>"}`, and `GET /application/<id>` then responds 404

#### Scenario: Files kept
- **WHEN** an application with a saved resume and cover letter is deleted from the viewer
- **THEN** both PDFs are still in the output folder

#### Scenario: Re-record after delete
- **WHEN** an application deleted from the viewer is posted again with the same `job_link`
- **THEN** the response is 201 with a new `application_id`

### Requirement: Viewer writes for unknown applications
For both viewer write endpoints, an `application_id` that is not a UUID or does not identify a stored row SHALL get 404 `{"ok": false, "message": "Application not found"}` and change nothing, even when the body is also invalid. A UUID SHALL be accepted in any letter case.

#### Scenario: Delete twice
- **WHEN** the viewer deletes the same application twice
- **THEN** the first response is 200 and the second is 404

#### Scenario: Not a UUID
- **WHEN** the viewer sends `PATCH /viewer/application/abc` or `DELETE /viewer/application/1`
- **THEN** the response is 404 `Application not found`, not a framework validation error

#### Scenario: Unknown ID with a bad body
- **WHEN** `PATCH` is sent for a random UUID with body `{"status": "ghosted"}`
- **THEN** the response is 404

#### Scenario: Store unavailable
- **WHEN** the application store cannot be read or written
- **THEN** the response is 503 `{"ok": false, "message": "Application store unavailable"}`

### Requirement: Viewer writes refuse cross-site requests
The viewer write endpoints SHALL respond 403 `{"ok": false, "message": "Cross-site request refused"}`, before reading the body or touching the store, when the request carries a `Sec-Fetch-Site` header other than `same-origin`, or carries no `Sec-Fetch-Site` but an `Origin` whose host does not match the request's `Host`. The service SHALL send no CORS headers that would allow another origin to call them.

#### Scenario: Request from another site
- **WHEN** a request to either write endpoint carries `Sec-Fetch-Site: cross-site` or `same-site`
- **THEN** the response is 403 and the row is unchanged

#### Scenario: Foreign origin
- **WHEN** a request carries no `Sec-Fetch-Site` and `Origin: https://evil.example`
- **THEN** the response is 403 and the row is unchanged

#### Scenario: From the viewer page
- **WHEN** the viewer page sends a write, with `Sec-Fetch-Site: same-origin`
- **THEN** the write is processed

#### Scenario: Client without browser headers
- **WHEN** a client on the tailnet sends a write with neither `Sec-Fetch-Site` nor `Origin`
- **THEN** the write is processed

#### Scenario: Preflight not granted
- **WHEN** a browser sends an `OPTIONS` preflight for either write endpoint from another origin
- **THEN** the response carries no `Access-Control-Allow-Origin` header

### Requirement: Viewer write endpoints only where the viewer is
The viewer write endpoints SHALL exist only when API docs are enabled. When docs are disabled, a request to either SHALL be handled as an unknown path, whatever `X-API-Key` it carries. The keyed `PATCH` and `DELETE /application/{application_id}` SHALL behave as before on every listener.

#### Scenario: Docs disabled
- **WHEN** API docs are disabled and a client sends `PATCH` or `DELETE /viewer/application/<id>` for an existing row, with or without a valid key
- **THEN** the response is 404 and the row is unchanged

#### Scenario: Keyed endpoints still need the key
- **WHEN** API docs are enabled and a client sends `DELETE /application/<id>` without `X-API-Key`
- **THEN** the response is 401 and the row still exists

### Requirement: Status changed from the viewer
For the selected application, the viewer SHALL show its status as a control listing the six application statuses, with the current one selected. Choosing a different status SHALL save it at once, update the status in the details and the list without reloading the page, and show that it was saved. If the save fails, the viewer SHALL show the error message and put the control back to the stored status.

#### Scenario: Changing status
- **WHEN** the owner selects `applied` for an application whose status is `verified`
- **THEN** one `PATCH /viewer/application/<id>` is sent, and the details and the list entry both show `applied`

#### Scenario: Save fails
- **WHEN** the save responds with an error
- **THEN** the page shows the error message and the control shows the previous status

#### Scenario: No write on selection
- **WHEN** the owner selects an application and does not change its status
- **THEN** no write request is sent

### Requirement: Application deleted from the viewer
For the selected application, the viewer SHALL offer a Delete action that first asks for confirmation naming the company and role and saying it cannot be undone. Only after the owner confirms SHALL it send the delete. On success it SHALL remove the application from the list, update the count and clear the detail pane. On failure it SHALL show the error and leave the application listed.

#### Scenario: Confirmed
- **WHEN** the owner chooses Delete on "Acme – Data Engineer" and confirms
- **THEN** one `DELETE /viewer/application/<id>` is sent, the entry leaves the list, the count drops by one and the detail pane says to select an application

#### Scenario: Cancelled
- **WHEN** the owner chooses Delete and then cancels
- **THEN** no request is sent and the application stays selected

#### Scenario: Delete fails
- **WHEN** the delete responds with an error
- **THEN** the page shows the error message and the application is still listed

#### Scenario: Deleted application in the URL
- **WHEN** the deleted application's ID is still in the page's URL fragment
- **THEN** the fragment is cleared, and a reload shows the list with nothing selected
