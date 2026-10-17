# output-storage Specification

## Purpose

Defines how generated files are persisted to Cloudflare R2 and how time-limited download links are issued for them.

## Requirements

### Requirement: Dated unique object keys
The system SHALL store each generated file at key `outputs/{YYYY-MM-DD}/{uuid4}.{extension}`, using the current UTC date and a fresh UUID4 per file.

#### Scenario: Key format
- **WHEN** a file with extension `json` is stored on 2026-10-08 UTC
- **THEN** its key matches `outputs/2026-10-08/<uuid4>.json`

#### Scenario: No overwrites
- **WHEN** two files are stored with identical content
- **THEN** they receive distinct keys

### Requirement: Content-Type preserved on upload
The system SHALL upload each file with the Content-Type supplied by the generator.

#### Scenario: JSON content type
- **WHEN** the stub output is uploaded
- **THEN** the R2 object has Content-Type `application/json`

### Requirement: Pre-signed download URLs
The system SHALL return a pre-signed GET URL for the stored object that is valid for the configured TTL and reports the matching expiry time.

#### Scenario: URL validity
- **WHEN** a file is stored with TTL 604800 seconds
- **THEN** the returned URL downloads the file until `expires_at`, roughly seven days after creation

### Requirement: Private bucket access
The system SHALL expose stored files only through pre-signed URLs and SHALL NOT make objects publicly readable.

#### Scenario: Unsigned access
- **WHEN** someone requests the object's R2 endpoint URL without a signature
- **THEN** access is denied
