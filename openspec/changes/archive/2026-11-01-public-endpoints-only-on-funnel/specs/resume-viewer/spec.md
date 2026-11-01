# Spec Delta

## MODIFIED Requirements

### Requirement: Viewer write endpoints only where the viewer is
The viewer write endpoints SHALL exist only when API docs are enabled. When docs are disabled, a request to either SHALL be handled as an unknown path, whatever `X-API-Key` it carries. The keyed `PATCH` and `DELETE /application/{application_id}` SHALL behave as before on the docs port and on a development server, and SHALL NOT be served on the installed service's public listener.

#### Scenario: Docs disabled
- **WHEN** API docs are disabled and a client sends `PATCH` or `DELETE /viewer/application/<id>` for an existing row, with or without a valid key
- **THEN** the response is 404 and the row is unchanged

#### Scenario: Keyed endpoints still need the key
- **WHEN** API docs are enabled and a client sends `DELETE /application/<id>` without `X-API-Key`
- **THEN** the response is 401 and the row still exists

#### Scenario: Keyed endpoints not public
- **WHEN** a client sends `PATCH` or `DELETE /application/<id>` with a valid key to the installed service's public listener
- **THEN** the response is 404 and the row is unchanged

## ADDED Requirements

### Requirement: Viewer requests stay on its own origin
Every request the viewer page makes, for lists, details, PDFs, status changes, deletes and form-filling sessions, SHALL go to the origin the page was loaded from, using relative paths, so that opened at `http://127.0.0.1:<docs port>/viewer` it uses only loopback endpoints. The page SHALL not describe itself as reachable from the tailnet.

#### Scenario: Opened on the Mac
- **WHEN** the owner opens `http://127.0.0.1:8081/viewer`, opens an application, changes its status and opens its PDFs
- **THEN** every request the page sends is to `http://127.0.0.1:8081`

#### Scenario: No absolute service URL
- **WHEN** the viewer page's HTML and script are inspected
- **THEN** they contain no absolute `http://` or `https://` URL to the service, its Tailscale hostname or its public address
