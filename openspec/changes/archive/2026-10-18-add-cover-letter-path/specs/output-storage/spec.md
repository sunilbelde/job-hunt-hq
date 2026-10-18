# Spec Delta

## ADDED Requirements

### Requirement: Cover letter file path
The cover letter for an application SHALL be located at `<OUTPUT_DIR>/<company folder>/<application_id>/SUNIL BELDE - Cover Letter.pdf`, in the same folder as that application's resume, with the company folder derived exactly as for the resume.

#### Scenario: Location next to the resume
- **WHEN** a resume is generated for application `<id>` whose company is "Acme Corp"
- **THEN** its cover letter path is `<OUTPUT_DIR>/Acme Corp/<id>/SUNIL BELDE - Cover Letter.pdf`

#### Scenario: Company folder naming applies
- **WHEN** the company is "AT&T / Mobility: West"
- **THEN** the cover letter path is inside the folder "AT&T - Mobility- West", like the resume

### Requirement: Cover letter not yet written
Until cover letter generation is implemented, the service SHALL NOT create, replace or delete any file at an application's cover letter path. A file placed there outside the service SHALL be left unchanged.

#### Scenario: Resume generated
- **WHEN** a resume is generated for application `<id>` and no cover letter exists
- **THEN** afterwards no file exists at its cover letter path, and the resume is the only file in `<OUTPUT_DIR>/<company folder>/<id>/`

#### Scenario: File already present
- **WHEN** a file exists at the cover letter path and a resume is generated again
- **THEN** that file is unchanged
