# Tasks

## 1. Store: UUID IDs and the integer-ID migration

- [x] 1.1 In `app/applications.py`:
  - Change `SCHEMA` to `id TEXT PRIMARY KEY`.
  - Make `record()` generate `str(uuid.uuid4())` and insert it, keeping `ON CONFLICT(job_link_key) DO NOTHING` and the select-by-key.
  - Change the type hints on `record`, `update`, `delete`, `exists` and `get` from `int` to `str`.

  Verify with `tests/test_applications.py`:
  - new IDs match the lowercase v4 pattern
  - two postings get distinct IDs
  - delete then re-record gives a different ID
  - the concurrent-insert test still yields one row and one shared ID
  - the integer-ordering assertions are removed
- [x] 1.2 Add the integer-ID migration to `ApplicationStore.__init__`, run after the status migration (design, "Integer-to-UUID migration"):
  - detect it with `PRAGMA table_info`
  - take a 0600 `applications.sqlite3.pre-uuid-<timestamp>.bak` backup with `Connection.backup()`
  - under `BEGIN IMMEDIATE`, re-check the schema, then fill `legacy_application_ids`, rebuild the table, drop the old one and rename the new one
  - add `legacy_ids() -> dict[int, str]`

  Verify with new tests that build an old-format store by hand, including a pre-status store:
  - every field, status, `created_at` and `updated_at` is kept
  - IDs become distinct UUIDs and the mapping matches
  - the backup exists with mode 0600 and still holds the integer rows
  - a restart changes nothing and makes no second backup
  - a failure injected mid-rebuild leaves the integer table intact and raises `StorageError` naming `OUTPUT_DIR`
  - after migration, `get(1)` and `get("1")` return `None`

## 2. Storage: UUID folders and the legacy rename

- [x] 2.1 In `app/storage.py`, change `save_resume` (and the `Storage` protocol) to take `application_id: str`. Verify that `tests/test_storage.py` cases use a UUID and that the path is `<root>/Acme Corp/<uuid>/SUNIL BELDE.pdf`.
- [x] 2.2 Add `rename_legacy_folders(root, mapping)` to `app/storage.py` (design, "Folder renames"):
  - for each real company directory, rename integer-named subfolders that have a mapping to their UUID with `os.rename`
  - skip symlinks, unmapped integers and existing targets, logging any conflict or `OSError` to `app.storage` without raising

  Verify with tests for:
  - a single move, with the file content intact
  - the same ID under two company folders
  - an unmapped folder left alone
  - a target that already exists (both kept, and a log line)
  - a second call that changes nothing
  - a symlinked company folder that is not followed

## 3. API: UUID parsing, bodies, responses and logs

- [x] 3.1 In `app/models.py`, change `ResumeRequest.application_id` to `StrictStr` and `StoredApplication.id` to `str`. Verify that `tests/test_models.py` accepts a string and rejects `7`, `7.5`, `true`, `null`, an object and a missing ID with errors naming `application_id`.
- [x] 3.2 In `app/main.py`:
  - replace `APPLICATION_ID`, `MAX_APPLICATION_ID` and `parse_application_id` with a canonical-UUID helper that matches any case and returns the ID in lowercase
  - use it for the `PATCH` and `DELETE` paths and for the `POST /resume` body
  - set `request.state.application_id` only from a parsed value
  - in `create_app`, call `rename_legacy_folders(settings.output_dir, applications.legacy_ids())` at startup

  Verify with `tests/test_api.py`:
  - `POST /application` returns a UUID string
  - `PATCH`/`DELETE` work with that ID, and with it in upper case (the response comes back in lower case)
  - `abc`, `1`, `0`, `-1` and a random UUID get 404 and change nothing
  - `POST /resume` with the UUID returns 201 and `saved_path` ending in `/<uuid>/SUNIL BELDE.pdf`
  - `{"application_id": 7}` gets 422, and `"7"` or `"not-a-uuid"` gets 404
  - the log lines carry the lowercase UUID, and never `not-a-uuid`
  - the auth-before-404 tests still pass
- [x] 3.3 Run the full test suite (`.venv/bin/pytest -q`) and `scripts/test_install_service.sh`. Verify that both pass.

## 4. Documentation

- [x] 4.1 Update `README.md`:
  - the endpoint table and the `POST /resume` body paragraph: UUID string; integer is a 422; non-UUID or unknown is a 404
  - the curl examples: use `$ID` from the `POST /application` response
  - a short "Upgrading from integer IDs" note covering the backup file, the `legacy_application_ids` table, folder renames, rollback steps, and the need to update Muse

  Verify that the curl sequence runs as written against a local `uvicorn`.

## 5. Integration on the Mac mini

- [ ] 5.1 Reinstall with `scripts/install_service.sh` against the live store. Verify:
  - application 1 now has a UUID and `legacy_application_ids` shows `1|<uuid>`
  - a `.bak` file exists with mode 600
  - `Acme Corp/1/` is now `Acme Corp/<uuid>/` with the PDF inside
  - `POST /resume` with the new UUID returns 201
  - `PATCH /application/1` returns 404
  - `scripts/service_status.sh` reports healthy

## Workflow follow-up

- Update Muse to store and send `application_id` as a string.
- Archive the change with `/opsx:archive` once task 5.1 is confirmed.
