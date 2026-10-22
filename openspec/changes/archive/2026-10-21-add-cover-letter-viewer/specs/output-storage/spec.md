# Spec Delta

## MODIFIED Requirements

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
