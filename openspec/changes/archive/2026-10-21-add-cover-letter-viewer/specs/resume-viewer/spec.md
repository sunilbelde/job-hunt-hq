# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
