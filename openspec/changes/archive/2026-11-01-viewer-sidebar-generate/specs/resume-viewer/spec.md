# Spec Delta

## MODIFIED Requirements

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

### Requirement: Fill form from the viewer
The selected application's action bar SHALL offer a **Fill form** button that posts to the fill endpoint for that application. While the request is pending the button SHALL be disabled. On success the action bar SHALL show "Opened Herdr tab <label>", or "Already open in Herdr tab <label>"; on failure, "Not opened: <message>". List entries SHALL carry no Fill form button.

#### Scenario: Opened
- **WHEN** the owner clicks Fill form in the action bar
- **THEN** one `POST /viewer/application/<id>/fill` is sent and the action bar shows the tab label

#### Scenario: Herdr not running
- **WHEN** the endpoint answers 503 `Herdr unavailable`
- **THEN** the action bar shows "Not opened: Herdr unavailable"

## ADDED Requirements

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
