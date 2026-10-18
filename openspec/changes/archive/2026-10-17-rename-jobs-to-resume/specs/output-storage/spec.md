## MODIFIED Requirements

### Requirement: Private file access
Saved resume files SHALL NOT be served over HTTP by the service. Every folder the service creates under the output directory SHALL be accessible only by the service's user account, and every resume file it writes SHALL be readable and writable only by that account.

#### Scenario: Unsigned access
- **WHEN** any client requests a path under `/files/`, with or without signature parameters, or any other path naming a saved resume
- **THEN** the system responds 404 and returns no file content

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

## ADDED Requirements

### Requirement: Resume file path
The system SHALL save each generated resume at `<OUTPUT_DIR>/<company folder>/<application_id>/SUNIL BELDE.pdf`, where the company folder is derived from the application's stored `company` at generation time and `application_id` is written in base 10. Missing folders SHALL be created.

#### Scenario: First resume for an application
- **WHEN** a resume is generated for application 7 whose company is "Acme Corp" and no folders exist yet
- **THEN** the file `<OUTPUT_DIR>/Acme Corp/7/SUNIL BELDE.pdf` exists afterwards

#### Scenario: Two applications at one company
- **WHEN** resumes are generated for applications 7 and 9, both with company "Acme Corp"
- **THEN** the files are `<OUTPUT_DIR>/Acme Corp/7/SUNIL BELDE.pdf` and `<OUTPUT_DIR>/Acme Corp/9/SUNIL BELDE.pdf`

#### Scenario: Company renamed
- **WHEN** application 7's company is changed from "Acme" to "Acme Inc" after a resume was generated, and a resume is generated again
- **THEN** the new file is at `<OUTPUT_DIR>/Acme Inc/7/SUNIL BELDE.pdf`
- **AND** the file under `<OUTPUT_DIR>/Acme/7/` is left unchanged

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
Generating a resume for an application whose resume file already exists at the computed path SHALL replace that file with the new render.

#### Scenario: Regenerate
- **WHEN** a resume is generated twice for application 7
- **THEN** exactly one file exists in `<OUTPUT_DIR>/<company folder>/7/`, holding the second render

### Requirement: Resume files are kept
The service SHALL NOT delete saved resume files or their folders on its own. They SHALL remain until removed outside the service, including after the application is deleted or the service restarts.

#### Scenario: Old resume kept
- **WHEN** a resume was saved 60 days ago and the service has run continuously since
- **THEN** the file still exists

#### Scenario: Application deleted
- **WHEN** application 7 is deleted with `DELETE /application/7`
- **THEN** its resume file is still on disk

## REMOVED Requirements

### Requirement: Dated unique object keys
**Reason**: Files are now saved at a fixed per-application path, not under random dated keys.
**Migration**: Use the `saved_path` returned by `POST /resume`. Existing `<OUTPUT_DIR>/outputs/` files are left in place and may be deleted by hand.

### Requirement: Pre-signed download URLs
**Reason**: The service is local-only and no longer issues download links.
**Migration**: Open the file at `saved_path` directly on the Mac.

### Requirement: Content-Type preserved on download
**Reason**: Files are no longer downloaded through the service.
**Migration**: None needed. The file's `.pdf` extension identifies its type locally.

### Requirement: Retention cleanup
**Reason**: Resume files are kept until deleted by hand, and no other files are written to the output tree.
**Migration**: Delete unwanted resume folders, and the legacy `<OUTPUT_DIR>/outputs/` folder, by hand.
