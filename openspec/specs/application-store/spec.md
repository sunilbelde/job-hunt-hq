# application-store Specification

## Purpose

Defines how recorded job applications are persisted locally: where they live, how IDs are assigned, how uniqueness on the posting link is enforced, and how the data survives restarts and cleanup.

## Requirements

### Requirement: Durable application rows
The system SHALL persist each accepted application, with every recognised body field, a `status`, a creation timestamp (UTC), an `updated_at` timestamp (UTC, null until the row is first updated) and a UUID application ID, in a single file at `<OUTPUT_DIR>/applications.sqlite3`. A stored row, including any updates, SHALL remain readable after the service restarts.

#### Scenario: Survives restart
- **WHEN** an application is recorded and the service is then restarted
- **THEN** posting the same `job_link` again returns the original `application_id`

#### Scenario: Fields stored as sent
- **WHEN** an application is recorded with `official_apply_url` ""
- **THEN** the stored row's `official_apply_url` is "" and omitted optional fields are stored as null

#### Scenario: Update survives restart
- **WHEN** an application's status is updated to `offer` and the service is then restarted
- **THEN** the stored status is still `offer`

#### Scenario: Update timestamp
- **WHEN** a row is created and later updated
- **THEN** its `updated_at` is null after creation and a UTC timestamp no earlier than `created_at` after the update, and `created_at` is unchanged

### Requirement: Random application IDs
Each application ID SHALL be a random (version 4) UUID assigned by the store when the row is created, and SHALL be reported as a lowercase, hyphenated 36-character string. IDs SHALL be unique across all rows, SHALL never change once assigned, and SHALL NOT be derivable from the posting, the row count or the order of recording.

#### Scenario: Distinct postings
- **WHEN** two applications with different `job_link` values are recorded
- **THEN** they receive different IDs, each matching `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`

#### Scenario: New ID after delete
- **WHEN** a row is deleted and an application with the same `job_link` is recorded again
- **THEN** the new row's ID differs from the deleted one

#### Scenario: ID is stable
- **WHEN** a row is updated and the service is restarted
- **THEN** the row keeps the ID it was given when it was recorded

### Requirement: Uniqueness on job_link
The store SHALL hold at most one row per `job_link` dedupe key, and SHALL enforce this itself so that concurrent writers cannot create a duplicate. Each row SHALL keep both the key and the `job_link` exactly as first sent, so keys can be rebuilt if the normalization rules change. Deleting a row SHALL free its key.

#### Scenario: Concurrent inserts
- **WHEN** several threads record the same new `job_link` at once
- **THEN** exactly one row exists and every caller gets its ID

#### Scenario: Raw link retained
- **WHEN** a row is recorded from `https://example.com/jobs/1/?utm_source=x`
- **THEN** the row's `job_link` is exactly that value and its key is `https://example.com/jobs/1`

#### Scenario: Key freed by delete
- **WHEN** a row is deleted and a decorated variant of its `job_link` is recorded
- **THEN** a new row is created and its `job_link` is the decorated variant as sent

### Requirement: Store initialisation
The system SHALL create the store file and its schema at startup if absent. If present, it SHALL leave existing rows' values untouched, except that a store created before statuses existed SHALL be migrated so that every existing row has status `verified` and a null `updated_at`, and a store with integer IDs SHALL be migrated to UUID IDs. It SHALL refuse to start with an error naming `OUTPUT_DIR` if the store cannot be opened, created or migrated.

#### Scenario: First start
- **WHEN** the service starts with no store file in `OUTPUT_DIR`
- **THEN** the file is created and the service starts

#### Scenario: Unwritable store
- **WHEN** the store file exists but cannot be opened for writing
- **THEN** startup fails with an error naming `OUTPUT_DIR`

#### Scenario: Pre-status store migrated
- **WHEN** the service starts with a store holding rows written before statuses existed
- **THEN** every such row has status `verified`, has a UUID ID, keeps every other field, and can be updated and deleted

#### Scenario: Migration is idempotent
- **WHEN** the service is restarted after a migration, or after rows changed status
- **THEN** no status is reset, no ID changes, and startup succeeds

### Requirement: Integer ID migration
At startup, a store whose rows have integer IDs SHALL be converted so that each row gets a new random UUID ID and keeps every other field. Before converting, the system SHALL copy the store file to a backup in `OUTPUT_DIR` readable only by the service's user account. The conversion SHALL happen in one transaction and SHALL record each old integer ID with its new UUID in the store. Old integer IDs SHALL NOT identify any application afterwards.

#### Scenario: Rows converted
- **WHEN** the service starts with a store holding rows 1 and 2
- **THEN** both rows have distinct UUID IDs, and their `job_link`, fields, `status`, `created_at` and `updated_at` are unchanged

#### Scenario: Backup kept
- **WHEN** an integer-ID store is migrated
- **THEN** a copy of the store as it was before the migration exists in `OUTPUT_DIR`, and its mode grants no access to group or other users

#### Scenario: Mapping recorded
- **WHEN** row 1 is migrated
- **THEN** the store records that old ID 1 became the row's new UUID

#### Scenario: Failed migration leaves store unchanged
- **WHEN** the migration fails partway through
- **THEN** the store still holds every row with its integer ID, and startup fails with an error naming `OUTPUT_DIR`

#### Scenario: Already migrated
- **WHEN** the service restarts after a completed migration
- **THEN** no ID changes and no new backup is made

#### Scenario: Old ID rejected
- **WHEN** a client uses integer ID 1 after the migration
- **THEN** the request is handled as an unknown application

### Requirement: Private application data
The store file SHALL be readable and writable only by the service's user account.

#### Scenario: File permissions
- **WHEN** the service creates the store file
- **THEN** its mode grants no access to group or other users

### Requirement: Atomic row updates
An update SHALL apply all of its field changes to one row in a single transaction, so the row reflects either all of the changes or none of them. Concurrent updates to the same row SHALL each apply whole, with the later one winning field by field.

#### Scenario: Concurrent updates
- **WHEN** two updates to the same row, one setting `salary` and one setting `status`, run at the same time
- **THEN** both changes are present afterwards and no update fails because of the other

### Requirement: Hard delete
Deleting an application SHALL remove its row and all its stored fields from the store. No row, tombstone or history of the posting SHALL remain, so the deletion cannot be undone through the service.

#### Scenario: Row gone
- **WHEN** a row is deleted
- **THEN** the store holds no row with that ID or that `job_link` dedupe key

### Requirement: One generation report per application
The store SHALL hold at most one generation report per application, in the same private SQLite file as the applications, created on startup in a store that lacks it without changing any application row.

#### Scenario: Existing store upgraded
- **WHEN** the service starts against a store created before reports existed
- **THEN** it starts normally, every application row is unchanged, and no application has a report

#### Scenario: Regenerated
- **WHEN** a report is stored for an application that already has one
- **THEN** only the new report remains for it

### Requirement: Report removed with its application
Deleting an application SHALL also delete its report, in the same transaction, so no report remains for an ID that no longer names an application.

#### Scenario: Application deleted
- **WHEN** an application with a report is deleted
- **THEN** the store holds no report for its ID, and its saved resume file is kept

### Requirement: Report kept across application updates
Updating an application's fields SHALL NOT change or remove its report.

#### Scenario: Company renamed
- **WHEN** an application with a report has its company changed
- **THEN** its report, including the saved path, is unchanged
