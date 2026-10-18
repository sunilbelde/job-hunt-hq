# Spec Delta

## MODIFIED Requirements

### Requirement: Environment-based configuration
The system SHALL read `API_KEY`, `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL` (required), `OUTPUT_DIR`, `OUTPUT_RETENTION_DAYS`, `SIGNED_URL_TTL_SECONDS` (optional, with defaults) and `ANTHROPIC_API_KEY` (optional) from the environment or the repository's `.env` file, and SHALL NOT require any cloud credentials.

#### Scenario: All required values present
- **WHEN** the service starts with every required variable set
- **THEN** it starts and serves requests

#### Scenario: No cloud variables needed
- **WHEN** the service starts with no `R2_*`, Google Cloud or other cloud provider variables set
- **THEN** it starts normally

#### Scenario: Output directory default
- **WHEN** `OUTPUT_DIR` is unset
- **THEN** files are stored under `~/Library/Application Support/job-hunt-hq/` of the service's user

### Requirement: Startup validation
The system SHALL fail to start with an error naming the invalid variables when a required variable is missing or empty, without printing secret values.

#### Scenario: Missing required variable
- **WHEN** the service starts without `LINK_SIGNING_SECRET`
- **THEN** startup fails and the error identifies `LINK_SIGNING_SECRET`

#### Scenario: Optional Anthropic key
- **WHEN** the service starts without `ANTHROPIC_API_KEY`
- **THEN** it starts normally

## ADDED Requirements

### Requirement: Signing secret strength
`LINK_SIGNING_SECRET` SHALL be at least 32 characters long, and startup SHALL fail otherwise.

#### Scenario: Short secret
- **WHEN** `LINK_SIGNING_SECRET` is 16 characters
- **THEN** startup fails with an error naming `LINK_SIGNING_SECRET` and not showing its value

### Requirement: Public base URL format
`PUBLIC_BASE_URL` SHALL be an absolute `http` or `https` URL with no query or fragment. A trailing slash SHALL be ignored, and startup SHALL fail for any other value.

#### Scenario: Tailscale URL accepted
- **WHEN** `PUBLIC_BASE_URL` is `https://mac-mini.tail1234.ts.net/`
- **THEN** startup succeeds and download links begin with `https://mac-mini.tail1234.ts.net/files/`

#### Scenario: Relative URL rejected
- **WHEN** `PUBLIC_BASE_URL` is `mac-mini:8080`
- **THEN** startup fails with an error naming `PUBLIC_BASE_URL`

### Requirement: Output directory usable at startup
At startup the system SHALL create the output directory if it does not exist, with access limited to the service's user, and SHALL fail to start if the directory cannot be created or written.

#### Scenario: Missing directory created
- **WHEN** `OUTPUT_DIR` points at a path that does not exist yet
- **THEN** the service creates it and starts

#### Scenario: Unwritable directory
- **WHEN** `OUTPUT_DIR` points at a directory the service user cannot write
- **THEN** startup fails with an error naming `OUTPUT_DIR`

### Requirement: Retention covers link lifetime
`OUTPUT_RETENTION_DAYS` SHALL default to 30, SHALL be a positive integer, and SHALL be long enough that no file is deleted while a link to it can still be valid (`OUTPUT_RETENTION_DAYS * 86400 >= SIGNED_URL_TTL_SECONDS`). Startup SHALL fail otherwise.

#### Scenario: Default retention
- **WHEN** `OUTPUT_RETENTION_DAYS` is unset
- **THEN** files are kept for 30 days

#### Scenario: Retention shorter than TTL
- **WHEN** `OUTPUT_RETENTION_DAYS` is 3 and `SIGNED_URL_TTL_SECONDS` is 604800
- **THEN** startup fails with an error naming both variables
