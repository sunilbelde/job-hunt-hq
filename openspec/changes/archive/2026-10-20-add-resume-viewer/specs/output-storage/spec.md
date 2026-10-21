# Spec Delta

## MODIFIED Requirements

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
