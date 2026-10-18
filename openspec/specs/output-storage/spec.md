# output-storage Specification

## Purpose

Defines how generated files are persisted to Cloudflare R2 and how time-limited download links are issued for them.

## Requirements

### Requirement: Dated unique object keys
The system SHALL store each generated file at key `outputs/{YYYY-MM-DD}/{uuid4}.{extension}`, using the current UTC date and a fresh UUID4 per file, and the key SHALL map to the same relative path under the configured output directory on the local filesystem.

#### Scenario: Key format
- **WHEN** a file with extension `pdf` is stored on 2026-10-08 UTC
- **THEN** its key matches `outputs/2026-10-08/<uuid4>.pdf`
- **AND** the file exists at `<OUTPUT_DIR>/outputs/2026-10-08/<uuid4>.pdf`

#### Scenario: No overwrites
- **WHEN** two files are stored with identical content
- **THEN** they receive distinct keys

### Requirement: Pre-signed download URLs
The system SHALL return, for each stored file, a download link under the configured public base URL that carries an expiry time and a signature, is valid for the configured TTL, and reports the matching expiry time.

#### Scenario: URL validity
- **WHEN** a file is stored with TTL 604800 seconds
- **THEN** the returned URL downloads the file until `expires_at`, roughly seven days after creation

#### Scenario: Expired link
- **WHEN** a link is used after its `expires_at`
- **THEN** the download is refused with 403 and the file content is not returned

#### Scenario: Tampered link
- **WHEN** the key, expiry or signature in a link is altered
- **THEN** the download is refused with 403

#### Scenario: Links survive restart
- **WHEN** the service restarts between issuing a link and its use, with the same signing secret
- **THEN** the link still downloads the file before expiry

### Requirement: Content-Type preserved on download
The system SHALL serve each stored file with the Content-Type supplied by the generator when it is downloaded.

#### Scenario: PDF content type
- **WHEN** a stored resume PDF is downloaded through its signed link
- **THEN** the response has Content-Type `application/pdf`

### Requirement: Private file access
Stored files SHALL be readable over HTTP only through a valid signed link, and the output directory SHALL be readable only by the service's user account.

#### Scenario: Unsigned access
- **WHEN** someone requests a stored file's download path without a signature
- **THEN** access is denied and no file content is returned

#### Scenario: Path traversal
- **WHEN** a download request names a key containing `..`, an absolute path, or any path outside the `outputs/` key format
- **THEN** it is rejected without reading any file, even if its signature is otherwise well-formed

#### Scenario: Directory permissions
- **WHEN** the service creates the output directory
- **THEN** other local user accounts cannot list or read it

### Requirement: Complete files only
A stored file SHALL become visible at its key only once it has been completely written, so a download never returns a partial file.

#### Scenario: Interrupted write
- **WHEN** the service is stopped while writing a file
- **THEN** no partial file exists at that file's key

### Requirement: Retention cleanup
The system SHALL delete stored files older than the configured retention period, at startup and at least hourly while running, and SHALL remove date directories left empty.

#### Scenario: Old file deleted
- **WHEN** retention is 30 days and a stored file was created 31 days ago
- **THEN** after the next cleanup run the file no longer exists

#### Scenario: Recent file kept
- **WHEN** retention is 30 days and a stored file was created 29 days ago
- **THEN** cleanup leaves it in place

#### Scenario: Cleanup failure is non-fatal
- **WHEN** a cleanup run hits an error deleting a file
- **THEN** the error is logged and the service keeps serving requests
