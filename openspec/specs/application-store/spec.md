# application-store Specification

## Purpose

Defines how recorded job applications are persisted locally: where they live, how IDs are assigned, how uniqueness on the posting link is enforced, and how the data survives restarts and cleanup.

## Requirements

### Requirement: Durable application rows
The system SHALL persist each accepted application, with every recognised body field, a `status`, a creation timestamp (UTC), an `updated_at` timestamp (UTC, null until the row is first updated) and an integer ID, in a single file at `<OUTPUT_DIR>/applications.sqlite3`. A stored row, including any updates, SHALL remain readable after the service restarts.

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

### Requirement: Stable increasing IDs
Application IDs SHALL be positive integers assigned by the store, unique across all rows, never changed once assigned, and never reused for any later row, including after the row holding the ID, or the row with the largest ID, is deleted.

#### Scenario: Distinct postings
- **WHEN** two applications with different `job_link` values are recorded
- **THEN** they receive different positive integer IDs, the later one larger

#### Scenario: No reuse after deleting the newest row
- **WHEN** the row with the largest ID is deleted and a new application is recorded
- **THEN** the new ID is larger than the deleted one

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
The system SHALL create the store file and its schema at startup if absent. If present, it SHALL leave existing rows' values untouched, except that a store created before statuses existed SHALL be migrated so that every existing row has status `verified` and a null `updated_at`. It SHALL refuse to start with an error naming `OUTPUT_DIR` if the store cannot be opened, created or migrated.

#### Scenario: First start
- **WHEN** the service starts with no store file in `OUTPUT_DIR`
- **THEN** the file is created and the service starts

#### Scenario: Unwritable store
- **WHEN** the store file exists but cannot be opened for writing
- **THEN** startup fails with an error naming `OUTPUT_DIR`

#### Scenario: Pre-status store migrated
- **WHEN** the service starts with a store holding rows written before statuses existed
- **THEN** every such row has status `verified`, keeps its ID and every other field, and can be updated and deleted

#### Scenario: Migration is idempotent
- **WHEN** the service is restarted after a migration, or after rows changed status
- **THEN** no status is reset and startup succeeds

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
