# Spec Delta

## MODIFIED Requirements

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

### Requirement: Overwrite on regeneration
Generating a resume for an application whose resume file already exists at the computed path SHALL replace that file with the new render. Generating a cover letter SHALL likewise replace an existing cover letter at its path. Neither SHALL touch the other's file.

#### Scenario: Regenerate
- **WHEN** a resume is generated twice for application `<id>`
- **THEN** exactly one resume file exists in `<OUTPUT_DIR>/<company folder>/<id>/`, holding the second render

#### Scenario: Regenerate the cover letter
- **WHEN** a cover letter is generated twice for application `<id>`
- **THEN** exactly one cover letter file exists in that folder, holding the second letter, and the resume there is unchanged

## ADDED Requirements

### Requirement: Cover letter written only on request
Only `POST /cover-letter` SHALL create or replace an application's cover letter file. Resume generation SHALL NOT create, replace or delete it, and a file placed there outside the service SHALL stay unchanged until a cover letter is requested.

#### Scenario: Resume generated
- **WHEN** a resume is generated for application `<id>` and no cover letter exists
- **THEN** afterwards no cover letter file exists in its folder

#### Scenario: File already present
- **WHEN** a cover letter file exists and a resume is generated again
- **THEN** that file is unchanged

### Requirement: Cover letter files are private, complete and kept
Cover letter files SHALL be written like resume files: atomically, so the path holds either the previous complete letter or the new one; readable and writable only by the service's user account, inside folders only that account can access; never served over HTTP; and never deleted by the service, including after the application is deleted.

#### Scenario: Failed write
- **WHEN** writing a replacement cover letter fails partway
- **THEN** the previous cover letter is unchanged and no temporary file is left behind

#### Scenario: File permissions
- **WHEN** the service writes a cover letter
- **THEN** its mode grants no access to group or other users

#### Scenario: No HTTP access
- **WHEN** any client requests a path naming a saved cover letter
- **THEN** the system responds 404 and returns no file content

#### Scenario: Application deleted
- **WHEN** application `<id>` is deleted
- **THEN** its cover letter file is still on disk

## REMOVED Requirements

### Requirement: Cover letter not yet written
**Reason**: Cover letters are now generated, on request only, by `POST /cover-letter`.
**Migration**: "Cover letter written only on request" keeps the guarantee that resume generation never touches the cover letter file.
