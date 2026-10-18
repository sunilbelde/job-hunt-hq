# Proposal

## Why

Application IDs are SQLite's auto-increment integers (1, 2, 3, …). The service is now on the public internet through Tailscale Funnel, and those IDs show anyone how many applications exist and make every other ID easy to guess. The API key still guards every endpoint, but an ID should say nothing about the store. A random UUID gives no count or order and can't be guessed, and Muse can treat it as an opaque handle.

## What Changes

- **BREAKING**: `application_id` becomes a server-generated random UUID (version 4), returned as a lowercase, hyphenated 36-character string, e.g. `"3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"`. This affects:
  - `POST /application` (201 and duplicate 200)
  - `PATCH /application/{application_id}`
  - `DELETE /application/{application_id}`
  - `POST /resume`
- **BREAKING**: `PATCH` and `DELETE /application/{application_id}` take a UUID in the path. Any value that is not a UUID (including an old integer like `1`) responds 404 "Application not found".
- **BREAKING**: the `POST /resume` body takes `{"application_id": "<uuid>"}` as a JSON string:
  - A missing value, or one that isn't a string (including a JSON integer like `7`), gets 422.
  - A string that isn't a UUID, or a UUID that names no row, gets 404.
- UUIDs are matched case-insensitively and always returned in lowercase.
- IDs no longer count up, so there's no ordering guarantee between them. They're still unique, never change once assigned, and are never handed out again.
- Resume files are saved at `<OUTPUT_DIR>/<company folder>/<uuid>/SUNIL BELDE.pdf`.
- **One-time migration at startup.** An existing store with integer IDs is converted in one transaction, so it either completes or leaves the store exactly as it was:
  - The store file is first copied to a private backup next to it.
  - Every row gets a new UUID, and every other field stays the same.
  - The old-to-new ID mapping is kept in the store.
  - Existing resume folders named after an old ID are renamed to the new UUID.

  Old integer IDs stop working once the migration has run. The migration is safe to run again: restarting after a crash part-way through finishes the folder renames, and a store that was already migrated is left alone.
- Log lines carry the UUID string as `application_id`. A path or body value that isn't a UUID is not logged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `application-store`:
  - IDs become random UUIDs instead of increasing integers.
  - Startup adds a migration of integer-ID stores, with a backup and an old-to-new ID mapping.
  - The durable-row wording changes from "integer ID" to "UUID".
- `application-api`:
  - The response shapes carry a UUID string.
  - The path `{application_id}` must be a UUID, and anything else is 404.
  - The logging and delete scenarios change from integer examples to UUID ones.
- `job-api`:
  - The `POST /resume` body takes a UUID string.
  - The response carries the UUID.
  - The unknown-ID rules move from "zero or negative" to "not a UUID".
  - Log scenarios use UUIDs.
- `output-storage`:
  - The resume path uses the UUID as the application folder name.
  - At migration, existing integer-named application folders are renamed to the new UUID.

## Impact

- **Code:**
  - `app/applications.py`: schema, ID generation, migration and mapping table.
  - `app/main.py`: path parsing replaces the `APPLICATION_ID` regex and `MAX_APPLICATION_ID`, plus response and log values.
  - `app/models.py`: `ResumeRequest.application_id` and `StoredApplication.id` become strings.
  - `app/storage.py`: `save_resume` takes a string ID, and a new folder-rename step is added for the migration.
- **Tests:** `tests/test_applications.py`, `tests/test_api.py`, `tests/test_storage.py` and `tests/test_models.py` replace integer-ID cases and gain migration tests.
- **Docs:** README endpoint table and curl examples.
- **Clients:** Muse must store and send the ID as a string. Any integer ID it already holds stops working after the upgrade. The single existing row (application 1, Acme Corp) gets a new UUID, and its resume moves from `Acme Corp/1/` to `Acme Corp/<uuid>/`.
- **Dependencies:** none (uses Python's `uuid` module).
