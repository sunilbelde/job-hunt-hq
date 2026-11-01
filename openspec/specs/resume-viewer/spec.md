# resume-viewer Specification

## Purpose

A page, served only on the Mac mini itself (the loopback-only local listener), for reviewing each application's generated resume against the base resume (the two PDFs side by side, the application details, the scores and what tailoring added or left as gaps) and its generated cover letter against the base cover letter, and for changing an application's status or deleting it.

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
`GET /applications` SHALL return every stored application, most recently generated first and then most recently recorded, each with its ID, company, role, status, recorded time, `jobs` and, when it has a report, the generation time, match status, base score and generated score. `jobs` SHALL hold `resume` and `cover_letter`, each null when that kind has no job, else exactly `status`, `started_at`, `finished_at` and `error`. It SHALL NOT include posting text, nor any job's saved path, match or letter text. It SHALL NOT require the API key, and SHALL ignore an `X-API-Key` header if one is sent.

#### Scenario: Listed with report summary
- **WHEN** the store holds an application with a stored report and one without
- **THEN** both are returned; the first carries its generation time, match status and scores, and the second carries `report` `null`

#### Scenario: Job summaries
- **WHEN** an application has a running resume job and a failed cover letter job, and another has no jobs
- **THEN** the first carries `jobs.resume` with `status` `running`, its `started_at` and null `finished_at` and `error`, and `jobs.cover_letter` with `status` `failed` and its fixed `error`; the second carries `{"resume": null, "cover_letter": null}`

#### Scenario: No job results in the list
- **WHEN** an application's resume and cover letter jobs are `done`
- **THEN** its list entry contains neither job's `saved_path`, `match` nor `text`

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
- **AND** the report's `saved_path` is `JANE DOE.pdf`

#### Scenario: Report saved under a since-renamed company
- **WHEN** the application's resume was generated while its company was "Acme", and the company was then renamed to "Acme Corp"
- **THEN** the report's `saved_path` is still `JANE DOE.pdf`, and `GET /application/{id}/resume.pdf` still returns the resume saved under the "Acme" folder

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
For the selected application, the viewer SHALL show its company, role, status, location, work type, salary, posting date, sponsorship, why it fits, the job link and careers URL as links, when it was recorded and last updated, and the posting text, which SHALL be collapsed until the owner expands it. Empty fields SHALL be omitted. The status SHALL be shown as text; the detail pane SHALL NOT offer a status control or a Delete action.

#### Scenario: Details present
- **WHEN** the owner selects an application with a location, salary and posting text
- **THEN** the page shows them, with the posting text collapsed

#### Scenario: Posting text shown as text
- **WHEN** the stored posting text contains HTML markup or script
- **THEN** the page shows it as literal text and runs nothing from it

#### Scenario: No write controls in the details
- **WHEN** the owner selects an application
- **THEN** the detail pane shows its status as text and has no status control and no Delete button

#### Scenario: Status text follows a change from the list
- **WHEN** the selected application's status is changed to `applied` from its list entry
- **THEN** the detail pane shows `applied` without reloading the application

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
The viewer page and its read endpoints, the cover letter reads included, SHALL NOT create, change or delete any application, report or file, and SHALL NOT start resume or cover letter generation. Only the viewer write endpoints SHALL change stored data or start work: a status change or a confirmed delete changes only the store, the fill endpoint only opens a Herdr tab, and only the two viewer generation endpoints start a generation run.

#### Scenario: Browsing
- **WHEN** the owner loads the viewer and opens every application without using any action
- **THEN** the store and the output folder are unchanged afterwards

#### Scenario: Browsing cover letters
- **WHEN** the owner opens the cover letter view of every application
- **THEN** the store, the output folder and `data/COVER_LETTER.pdf` are unchanged, and no Claude run starts

#### Scenario: Writes touch only the store
- **WHEN** the owner changes a status and deletes an application from the viewer
- **THEN** the output folder is unchanged, and no Claude run starts

#### Scenario: Polling changes nothing
- **WHEN** the page re-reads the list while a job runs
- **THEN** no job is started or changed by those reads

### Requirement: Viewer requests logged without content
Each request to `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `PATCH /viewer/application/{application_id}`, `DELETE /viewer/application/{application_id}`, `POST /viewer/application/{application_id}/resume` and `POST /viewer/application/{application_id}/cover-letter` SHALL emit one `application_request` log line with the method, status, duration and, when known, the application ID. `GET /resume/base.pdf` SHALL emit one `resume_request` line and `GET /cover-letter/base.pdf` one `cover_letter_request` line. No log line SHALL contain the API key, posting text, keywords, requirement text, resume content, letter content or the status sent in a write. Loading `/viewer` itself SHALL emit no structured request line.

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

#### Scenario: Generation request logged
- **WHEN** the owner starts a resume from the viewer
- **THEN** one `application_request` line with method `POST`, status 202 and the application ID is logged, and the run's own `resume_job` line follows when it finishes

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
The viewer write endpoints SHALL exist only when API docs are enabled. When docs are disabled, a request to either SHALL be handled as an unknown path, whatever `X-API-Key` it carries. The keyed `PATCH` and `DELETE /application/{application_id}` SHALL behave as before on the docs port and on a development server, and SHALL NOT be served on the installed service's public listener.

#### Scenario: Docs disabled
- **WHEN** API docs are disabled and a client sends `PATCH` or `DELETE /viewer/application/<id>` for an existing row, with or without a valid key
- **THEN** the response is 404 and the row is unchanged

#### Scenario: Keyed endpoints still need the key
- **WHEN** API docs are enabled and a client sends `DELETE /application/<id>` without `X-API-Key`
- **THEN** the response is 401 and the row still exists

#### Scenario: Keyed endpoints not public
- **WHEN** a client sends `PATCH` or `DELETE /application/<id>` with a valid key to the installed service's public listener
- **THEN** the response is 404 and the row is unchanged

### Requirement: Status changed from the viewer
The selected application's action bar SHALL show its status as a control listing the six application statuses, with the current one selected. Choosing a different status SHALL save it at once, update the action bar, the details and that application's list entry without reloading the page, and show that it was saved. If the save fails, the viewer SHALL show the error message in the action bar and put the control back to the stored status. List entries SHALL carry no status control.

#### Scenario: Changing status
- **WHEN** the owner selects `applied` in the action bar of an application whose status is `verified`
- **THEN** one `PATCH /viewer/application/<id>` is sent, and the action bar, the details and the list entry show `applied`

#### Scenario: Changing status of an unopened application
- **WHEN** application A is selected and the owner wants to change application B's status
- **THEN** B's list entry offers no control for it; selecting B shows B's action bar, and A's details are no longer shown

#### Scenario: Save fails
- **WHEN** the save responds with an error
- **THEN** the action bar shows the error message and its control shows the previous status

#### Scenario: No write on selection
- **WHEN** the owner selects an application and does not change its status
- **THEN** no write request is sent

#### Scenario: Status shown in the list
- **WHEN** the list is shown
- **THEN** each entry shows its status as text, not as a control

### Requirement: Application deleted from the viewer
The selected application's action bar SHALL offer a Delete action that first asks for confirmation naming the company and role and saying it cannot be undone. Only after the owner confirms SHALL it send the delete. On success it SHALL remove the entry from the list, update the count and clear the detail pane. On failure it SHALL show the error in the action bar and leave the application listed and selected. List entries SHALL carry no Delete action.

#### Scenario: Confirmed
- **WHEN** the owner selects "Acme – Data Engineer", chooses Delete and confirms
- **THEN** one `DELETE /viewer/application/<id>` is sent, the entry leaves the list and the count drops by one

#### Scenario: Selected application deleted
- **WHEN** the delete succeeds
- **THEN** the detail pane says to select an application

#### Scenario: Other application deleted
- **WHEN** application A is selected and the owner wants to delete application B
- **THEN** B's list entry offers no Delete action; B can be deleted only from its own action bar after selecting it, and A is unaffected until then

#### Scenario: Cancelled
- **WHEN** the owner chooses Delete and then cancels
- **THEN** no request is sent, the entry stays listed and the selection is unchanged

#### Scenario: Delete fails
- **WHEN** the delete responds with an error
- **THEN** the action bar shows the error message and the application is still listed and selected

#### Scenario: Deleted application in the URL
- **WHEN** the deleted application's ID is still in the page's URL fragment
- **THEN** the fragment is cleared, and a reload shows the list with nothing selected

### Requirement: List filtered by status
Above the application list, the viewer SHALL offer a status filter with "All statuses" (the default) and each of the six application statuses. Choosing a status SHALL show only applications with that status. Filtering SHALL happen in the page and SHALL NOT send a request.

#### Scenario: Filter by status
- **WHEN** the list holds 3 `applied` and 2 `verified` applications and the owner filters by `applied`
- **THEN** only the 3 `applied` entries are listed and no request is sent

#### Scenario: Back to all
- **WHEN** the owner chooses "All statuses" again
- **THEN** all 5 entries are listed

#### Scenario: Status changed out of the filter
- **WHEN** the list is filtered by `verified` and the owner changes an entry's status to `applied`
- **THEN** after the save succeeds the entry leaves the filtered list and the counts update

### Requirement: List filtered by recorded date
Above the application list, the viewer SHALL offer an optional "Recorded from" and "Recorded to" date. They SHALL filter on when the application was recorded in the store, not on the posting date, both ends inclusive, by calendar day in the browser's time zone. An empty end SHALL be unbounded. Both filters SHALL combine with the status filter.

#### Scenario: Date range
- **WHEN** applications were recorded on Oct 20, Oct 25 and Oct 30 and the owner sets from Oct 25 to Oct 30
- **THEN** the Oct 25 and Oct 30 applications are listed

#### Scenario: Posting date ignored
- **WHEN** an application was recorded on Oct 30 for a posting dated Sep 1 and the range is Oct 25 to Oct 30
- **THEN** it is listed

#### Scenario: Only a start date
- **WHEN** only "Recorded from" Oct 25 is set
- **THEN** every application recorded on or after Oct 25 is listed

#### Scenario: Combined with status
- **WHEN** the status filter is `applied` and the range is Oct 25 to Oct 30
- **THEN** only `applied` applications recorded in that range are listed

### Requirement: Filtered count and empty result
When any filter is set, the header count SHALL show how many applications match out of the total (for example "5 of 20 applications"); with no filter it SHALL show the total as before. When no application matches, the list SHALL say so and offer to clear the filters. The selected application's details SHALL stay shown when a filter hides its entry.

#### Scenario: Count while filtered
- **WHEN** 5 of 20 applications match the filters
- **THEN** the header shows "5 of 20 applications"

#### Scenario: Nothing matches
- **WHEN** no application matches
- **THEN** the list says no applications match and offers a control that clears every filter and lists all applications

#### Scenario: Selected application filtered out
- **WHEN** the selected application's entry is hidden by a filter
- **THEN** its details stay shown

### Requirement: Viewer fill endpoint
Where the viewer is served, `POST /viewer/application/{application_id}/fill` SHALL, without requiring the API key, open a tab in the Herdr workspace named by `FILL_WORKSPACE` (default `Claude-Jobs-Automation`), labelled `<company>-<role>-<application id>`, starting in the repository, that runs `claude --chrome "/job-application-form-filler <application id>"`. It SHALL change no stored data and ignore any request body.

#### Scenario: Tab opened
- **WHEN** the viewer posts to the fill endpoint for application `<id>` of "Rula – Staff Forward Deployed Engineer"
- **THEN** a tab labelled `Rula-Staff Forward Deployed Engineer-<id>` opens in `Claude-Jobs-Automation` running `claude --chrome "/job-application-form-filler <id>"`
- **AND** the response is 200 with exactly `{"ok": true, "application_id": "<id>", "tab_id": "<herdr tab id>", "tab_label": "Rula-Staff Forward Deployed Engineer-<id>", "already_open": false}`, the ID in lowercase

#### Scenario: Workspace missing
- **WHEN** no Herdr workspace is labelled `Claude-Jobs-Automation`
- **THEN** one is created with that label and its first tab is used, labelled as above

#### Scenario: Already open
- **WHEN** a tab whose label ends with the application's ID is open in the workspace
- **THEN** no tab is opened and nothing is run, and the response is 200 with that tab and `already_open` true

#### Scenario: Only the ID reaches the command
- **WHEN** the company or role contains shell syntax or control characters
- **THEN** the command run is still exactly the fixed command with the application ID, and the label has the control characters removed

#### Scenario: Herdr unavailable
- **WHEN** the Herdr CLI is missing, the Herdr server is not running, or Herdr returns an error or an unexpected reply
- **THEN** the response is 503 `{"ok": false, "message": "Herdr unavailable"}` and the log records a `herdr_error` without Herdr's output

#### Scenario: Unknown application
- **WHEN** the ID is not a UUID or not stored
- **THEN** the response is 404 `Application not found` and Herdr is not called

#### Scenario: Cross-site or docs off
- **WHEN** the request is cross-site under the rule for viewer writes, or API docs are disabled
- **THEN** the response is 403 `Cross-site request refused`, or 404 as for an unknown path, and Herdr is not called

### Requirement: Fill form from the viewer
The selected application's action bar SHALL offer a **Fill form** button that posts to the fill endpoint for that application. While the request is pending the button SHALL be disabled. On success the action bar SHALL show "Opened Herdr tab <label>", or "Already open in Herdr tab <label>"; on failure, "Not opened: <message>". List entries SHALL carry no Fill form button.

#### Scenario: Opened
- **WHEN** the owner clicks Fill form in the action bar
- **THEN** one `POST /viewer/application/<id>/fill` is sent and the action bar shows the tab label

#### Scenario: Herdr not running
- **WHEN** the endpoint answers 503 `Herdr unavailable`
- **THEN** the action bar shows "Not opened: Herdr unavailable"

### Requirement: Viewer requests stay on its own origin
Every request the viewer page makes, for lists, details, PDFs, status changes, deletes, form-filling sessions and resume and cover letter generation, SHALL go to the origin the page was loaded from, using relative paths, so that opened at `http://127.0.0.1:<docs port>/viewer` it uses only loopback endpoints. The page SHALL not describe itself as reachable from the tailnet.

#### Scenario: Opened on the Mac
- **WHEN** the owner opens `http://127.0.0.1:8081/viewer`, opens an application, changes its status and opens its PDFs
- **THEN** every request the page sends is to `http://127.0.0.1:8081`

#### Scenario: No absolute service URL
- **WHEN** the viewer page's HTML and script are inspected
- **THEN** they contain no absolute `http://` or `https://` URL to the service, its Tailscale hostname or its public address

### Requirement: Viewer resume generation endpoint
Where the viewer is served, `POST /viewer/application/{application_id}/resume` SHALL, without the API key, start a resume job for that application exactly as `POST /resume` does, under the same one-running-job rule, and respond 202 with the same body. It SHALL ignore any request body.

#### Scenario: Started
- **WHEN** the viewer posts for application `<id>` with no running resume job
- **THEN** the response is 202 `{"ok": true, "application_id": "<id>", "status": "running", "started_at": "<timestamp>"}` and a resume run starts in the background

#### Scenario: Already running
- **WHEN** a resume job for `<id>` started by `POST /resume` is still running and the viewer posts for `<id>`
- **THEN** the response is 202 with that job's `started_at`, and no second run starts

#### Scenario: Result readable through the keyed status endpoint
- **WHEN** a resume job started from the viewer finishes
- **THEN** `GET /resume/<id>/status` reports it `done` with its `match` and file name, as for a job started by `POST /resume`

#### Scenario: Unknown application
- **WHEN** the ID is not a UUID or not stored
- **THEN** the response is 404 `Application not found` and no job starts

### Requirement: Viewer cover letter generation endpoint
Where the viewer is served, `POST /viewer/application/{application_id}/cover-letter` SHALL, without the API key, start a cover letter job exactly as `POST /cover-letter` does, under the same one-running-job rule and posting-text check, and respond with the same 202 body or 422. It SHALL ignore any request body.

#### Scenario: Started
- **WHEN** the viewer posts for an application with usable posting text and no running cover letter job
- **THEN** the response is 202 with `status` `running` and a cover letter run starts in the background

#### Scenario: No posting text
- **WHEN** the application has no usable posting text
- **THEN** the response is 422 with the same message `POST /cover-letter` gives, and no job starts

#### Scenario: Both kinds together
- **WHEN** a resume job for `<id>` is running and the viewer posts a cover letter for `<id>`
- **THEN** the cover letter job starts, and both run

### Requirement: Viewer generation endpoints guarded like other viewer writes
The two viewer generation endpoints SHALL refuse cross-site requests with 403 `Cross-site request refused` under the rule for viewer writes, before touching the store or starting a job, and SHALL exist only when API docs are enabled. A store failure SHALL get 503 as for the keyed endpoints.

#### Scenario: Cross-site
- **WHEN** a generation request carries `Sec-Fetch-Site: cross-site`
- **THEN** the response is 403 and no job starts

#### Scenario: Docs disabled
- **WHEN** API docs are disabled and a client posts to either viewer generation path, with or without a valid key
- **THEN** the response is 404 as for an unknown path and no job starts

#### Scenario: Keyed endpoints unchanged
- **WHEN** a client posts `POST /resume` without `X-API-Key` on either listener
- **THEN** the response is still 401

### Requirement: Generate and regenerate from the viewer
The selected application's action bar SHALL offer one resume and one cover letter action. Each SHALL read "Generate" when the viewer knows of no generated document of that kind for the application, and "Regenerate" when it does. Using one SHALL post to the matching viewer generation endpoint. A failed request SHALL show its message in the action bar.

#### Scenario: First resume
- **WHEN** the owner selects an application with no report, no resume job and no generated resume, and clicks "Generate resume"
- **THEN** one `POST /viewer/application/<id>/resume` is sent without a confirmation prompt

#### Scenario: Letter without posting text
- **WHEN** the owner clicks the cover letter action and the endpoint answers 422
- **THEN** the action bar shows the endpoint's message and no job is shown as running

### Requirement: Regenerating asks first
Before regenerating a document that already exists, the viewer SHALL ask for confirmation naming the document, the company and role, and saying it replaces the current one when the new run finishes. Cancelling SHALL send nothing.

#### Scenario: Confirmed
- **WHEN** the owner clicks "Regenerate resume" for "Acme – Data Engineer" and confirms
- **THEN** one `POST /viewer/application/<id>/resume` is sent

#### Scenario: Cancelled
- **WHEN** the owner clicks "Regenerate cover letter" and cancels
- **THEN** no request is sent

### Requirement: Job progress shown in the viewer
While a job of either kind is running for an application, its list entry SHALL show which kind is running, and when it is selected, that kind's action SHALL be disabled and say it is generating. While any listed job is running, the viewer SHALL re-read `GET /applications` about every 5 seconds, and SHALL stop when none is running.

#### Scenario: Running after a click
- **WHEN** the owner starts a resume from the viewer
- **THEN** the list entry shows a running resume indicator and the resume action is disabled until the job ends

#### Scenario: Job started elsewhere
- **WHEN** the page loads while a cover letter job started by `POST /cover-letter` is running
- **THEN** that application's entry shows the running indicator and the page polls until the job ends

#### Scenario: Polling stops
- **WHEN** the last running job finishes
- **THEN** the viewer stops re-reading the list

### Requirement: Finished jobs refresh the selected application
When a job of the selected application leaves `running`, the viewer SHALL show the outcome in the action bar. On `done` it SHALL reload the affected document panes, and for a resume the scores, additions and gaps, keeping the document view the owner is on. On `failed` it SHALL show the job's error and leave the shown documents as they are.

#### Scenario: Resume done while selected
- **WHEN** the selected application's resume job becomes `done`
- **THEN** the action bar says the resume was generated, the generated resume pane and score cards show the new result, and the resume action reads "Regenerate resume"

#### Scenario: Letter done while viewing the resume
- **WHEN** the owner is on the resume view and the cover letter job becomes `done`
- **THEN** the resume view stays shown, and the cover letter view shows the new letter when the owner switches to it

#### Scenario: Job failed
- **WHEN** the selected application's cover letter job becomes `failed`
- **THEN** the action bar shows "Cover letter failed: <error>" and the previously shown letter stays

### Requirement: List entries are plain cards
Each list entry SHALL be a single control that selects the application. It SHALL show the company, role, application status, match badge, score when there is one, and recorded date, and SHALL contain no other controls. The selected entry SHALL be marked.

#### Scenario: Entry content
- **WHEN** the list shows a tailored application with base score 38 and tailored score 61, status `verified`, recorded Oct 28
- **THEN** its entry shows the company, role, `verified`, "Tailored", "38 → 61" and the recorded date, and has no select, Fill form or Delete control

#### Scenario: Selecting by entry
- **WHEN** the owner clicks anywhere on an entry
- **THEN** that application is selected and its entry is marked current

### Requirement: List filtered by text
Above the application list, the viewer SHALL offer a search field. A non-empty search SHALL show only applications whose company or role contains it, ignoring case and surrounding spaces, combined with the status and date filters. It SHALL count as a filter for the filtered count and for clearing filters, and SHALL NOT send a request.

#### Scenario: Search by company
- **WHEN** the owner types "snow" and the list holds "Snowflake" and "Samsara"
- **THEN** only the Snowflake entry is listed and no request is sent

#### Scenario: Combined with status
- **WHEN** the search is "engineer" and the status filter is `applied`
- **THEN** only `applied` applications whose company or role contains "engineer" are listed

#### Scenario: Cleared with the other filters
- **WHEN** no entry matches and the owner uses the control that clears the filters
- **THEN** the search, status and dates are all empty and every application is listed
