# Design

## Context

- `app/applications.py` owns the SQLite store.
  - `ApplicationStore.__init__` runs `CREATE TABLE IF NOT EXISTS` and a write probe. `record()` opens a per-call connection (`timeout=5`) and does `INSERT ... ON CONFLICT(job_link_key) DO NOTHING`.
  - The table already uses `INTEGER PRIMARY KEY AUTOINCREMENT`, so SQLite never hands out a deleted ID again, including the largest one.
- `app/main.py` defines `POST /application` inline.
  - It checks the key with `api_key_valid`, not the `require_api_key` dependency, so that errors keep the `{"ok": false, "message"}` shape.
  - It builds 422 messages with `validation_message()`, which never includes input values.
- The log middleware chooses its event with `REQUEST_EVENTS.get(request.url.path)`, an exact-path lookup. `/application/7` would currently produce no log line at all.
- `ApplicationRow` in `app/models.py` validates `POST` bodies. Its after-validator ties `official_apply_url` to `job_link`, which is part of why those fields are immutable (see proposal).

## Goals / Non-Goals

**Goals:**
- Add update and delete with the same error envelope, auth order and logging as `POST /application`.
- An in-place, additive migration with no separate script or manual step.

**Non-Goals:**
- Reading rows back (`GET`), listing, or status history.
- Optimistic concurrency, soft delete, and undo.
- Changing the `POST` request, response or dedupe behaviour.

## Decisions

### D1. Status lives in a column on the existing table, migrated at open
`__init__` runs `PRAGMA table_info(applications)` after `CREATE TABLE IF NOT EXISTS`. If `status` is missing, it runs this in one transaction:
- `ALTER TABLE applications ADD COLUMN status TEXT NOT NULL DEFAULT 'verified'`
- `ALTER TABLE applications ADD COLUMN updated_at TEXT`

The `SCHEMA` for new files declares both columns, with the same `DEFAULT 'verified'`. SQLite fills existing rows with the default on `ADD COLUMN`, so no `UPDATE` pass is needed. A migration failure is wrapped in `StorageError` naming `OUTPUT_DIR`, like the write probe.

*Alternatives:*
- A separate `application_status` table with history. Rejected as scope creep; that would be a later change.
- `PRAGMA user_version` migrations. This is the first schema change, so checking for the column is enough. Adopt `user_version` when a second migration arrives.

*Concurrency:* the migration is guarded by `BEGIN IMMEDIATE` and re-checks the column inside the transaction, so two instances starting together (as tests do) cannot both add it.

### D2. Status values are validated in the model, not by a CHECK constraint
`ApplicationStatus = Literal["verified", "applied", "interviewing", "offer", "rejected", "withdrawn"]` is defined in `app/models.py` and is the single source. A SQL `CHECK` would duplicate the list. Changing it later would also mean rebuilding the table, because SQLite cannot alter constraints. Only the service writes to the file.

### D3. `ApplicationUpdate` model with `exclude_unset` for partial semantics
`ApplicationUpdate` is a new Pydantic model with `extra="ignore"`.
- Field types:
  - `status: ApplicationStatus`
  - `company` and `role`: `StrictStr` with `min_length=1`
  - the nine optional fields: `StrictStr | None`
- Every field defaults to a private sentinel, so that "absent" differs from "null". `model_dump(exclude_unset=True)` then gives exactly the fields to write. `status`, `company` and `role` reject an explicit `null` through their type.
- A `model_validator(mode="before")` rejects any of `IMMUTABLE_FIELDS = ("job_link", "posting_source_type", "verification_method", "official_apply_url")`. It runs before `extra="ignore"` drops them, and its message names only the fields.
- An after-check rejects an empty set of updatable fields with "Request body has no updatable fields".

*Alternative:* reusing `ApplicationRow` with every field optional. Rejected because its pairing validator and required fields do not apply to a partial update.

### D4. Store methods: `update(id, changes) -> str | None` and `delete(id) -> bool`
- **`update`** does `UPDATE applications SET <cols>=?, ..., updated_at=? WHERE id=? RETURNING status` in one statement. It returns the new status, or `None` when no row matched.
  - The column names come only from the model's known field names, never from client input, so building the SQL with f-strings is safe.
  - One statement is atomic. SQLite serialises writers (`timeout=5`), so concurrent updates apply whole and the last one wins per column.
- **`delete`** does `DELETE FROM applications WHERE id=?` and returns `rowcount == 1`.
- Both wrap `sqlite3.Error` in `ApplicationStoreError`. `RETURNING` needs SQLite 3.35 or later. macOS's Python ships 3.43 or later. The baseline task checks `sqlite3.sqlite_version`.
- **`exists(id) -> bool`** is used only to order 404 before 422 (D5).

### D5. Route order: auth → ID → body → store
- Both routes take `application_id` as a `str` path parameter and parse it with `parse_application_id()`, which matches `^[1-9][0-9]*$` and caps the value at SQLite's int64 range. Anything else is a 404. A typed `int` parameter would let FastAPI return its own 422 `{"detail": ...}` shape, which breaks the error envelope.
- `PATCH` order:
  1. Key check → 401.
  2. ID parse → 404.
  3. Body JSON/object/validation → 422. Before returning a 422, the route calls `exists(id)` and returns 404 instead when the row is missing (spec "Unknown ID with bad body").
  4. `update()` → `None` → 404, which covers a row deleted between steps.
  5. 200.
- `DELETE`: key check → ID parse → `delete()` → 200 or 404. The body is never read.
- Store calls go through `run_in_threadpool`, as in `record`.

*Alternative:* 422 before 404, which is simpler with no extra read. Rejected because a client fixing its body would then just get a 404, and the spec chose 404-first.

### D6. Log middleware matches by prefix and records the method
- `REQUEST_EVENTS` lookup becomes a small function. It returns `job_request` for `/jobs`, and `application_request` for `/application` or any path starting with `/application/`.
- Application lines gain `"method": request.method`.
- Routes set `request.state.application_id` once the ID parses, so 404s for well-formed IDs log the ID too. `duplicate` stays `POST`-only.
- Nothing from the body is logged, including the new status (spec).
- The `job_request` line is unchanged.

### D7. Hard delete with AUTOINCREMENT, no secure-delete pragma
Deleting frees the `job_link_key` UNIQUE slot, so the next `POST` inserts a fresh row. `AUTOINCREMENT`'s `sqlite_sequence` keeps IDs increasing across deletes.

SQLite may leave deleted bytes in free pages until they are reused or the file is vacuumed. That is acceptable, because the file is mode 0600 and on the user's own machine. `PRAGMA secure_delete` was considered and left out to keep writes cheap. It could be revisited if the data's sensitivity changes.

## Risks / Trade-offs

- [The migration is one-way and runs on the first start of the new build] → The README says to take a `.backup` before deploying. The added columns are ignored by the old build, so a rollback needs no schema revert.
- [A leaked key can now destroy data, not only add it] → The same single-key model as before, and still behind Funnel. Recorded as a follow-up alongside rate limiting. Backups are the recovery path.
- [Rejecting immutable fields breaks a client that echoes the full row back] → A clear 422 naming the fields. This is listed as an open question in the proposal.
- [The 404-before-422 ordering costs an extra `exists` read on invalid bodies only] → Negligible. The valid path does a single `UPDATE`.
- [The middleware's prefix match could catch future `/application/...` routes] → Intended: they belong to the same event.

## Migration Plan

1. Back up: `sqlite3 "$OUTPUT_DIR/applications.sqlite3" ".backup applications-pre-status.sqlite3"`.
2. Deploy with `scripts/install_service.sh`. The first start adds `status` and `updated_at`, and existing rows read `verified`.
3. Smoke test through the Funnel URL:
   - `PATCH /application/<known id>` with `{"status": "verified"}` → 200.
   - A `PATCH` without a key → 401.
4. Rollback: reinstall the previous build. It ignores the extra columns. Restore the backup only if rows must lose their statuses.
