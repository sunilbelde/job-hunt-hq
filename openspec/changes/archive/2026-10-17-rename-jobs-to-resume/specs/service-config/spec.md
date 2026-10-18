## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Signed URL TTL bounds
**Reason**: Download links are no longer issued.
**Migration**: Remove `SIGNED_URL_TTL_SECONDS` from `.env`. It is ignored if left in.

### Requirement: Signing secret strength
**Reason**: Download links are no longer signed.
**Migration**: Remove `LINK_SIGNING_SECRET` from `.env`. It is ignored if left in.

### Requirement: Public base URL format
**Reason**: No response contains a URL any more, because `POST /resume` returns a local path.
**Migration**: Remove `PUBLIC_BASE_URL` from `.env`. It is ignored if left in. Funnel exposure is configured in Tailscale and does not depend on it.

### Requirement: Retention covers link lifetime
**Reason**: Retention cleanup and download links are both removed.
**Migration**: Remove `OUTPUT_RETENTION_DAYS` from `.env`. It is ignored if left in.
