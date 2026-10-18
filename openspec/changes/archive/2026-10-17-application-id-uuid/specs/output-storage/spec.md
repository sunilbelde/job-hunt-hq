## MODIFIED Requirements

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

### Requirement: Overwrite on regeneration
Generating a resume for an application whose resume file already exists at the computed path SHALL replace that file with the new render.

#### Scenario: Regenerate
- **WHEN** a resume is generated twice for application `<id>`
- **THEN** exactly one file exists in `<OUTPUT_DIR>/<company folder>/<id>/`, holding the second render

### Requirement: Resume files are kept
The service SHALL NOT delete saved resume files or their folders on its own. They SHALL remain until removed outside the service, including after the application is deleted or the service restarts.

#### Scenario: Old resume kept
- **WHEN** a resume was saved 60 days ago and the service has run continuously since
- **THEN** the file still exists

#### Scenario: Application deleted
- **WHEN** application `<id>` is deleted with `DELETE /application/<id>`
- **THEN** its resume file is still on disk

## ADDED Requirements

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
