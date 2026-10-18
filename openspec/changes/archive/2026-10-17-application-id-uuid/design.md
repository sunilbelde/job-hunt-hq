# Design

## Context

`ApplicationStore` keeps applications in one SQLite table whose key is `id INTEGER PRIMARY KEY AUTOINCREMENT`. The ID moves through the code as an `int`:

- `app/main.py` parses path IDs with the `APPLICATION_ID` regex and `MAX_APPLICATION_ID`.
- `ResumeRequest.application_id` is a `StrictInt`.
- `StoredApplication.id` is an `int`.
- `LocalStorage.save_resume` writes the integer into the folder name.

The store already has one in-place migration, which adds the `status` and `updated_at` columns under `BEGIN IMMEDIATE` and re-checks the schema first. This change follows the same pattern.

The live store on the Mac mini holds one row (ID 1, Acme Corp), and its resume is at `Acme Corp/1/SUNIL BELDE.pdf`. Only one service instance runs, under launchd.

## Goals / Non-Goals

**Goals:**
- One canonical ID form everywhere: a lowercase, hyphenated UUID string, stored, returned and logged.
- An unattended migration at service start that loses no row, leaves a backup, and survives a crash at any point.

**Non-Goals:**
- Keeping old integer IDs working as aliases. The mapping is kept for the record and for renaming folders, not for lookups.
- Ordering or listing applications. No endpoint lists them, and `created_at` already gives the order.
- Changes to Muse. That's a separate client update.

## Decisions

**UUID v4 generated in Python, stored as TEXT.** `str(uuid.uuid4())` is made in `record()` and inserted as `id TEXT PRIMARY KEY`.
- Alternatives:
  - A 16-byte BLOB: smaller, but unreadable in `sqlite3` and in folder names.
  - UUIDv7: sortable, but it leaks the creation time, which is part of what we want to hide.
- The insert still uses `ON CONFLICT(job_link_key) DO NOTHING` and then selects the ID by key, so duplicate handling and concurrent inserts are unchanged.
- A primary-key collision would raise `IntegrityError` and so a 503. With random v4 UUIDs this can't realistically happen, so it gets no retry logic.

**Strict canonical parsing, not `uuid.UUID()`.** One helper fullmatches `[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}` and lowercases the match. It replaces `APPLICATION_ID`, `MAX_APPLICATION_ID` and `parse_application_id` for the path, and the `POST /resume` body uses it too.
- `uuid.UUID()` also accepts braces, `urn:uuid:` and unhyphenated hex. Those would give the same ID several spellings in logs and paths.
- The version nibble isn't checked. A well-formed non-v4 value simply matches no row, which gives the 404 the spec requires.

**`POST /resume` body.** `ResumeRequest.application_id` becomes `StrictStr`, so a non-string is a 422 from model validation, as now. Parsing the string happens after validation: a string that isn't a UUID is a 404. `request.state.application_id` is set only from a parsed value, so arbitrary client strings never reach a log line. This replaces the old "abs(target) ≤ MAX" guard.

**Integer-to-UUID migration as a table rebuild.** SQLite can't change a primary key's type in place. The migration runs in `ApplicationStore.__init__` after the status migration, and only when `PRAGMA table_info(applications)` reports `id` as `INTEGER`:

1. Back up the store with `sqlite3.Connection.backup()` to `applications.sqlite3.pre-uuid-<UTC timestamp>.bak`. The file is created beforehand with mode 0600, like the store itself. The name starts with `applications.sqlite3`, so the existing company-folder rule (a leading `_`) already keeps a company folder from colliding with it.
2. Run `BEGIN IMMEDIATE`, then re-check the column type, in case another process migrated in the meantime.
3. Create `legacy_application_ids(old_id INTEGER PRIMARY KEY, application_id TEXT NOT NULL UNIQUE)` and fill it with a fresh UUID for each existing `id`.
4. Create `applications_new` with the new schema, then copy every row across with `INSERT … SELECT` joined on the mapping.
5. Run `DROP TABLE applications` and `ALTER TABLE applications_new RENAME TO applications`, then commit.

SQLite DDL is transactional, so any failure rolls everything back and startup fails with the existing "OUTPUT_DIR … application store" error.

- Alternative: add a separate `uuid` column and keep the integer key. That's less work, but leaves two IDs per row and an unused auto-increment counter.
- Alternative: mint UUIDs at read time. That isn't stable.

**Folder renames as a separate, repeatable startup step.** After both the store and storage are built, `create_app` reads the mapping with `ApplicationStore.legacy_ids()` and passes it to a function in `app/storage.py` that:

- scans each real directory (not a symlink) directly inside `OUTPUT_DIR`, and each subfolder named by a positive integer
- skips names that have no mapping
- renames a mapped folder to its UUID with `os.rename`, which is atomic within one filesystem, unless the target already exists
- logs any conflict or `OSError` to `app.storage` and carries on

This runs at every start while the mapping table has rows, which is how an interrupted run finishes. It's cheap: one directory listing per company. It's kept out of the database transaction because a rename can't be rolled back alongside SQL. Doing the rename after the commit means a crash leaves only un-renamed folders, which the next start fixes.

A rename failure doesn't stop the service from starting. The API doesn't depend on old resume folders, and refusing to start over a stray folder would take the whole service down.

## Risks / Trade-offs

- **[Risk] Muse still holds or sends integer IDs after the upgrade.** → Those requests get 404 (path) or 422 (integer in the `/resume` body), never the wrong application. The README states the new contract; update Muse at the same time.
- **[Risk] The migration corrupts or loses rows.** → The backup is taken before any write; the rebuild is a single transaction; tests check that every field, status and timestamp is preserved.
- **[Risk] A folder rename hits a name already in use, or a permission error.** → The folder is left in place and the problem logged. No file is ever deleted.
- **[Trade-off] Random UUIDs make index inserts slightly scattered.** Irrelevant at this store's size.
- **[Trade-off] UUIDs are longer to type in curl examples.** Accepted.

## Migration Plan

1. Pull and reinstall with `scripts/install_service.sh`. The service restarts, migrates the store, writes the `.bak` file, and renames `Acme Corp/1/` to `Acme Corp/<uuid>/`.
2. Check:
   - `sqlite3 applications.sqlite3 "select id, company from applications"` shows a UUID.
   - `select * from legacy_application_ids` shows `1|<uuid>`.
   - The resume folder has been renamed.
3. Update Muse to store and send `application_id` as a string.

**Rollback:**
1. Run `scripts/uninstall_service.sh`.
2. Restore the `.bak` file over `applications.sqlite3` and remove any `-wal` or `-shm` siblings.
3. Rename the UUID folders back using the mapping.
4. Check out the previous commit and reinstall.
