# Spec Delta

## Purpose

Defines how recorded job applications are persisted locally: where they live, how IDs are assigned, how uniqueness on the posting link is enforced, and how the data survives restarts and cleanup.

## ADDED Requirements

### Requirement: Durable application rows
The system SHALL persist each accepted application, with every recognised body field, a creation timestamp (UTC) and an integer ID, in a single file at `<OUTPUT_DIR>/applications.sqlite3`. A stored row SHALL remain readable after the service restarts.

#### Scenario: Survives restart
- **WHEN** an application is recorded and the service is then restarted
- **THEN** posting the same `job_link` again returns the original `application_id`

#### Scenario: Fields stored as sent
- **WHEN** an application is recorded with `official_apply_url` ""
- **THEN** the stored row's `official_apply_url` is "" and omitted optional fields are stored as null

### Requirement: Stable increasing IDs
Application IDs SHALL be positive integers assigned by the store, unique across all rows, never reused for a different `job_link`, and never changed once assigned.

#### Scenario: Distinct postings
- **WHEN** two applications with different `job_link` values are recorded
- **THEN** they receive different positive integer IDs, the later one larger

### Requirement: Uniqueness on job_link
The store SHALL hold at most one row per `job_link` dedupe key, and SHALL enforce this itself so that concurrent writers cannot create a duplicate. Each row SHALL keep both the key and the `job_link` exactly as first sent, so keys can be rebuilt if the normalization rules change.

#### Scenario: Concurrent inserts
- **WHEN** several threads record the same new `job_link` at once
- **THEN** exactly one row exists and every caller gets its ID

#### Scenario: Raw link retained
- **WHEN** a row is recorded from `https://example.com/jobs/1/?utm_source=x`
- **THEN** the row's `job_link` is exactly that value and its key is `https://example.com/jobs/1`

### Requirement: Store initialisation
The system SHALL create the store file and its schema at startup if absent, SHALL leave existing rows untouched if present, and SHALL refuse to start with an error naming `OUTPUT_DIR` if the store cannot be opened or created.

#### Scenario: First start
- **WHEN** the service starts with no store file in `OUTPUT_DIR`
- **THEN** the file is created and the service starts

#### Scenario: Unwritable store
- **WHEN** the store file exists but cannot be opened for writing
- **THEN** startup fails with an error naming `OUTPUT_DIR`

### Requirement: Private application data
The store file SHALL be readable and writable only by the service's user account.

#### Scenario: File permissions
- **WHEN** the service creates the store file
- **THEN** its mode grants no access to group or other users

### Requirement: Excluded from output retention
Retention cleanup of generated files SHALL NOT delete or modify the application store, regardless of its age.

#### Scenario: Old store kept
- **WHEN** retention is 30 days and the store file was last modified 31 days ago
- **THEN** after a cleanup run the store file and all its rows still exist
