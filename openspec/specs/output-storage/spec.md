# output-storage Specification

## Purpose

Defines how generated files are persisted to Cloudflare R2 and how time-limited download links are issued for them.

## Requirements

### Requirement: Private file access
Saved resume files SHALL NOT be served over HTTP by the service, except by the viewer's `GET /application/{application_id}/resume.pdf`, which exists only where API docs are enabled and requires the API key. Every folder the service creates under the output directory SHALL be accessible only by the service's user account, and every resume file it writes SHALL be readable and writable only by that account.

#### Scenario: Unsigned access
- **WHEN** any client requests a path under `/files/`, with or without signature parameters, or any other path naming a saved resume apart from the viewer's PDF endpoint
- **THEN** the system responds 404 and returns no file content

#### Scenario: Viewer PDF without the key
- **WHEN** a client requests `GET /application/{application_id}/resume.pdf` without a valid `X-API-Key`
- **THEN** the system responds 401 and returns no file content

#### Scenario: Viewer PDF where docs are disabled
- **WHEN** API docs are disabled and a client requests `GET /application/{application_id}/resume.pdf` with a valid key
- **THEN** the system responds 404 and returns no file content

#### Scenario: Stored path outside the output directory
- **WHEN** an application's stored report names a saved path outside `OUTPUT_DIR`
- **THEN** the viewer's PDF endpoint responds 404 and reads no file

#### Scenario: Path traversal
- **WHEN** an application's stored company contains `..`, `/`, `\` or an absolute path
- **THEN** its resume is written inside `OUTPUT_DIR`, and no file or folder outside `OUTPUT_DIR` is created or changed

#### Scenario: Directory permissions
- **WHEN** the service creates the output directory, a company folder or an application folder
- **THEN** other local user accounts cannot list or read it

#### Scenario: File permissions
- **WHEN** the service writes a resume file
- **THEN** its mode grants no access to group or other users

### Requirement: Complete files only
A resume file SHALL appear at its path only once completely written. Replacing an existing resume SHALL be atomic, so the path always holds either the previous complete file or the new complete file.

#### Scenario: Interrupted write
- **WHEN** the service is stopped while writing a resume file
- **THEN** no partial file exists at that file's path, and any previous resume at that path is intact

#### Scenario: Failed regeneration
- **WHEN** writing a replacement resume fails partway
- **THEN** the previously saved resume at that path is unchanged and no temporary file is left behind

### Requirement: Resume file path
The system SHALL save each generated resume at `<OUTPUT_DIR>/<company folder>/<application_id>/SUNIL BELDE.pdf`, where the company folder is derived from the application's stored `company` at generation time and `application_id` is the application's UUID in lowercase. Missing folders SHALL be created.

#### Scenario: First resume for an application
- **WHEN** a resume is generated for application `<id>` whose company is "Acme Corp" and no folders exist yet
- **THEN** the file `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` exists afterwards

#### Scenario: Two applications at one company
- **WHEN** resumes are generated for applications `<a>` and `<b>`, both with company "Acme Corp"
- **THEN** the files are `<OUTPUT_DIR>/Acme Corp/<a>/SUNIL BELDE.pdf` and `<OUTPUT_DIR>/Acme Corp/<b>/SUNIL BELDE.pdf`

#### Scenario: Company renamed
- **WHEN** application `<id>`'s company is changed from "Acme" to "Acme Inc" after a resume was generated, and a resume is generated again
- **THEN** the new file is at `<OUTPUT_DIR>/Acme Inc/<id>/SUNIL BELDE.pdf`
- **AND** the file under `<OUTPUT_DIR>/Acme/<id>/` is left unchanged

### Requirement: Cover letter file path
The cover letter for an application SHALL be saved at `<OUTPUT_DIR>/<company folder>/<application_id>/SUNIL BELDE - Cover Letter.pdf`, the folder that application's resume uses, with the company folder derived from the stored company exactly as for the resume. The path SHALL NOT depend on whether a resume exists.

#### Scenario: Location next to the resume
- **WHEN** a cover letter is generated for application `<id>` whose company is "Acme Corp"
- **THEN** it is saved at `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf`, beside `SUNIL BELDE.pdf` when that exists

#### Scenario: Company folder naming applies
- **WHEN** the company is "AT&T / Mobility: West"
- **THEN** the cover letter is saved inside the folder "AT&T - Mobility- West", like the resume

#### Scenario: No resume yet
- **WHEN** a cover letter is generated for an application that has no resume
- **THEN** the application's folder is created and holds only the cover letter

### Requirement: Company folder naming
The company folder SHALL be the stored `company` with each `/`, `\`, `:` and control character replaced by `-`, leading and trailing spaces and dots removed, and the result cut to 100 characters. It SHALL be `unknown-company` if nothing remains, and SHALL get a leading `_` if it starts with `applications.sqlite3` in any case.

#### Scenario: Spaces and case kept
- **WHEN** the company is "Acme Corp"
- **THEN** the folder is "Acme Corp"

#### Scenario: Separators replaced
- **WHEN** the company is "AT&T / Mobility: West"
- **THEN** the folder is "AT&T - Mobility- West"

#### Scenario: Traversal neutralised
- **WHEN** the company is "../../etc" or ".."
- **THEN** the folder is "-..-etc" or "unknown-company" respectively, and the file is written inside `OUTPUT_DIR`

#### Scenario: Store name protected
- **WHEN** the company is "applications.sqlite3"
- **THEN** the folder is "_applications.sqlite3" and the application store is untouched

#### Scenario: Long name
- **WHEN** the company is 300 characters long
- **THEN** the folder name is its first 100 characters, trimmed as above

### Requirement: Overwrite on regeneration
Generating a resume for an application whose resume file already exists at the computed path SHALL replace that file with the new render. Generating a cover letter SHALL likewise replace an existing cover letter at its path. Neither SHALL touch the other's file.

#### Scenario: Regenerate
- **WHEN** a resume is generated twice for application `<id>`
- **THEN** exactly one resume file exists in `<OUTPUT_DIR>/<company folder>/<id>/`, holding the second render

#### Scenario: Regenerate the cover letter
- **WHEN** a cover letter is generated twice for application `<id>`
- **THEN** exactly one cover letter file exists in that folder, holding the second letter, and the resume there is unchanged

### Requirement: Resume files are kept
The service SHALL NOT delete saved resume files or their folders on its own. They SHALL remain until removed outside the service, including after the application is deleted or the service restarts.

#### Scenario: Old resume kept
- **WHEN** a resume was saved 60 days ago and the service has run continuously since
- **THEN** the file still exists

#### Scenario: Application deleted
- **WHEN** application `<id>` is deleted with `DELETE /application/<id>`
- **THEN** its resume file is still on disk

### Requirement: Resume folders follow migrated IDs
At startup, every application folder directly inside a company folder whose name is an old integer ID recorded by the integer ID migration SHALL be renamed to that application's UUID, keeping its contents. A folder whose integer has no recorded UUID, or whose UUID folder already exists in the same company folder, SHALL be left as it is and logged. Renaming SHALL NOT delete any file, and SHALL complete on a later start if interrupted.

#### Scenario: Existing resume moved
- **WHEN** application 1, company "Acme Corp", is migrated to `<id>` and `<OUTPUT_DIR>/Acme Corp/1/SUNIL BELDE.pdf` exists
- **THEN** after startup the file is at `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE.pdf` and `<OUTPUT_DIR>/Acme Corp/1/` no longer exists

#### Scenario: Folders under an earlier company name
- **WHEN** resumes for application 1 exist under both `Acme/1/` and `Acme Inc/1/`
- **THEN** both are renamed to `Acme/<id>/` and `Acme Inc/<id>/`

#### Scenario: Folder for a deleted application
- **WHEN** `<OUTPUT_DIR>/Acme Corp/5/` exists but application 5 was deleted before the migration
- **THEN** the folder is left unchanged

#### Scenario: Interrupted rename
- **WHEN** the service stops after the store was migrated but before every folder was renamed
- **THEN** the next start renames the remaining folders

#### Scenario: Target already exists
- **WHEN** both `Acme Corp/1/` and `Acme Corp/<id>/` exist
- **THEN** neither is changed and the conflict is logged

### Requirement: Cover letter written only on request
Only `POST /cover-letter` SHALL create or replace an application's cover letter file. Resume generation SHALL NOT create, replace or delete it, and a file placed there outside the service SHALL stay unchanged until a cover letter is requested.

#### Scenario: Resume generated
- **WHEN** a resume is generated for application `<id>` and no cover letter exists
- **THEN** afterwards no cover letter file exists in its folder

#### Scenario: File already present
- **WHEN** a cover letter file exists and a resume is generated again
- **THEN** that file is unchanged

### Requirement: Cover letter files are private, complete and kept
Cover letter files SHALL be written like resume files: atomically, so the path holds either the previous complete letter or the new one; readable and writable only by the service's user account, inside folders only that account can access; and never deleted by the service, including after the application is deleted. Over HTTP they SHALL be readable only through the viewer's `GET /application/{application_id}/cover-letter.pdf`, which exists only where API docs are enabled, and never by a path naming the file.

#### Scenario: Failed write
- **WHEN** writing a replacement cover letter fails partway
- **THEN** the previous cover letter is unchanged and no temporary file is left behind

#### Scenario: File permissions
- **WHEN** the service writes a cover letter
- **THEN** its mode grants no access to group or other users

#### Scenario: No HTTP access
- **WHEN** any client requests a path naming a saved cover letter
- **THEN** the system responds 404 and returns no file content

#### Scenario: Viewer read only where docs are enabled
- **WHEN** a client on a listener with API docs disabled requests `GET /application/{id}/cover-letter.pdf`
- **THEN** the system responds 404 and returns no file content

#### Scenario: Application deleted
- **WHEN** application `<id>` is deleted
- **THEN** its cover letter file is still on disk

### Requirement: Host paths never in responses
No HTTP response body from the service SHALL contain a file-system path on the service host: not the `OUTPUT_DIR` path, not the service user's home directory, and not a company or application folder. This SHALL hold on both listeners, for success and error responses and for 404s. A saved file SHALL be identified to clients only by its file name. Stored reports and job records SHALL keep the absolute path for the service's own use.

#### Scenario: Every JSON and HTML response checked
- **WHEN** a resume and a cover letter have been generated for an application, and every documented JSON or HTML endpoint is called for it, including unknown-ID, wrong-key and no-job 404 and 401 cases
- **THEN** no response body contains the `OUTPUT_DIR` path or the service user's home directory

#### Scenario: Stored path still used to read the file
- **WHEN** an application's resume was saved under its company's folder, and the company was renamed afterwards
- **THEN** the viewer's PDF endpoints still find the resume and the cover letter through the absolute path stored in the report
