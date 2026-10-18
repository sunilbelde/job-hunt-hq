## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Stable increasing IDs
**Reason**: IDs are now random UUIDs, so they no longer increase and say nothing about how many applications exist or in what order they were recorded.
**Migration**: Replaced by "Random application IDs". Clients must treat `application_id` as an opaque string. Order applications by `created_at` where order matters.

## ADDED Requirements

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
