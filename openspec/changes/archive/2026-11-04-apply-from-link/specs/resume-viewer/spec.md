# Spec Delta

## ADDED Requirements

### Requirement: Viewer apply-from-link endpoint
Where the viewer is served, `POST /viewer/apply-from-link` SHALL, without the API key, take a JSON body `{"link": "<url>"}` and open a tab in the `FILL_WORKSPACE` Herdr workspace, starting in the repository, that runs `claude --chrome "/apply-from-link <link>"`. It SHALL change no stored data.

#### Scenario: Tab opened
- **WHEN** the viewer posts `{"link": "https://jobs.ashbyhq.com/acme/1"}`
- **THEN** a tab labelled `ByLink-jobs.ashbyhq.com-<hash>` opens running that command
- **AND** the response is 200 with exactly `{"ok": true, "tab_id": "<herdr tab id>", "tab_label": "<label>", "already_open": false}`

#### Scenario: Same link already open
- **WHEN** a tab for a link with the same dedupe key is open in the workspace
- **THEN** no tab is opened, nothing is run, and the response is 200 with that tab and `already_open` true

#### Scenario: Herdr unavailable
- **WHEN** Herdr is missing, not running, or returns an error or an unexpected reply
- **THEN** the response is 503 `{"ok": false, "message": "Herdr unavailable"}` and the log records a `herdr_error` without the link or Herdr's output

### Requirement: Link validated before it reaches a command
The endpoint SHALL accept only a string `link` of at most 2048 characters that is an `http` or `https` URL with a host, no user information, and no whitespace or control characters. Anything else, including a body that is not a JSON object, SHALL be answered 422 `{"ok": false, "message": ...}` naming `link` without its value, and Herdr SHALL NOT be called.

#### Scenario: Not a web link
- **WHEN** `link` is `file:///etc/passwd`, `javascript:alert(1)` or "not a url"
- **THEN** the response is 422 naming `link`, the value is not echoed, and Herdr is not called

#### Scenario: Hidden whitespace
- **WHEN** `link` contains a space, a newline or another control character
- **THEN** the response is 422 and Herdr is not called

#### Scenario: Too long or wrong type
- **WHEN** `link` is over 2048 characters, missing, null or a number, or the body is not valid JSON
- **THEN** the response is 422 and Herdr is not called

### Requirement: Link is one quoted command argument
The link SHALL reach the command only as part of a single shell-quoted argument, so that no character in it can end the argument or start another command.

#### Scenario: Shell syntax in a link
- **WHEN** a valid link contains `;`, `$()`, a backtick or a single quote
- **THEN** the command run still has the fixed form, with the link inside its one quoted argument

### Requirement: Link tab label
The tab label SHALL be `ByLink-<host>-<hash>`, where `<host>` is the link's host with control characters removed and `<hash>` is a short hash of the link's dedupe key. The open-tab check SHALL match on that hash, so two forms of one link find the same tab.

#### Scenario: Decorated link finds the open tab
- **WHEN** a tab was opened for `https://jobs.ashbyhq.com/acme/1` and the owner submits `https://jobs.ashbyhq.com/acme/1/?utm_source=x`
- **THEN** the response has `already_open` true

### Requirement: Apply-from-link endpoint guarded like other viewer writes
`POST /viewer/apply-from-link` SHALL follow the rules for viewer writes: 403 `Cross-site request refused` before reading the body for a cross-site request, and handled as an unknown path where API docs are disabled, whatever `X-API-Key` it carries. The installed service's public listener SHALL NOT serve it.

#### Scenario: Request from another site
- **WHEN** a request carries `Sec-Fetch-Site: cross-site` and a valid body
- **THEN** the response is 403 and Herdr is not called

#### Scenario: Docs disabled
- **WHEN** API docs are disabled and a client posts a valid body, with or without a valid key
- **THEN** the response is 404 and Herdr is not called

#### Scenario: Public address
- **WHEN** a client posts to the installed service's public listener
- **THEN** the response is 404

### Requirement: Link box in the viewer
Above the application list, the viewer SHALL offer a link field and an **Apply from link** button that posts the trimmed link to the endpoint. While the request is pending the button SHALL be disabled. An empty field SHALL send nothing.

#### Scenario: Started
- **WHEN** the owner enters a link and clicks Apply from link
- **THEN** one `POST /viewer/apply-from-link` is sent, the page shows "Opened Herdr tab <label>", and the field is cleared

#### Scenario: Already open
- **WHEN** the endpoint answers `already_open` true
- **THEN** the page shows "Already open in Herdr tab <label>"

#### Scenario: Refused
- **WHEN** the endpoint answers 422 or 503
- **THEN** the page shows "Not opened: <message>" and keeps the field's text

#### Scenario: Empty field
- **WHEN** the field is empty or only spaces and the owner clicks the button
- **THEN** no request is sent

### Requirement: New application appears after a link is started
For 15 minutes after a link session is opened, the viewer SHALL keep re-reading the list at its usual polling interval, even with no job running, so that the application appears when recorded. Polling SHALL then return to running only while a job runs.

#### Scenario: Application recorded by the session
- **WHEN** the session records the application while the page is open
- **THEN** its entry appears in the list without a reload

#### Scenario: Window ends
- **WHEN** 15 minutes have passed since the last link was started and no job is running
- **THEN** the page stops re-reading the list

### Requirement: Origin tag on list entries
Each list entry SHALL show a tag for how the application was added: **ByLink** for `added_via` `link` and **Manual** for `manual`. The tag SHALL be display only.

#### Scenario: Added by link
- **WHEN** an application has `added_via` `link`
- **THEN** its entry shows the tag ByLink

#### Scenario: Existing application
- **WHEN** an application was recorded before this field existed
- **THEN** its entry shows the tag Manual

## MODIFIED Requirements

### Requirement: Application list
`GET /applications` SHALL return every stored application, most recently generated first and then most recently recorded, each with its ID, company, role, status, recorded time, `added_via`, `jobs` and, when it has a report, the generation time, match status, base score and generated score. `jobs` SHALL hold `resume` and `cover_letter`, each null when that kind has no job, else exactly `status`, `started_at`, `finished_at` and `error`. It SHALL NOT include posting text, nor any job's saved path, match or letter text. It SHALL NOT require the API key, and SHALL ignore an `X-API-Key` header if one is sent.

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

#### Scenario: Origin listed
- **WHEN** the store holds an application recorded by link and one with no recorded origin
- **THEN** the first carries `added_via` `link` and the second `manual`

#### Scenario: Filtered by link
- **WHEN** `GET /applications?job_link=<link>` is sent and a stored application's `job_link` has the same dedupe key
- **THEN** the response holds only that application

#### Scenario: Filter matches nothing
- **WHEN** no stored application has that dedupe key
- **THEN** the response is 200 with an empty `applications` list

#### Scenario: Filter ignores tracking parameters
- **WHEN** the stored link is `https://jobs.ashbyhq.com/acme/1` and the filter value is `https://jobs.ashbyhq.com/acme/1/?utm_source=x`
- **THEN** that application is returned

### Requirement: Viewer reads never change data
The viewer page and its read endpoints, the cover letter reads included, SHALL NOT create, change or delete any application, report or file, and SHALL NOT start resume or cover letter generation. Only the viewer write endpoints SHALL change stored data or start work: a status change or a confirmed delete changes only the store, the fill and apply-from-link endpoints only open a Herdr tab, and only the two viewer generation endpoints start a generation run.

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
Each request to `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `PATCH /viewer/application/{application_id}`, `DELETE /viewer/application/{application_id}`, `POST /viewer/application/{application_id}/resume`, `POST /viewer/application/{application_id}/cover-letter` and `POST /viewer/apply-from-link` SHALL emit one `application_request` log line with the method, status, duration and, when known, the application ID. `GET /resume/base.pdf` SHALL emit one `resume_request` line and `GET /cover-letter/base.pdf` one `cover_letter_request` line. No log line SHALL contain the API key, posting text, keywords, requirement text, resume content, letter content, the link sent to the apply-from-link endpoint or to the `job_link` filter, or the status sent in a write. Loading `/viewer` itself SHALL emit no structured request line.

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

#### Scenario: Apply from link logged
- **WHEN** the owner submits a link in the viewer
- **THEN** one `application_request` line with method `POST` and the status is logged, and it does not contain the link

#### Scenario: Link lookup logged
- **WHEN** a client sends `GET /applications?job_link=<link>`
- **THEN** the log line does not contain the link

### Requirement: List entries are plain cards
Each list entry SHALL be a single control that selects the application. It SHALL show the company, role, application status, origin tag, match badge, score when there is one, and recorded date, and SHALL contain no other controls. The selected entry SHALL be marked.

#### Scenario: Entry content
- **WHEN** the list shows a tailored application with base score 38 and tailored score 61, status `verified`, recorded Oct 28
- **THEN** its entry shows the company, role, `verified`, an origin tag, "Tailored", "38 → 61" and the recorded date, and has no select, Fill form or Delete control

#### Scenario: Selecting by entry
- **WHEN** the owner clicks anywhere on an entry
- **THEN** that application is selected and its entry is marked current
