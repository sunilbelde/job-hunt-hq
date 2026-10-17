# service-config Specification

## Purpose

Defines how the service is configured through environment variables, which are validated at startup so misconfiguration fails fast and secrets stay out of the repository and logs.

## Requirements

### Requirement: Environment-based configuration
The system SHALL read `API_KEY`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` (required), `ANTHROPIC_API_KEY` (optional) and `SIGNED_URL_TTL_SECONDS` from the environment.

#### Scenario: All required values present
- **WHEN** the service starts with every required variable set
- **THEN** it starts and serves requests

### Requirement: Startup validation
The system SHALL fail to start with an error naming the invalid variables when a required variable is missing or empty, without printing secret values.

#### Scenario: Missing required variable
- **WHEN** the service starts without `R2_BUCKET`
- **THEN** startup fails and the error identifies `R2_BUCKET`

#### Scenario: Optional Anthropic key
- **WHEN** the service starts without `ANTHROPIC_API_KEY`
- **THEN** it starts normally

### Requirement: Signed URL TTL bounds
`SIGNED_URL_TTL_SECONDS` SHALL default to 604800 (7 days) and SHALL be a positive integer no greater than 604800; other values SHALL fail startup.

#### Scenario: Default TTL
- **WHEN** the variable is unset
- **THEN** signed URLs are valid for 604800 seconds

#### Scenario: TTL too large
- **WHEN** the variable is set to 604801
- **THEN** startup fails with a validation error

### Requirement: No committed secrets
The repository SHALL provide a `.env.example` listing every variable with placeholder values only, and real secrets SHALL NOT be committed or logged.

#### Scenario: Example file
- **WHEN** a developer opens `.env.example`
- **THEN** every configuration variable appears with a placeholder value and no real credentials
