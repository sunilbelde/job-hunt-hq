# Spec Delta

## MODIFIED Requirements

### Requirement: API docs setting
The system SHALL read an optional boolean `API_DOCS_ENABLED` from the environment or `.env`, defaulting to `false`, which turns the API reference pages, the OpenAPI document, the resume viewer and the viewer's read endpoints on or off. A value set in the process environment SHALL take precedence over `.env`. A value that is not a boolean SHALL fail startup with an error naming `API_DOCS_ENABLED`.

#### Scenario: Unset
- **WHEN** the service starts without `API_DOCS_ENABLED`
- **THEN** it starts normally with API docs and the viewer disabled

#### Scenario: Enabled for local development
- **WHEN** the service starts with `API_DOCS_ENABLED=true`
- **THEN** it serves the API reference pages and the resume viewer

#### Scenario: Environment overrides env file
- **WHEN** `.env` sets `API_DOCS_ENABLED=true` and the process environment sets `API_DOCS_ENABLED=false`
- **THEN** API docs and the viewer are disabled

#### Scenario: Invalid value
- **WHEN** the service starts with `API_DOCS_ENABLED=maybe`
- **THEN** startup fails and the error identifies `API_DOCS_ENABLED`

#### Scenario: Documented in example file
- **WHEN** a developer opens `.env.example`
- **THEN** `API_DOCS_ENABLED` appears with the value `false` and a note that it is for local development only and also turns on the resume viewer
