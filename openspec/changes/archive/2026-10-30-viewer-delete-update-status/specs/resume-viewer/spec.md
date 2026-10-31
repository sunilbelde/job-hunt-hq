# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
