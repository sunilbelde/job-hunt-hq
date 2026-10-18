# service-config Specification

## Purpose

Defines how the service is configured through environment variables, which are validated at startup so misconfiguration fails fast and secrets stay out of the repository and logs.

## Requirements

### Requirement: Environment-based configuration
The system SHALL read `API_KEY` (required), `OUTPUT_DIR` (optional, with a default) and `ANTHROPIC_API_KEY` (optional) from the environment or the repository's `.env` file, SHALL NOT require any cloud credentials, and SHALL ignore variables it no longer uses, such as `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL`, `SIGNED_URL_TTL_SECONDS` and `OUTPUT_RETENTION_DAYS`.

#### Scenario: All required values present
- **WHEN** the service starts with every required variable set
- **THEN** it starts and serves requests

#### Scenario: No cloud variables needed
- **WHEN** the service starts with no `R2_*`, Google Cloud or other cloud provider variables set
- **THEN** it starts normally

#### Scenario: Output directory default
- **WHEN** `OUTPUT_DIR` is unset
- **THEN** files are stored under `~/Library/Application Support/job-hunt-hq/` of the service's user

#### Scenario: Retired variables ignored
- **WHEN** the service starts with `.env` still setting `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL`, `SIGNED_URL_TTL_SECONDS` and `OUTPUT_RETENTION_DAYS`, including invalid values such as `SIGNED_URL_TTL_SECONDS=999999`
- **THEN** it starts normally

#### Scenario: Retired variables not required
- **WHEN** the service starts with only `API_KEY` set
- **THEN** it starts normally

### Requirement: Startup validation
The system SHALL fail to start with an error naming the invalid variables when a required variable is missing or empty, without printing secret values.

#### Scenario: Missing required variable
- **WHEN** the service starts without `API_KEY`, or with `API_KEY` empty
- **THEN** startup fails and the error identifies `API_KEY`

#### Scenario: Optional Anthropic key
- **WHEN** the service starts without `ANTHROPIC_API_KEY`
- **THEN** it starts normally

### Requirement: No committed secrets
The repository SHALL provide a `.env.example` listing every variable with placeholder values only, and real secrets SHALL NOT be committed or logged.

#### Scenario: Example file
- **WHEN** a developer opens `.env.example`
- **THEN** every configuration variable appears with a placeholder value and no real credentials

### Requirement: Output directory usable at startup
At startup the system SHALL create the output directory if it does not exist, with access limited to the service's user, and SHALL fail to start if the directory cannot be created or written.

#### Scenario: Missing directory created
- **WHEN** `OUTPUT_DIR` points at a path that does not exist yet
- **THEN** the service creates it and starts

#### Scenario: Unwritable directory
- **WHEN** `OUTPUT_DIR` points at a directory the service user cannot write
- **THEN** startup fails with an error naming `OUTPUT_DIR`
