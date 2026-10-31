# resume-viewer Specification

## Purpose

A read-only page, served only on the owner's tailnet, for reviewing each application's generated resume against the base resume (the two PDFs side by side, the application details, the scores and what tailoring added or left as gaps) and its generated cover letter against the base cover letter.

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
The viewer page and its read endpoints, the cover letter reads included, SHALL NOT create, change or delete any application, report or file, and SHALL NOT start resume or cover letter generation.

#### Scenario: Browsing
- **WHEN** the owner loads the viewer and opens every application
- **THEN** the store and the output folder are unchanged afterwards

#### Scenario: Browsing cover letters
- **WHEN** the owner opens the cover letter view of every application
- **THEN** the store, the output folder and `data/COVER_LETTER.pdf` are unchanged, and no Claude run starts

### Requirement: Viewer requests logged without content
Each request to `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf` and `GET /application/{application_id}/cover-letter.pdf` SHALL emit one `application_request` log line with the method, status, duration and, when known, the application ID. `GET /resume/base.pdf` SHALL emit one `resume_request` line and `GET /cover-letter/base.pdf` one `cover_letter_request` line. No log line SHALL contain the API key, posting text, keywords, requirement text, resume content or letter content. Loading `/viewer` itself SHALL emit no structured request line.

#### Scenario: Detail request logged
- **WHEN** the owner opens an application in the viewer
- **THEN** one `application_request` line with method `GET` and its application ID is logged, without any of its fields' values

#### Scenario: Cover letter reads logged
- **WHEN** the owner switches to the cover letter view for the first time since loading the page
- **THEN** one `application_request` line with method `GET` and the application ID and one `cover_letter_request` line for the base letter are logged, with no path, company or letter text

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
