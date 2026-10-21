# Spec Delta

## ADDED Requirements

### Requirement: Pinned reference page assets
The interactive reference page SHALL load its Swagger UI script and stylesheet, and `/redoc` its ReDoc script, from an exact, pinned version, with integrity checks, so the code that runs where the API key is typed cannot change without a change to this repository.

#### Scenario: Exact version
- **WHEN** a browser loads `/docs` or `/redoc`
- **THEN** every Swagger UI or ReDoc script and stylesheet URL on the page names an exact version (major, minor and patch), not a range such as `@5` or `@2`

#### Scenario: Integrity checked
- **WHEN** a browser loads `/docs`
- **THEN** the Swagger UI script and stylesheet tags carry a subresource integrity hash, so a modified file is refused

#### Scenario: Page behaviour unchanged
- **WHEN** a user opens `/docs` with the pinned assets
- **THEN** endpoints are grouped by tag with coloured method badges, Authorize and Try it out work, and an entered key is not persisted across reloads

### Requirement: Primary health check listed first
The reference SHALL list `GET /healthz` before its alias `GET /health` within the `health` tag.

#### Scenario: Order in the document
- **WHEN** the OpenAPI document is fetched
- **THEN** the `/healthz` path appears before the `/health` path
