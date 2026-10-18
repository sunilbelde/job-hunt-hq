# Proposal

## Why

`POST /application` records a verified posting and returns its ID, but nothing after that. Once a posting is recorded the client has no way to say the user applied, got an interview or was rejected. It cannot correct a stale salary or description, which the duplicate rule deliberately never overwrites. It also cannot remove a row recorded by mistake. The earlier proposal deferred this as "an update path can be added later". Tracking progress also needs a status on each row, and rows have none today.

## What Changes

- **Application status.** Each row gets a `status`, one of `verified`, `applied`, `interviewing`, `offer`, `rejected` or `withdrawn`. Matching is exact and case-sensitive, like the existing enums.
  - New rows from `POST /application` start as `verified`, because Muse only records verified postings, before the user applies.
  - Existing rows are migrated to `verified` when the store opens.
  - A duplicate `POST` still never changes the row, so it never changes the status either.
- **`PATCH /application/{application_id}`**: a partial update. It changes only the fields present in the body.
  - Updatable: `status`, `company` and `role` (non-empty strings), and the optional strings `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain` and `full_job_description`. An optional field can be cleared with `null`.
  - Status is changed by sending `{"status": "<value>"}`. Any status may move to any other status, and setting the current status again is allowed.
  - Immutable: `job_link` (the dedupe key), `posting_source_type`, `verification_method` and `official_apply_url`. These four make up the verification record, and the pairing rules tie them to `job_link`. A body that includes any of them is rejected with 422 naming the field. Unknown fields are ignored, as on `POST`.
  - A body with no updatable field is rejected with 422.
  - Success is 200 `{"ok": true, "application_id": <int>, "status": "<current status>"}`.
  - Each successful update sets an `updated_at` timestamp (UTC) on the row.
- **`DELETE /application/{application_id}`**: a **hard** delete. The row is removed and its `job_link` is free again, so a later `POST` of the same link creates a new row with a new, larger ID. IDs are never reused. Success is 200 `{"ok": true, "application_id": <int>}`. "Not pursuing" is expressed with `status: withdrawn`, not by deleting.
- **Unknown application_id.** `PATCH` or `DELETE` on an ID that does not exist (never created, already deleted, not a positive integer) returns 404 `{"ok": false, "message": "Application not found"}`. Deleting the same ID twice therefore returns 200 and then 404.
- **Shared conventions** for both new endpoints:
  - The `X-API-Key` check runs first and returns 401 before the ID is looked up or the body is read, so a caller without the key cannot probe which IDs exist.
  - All errors are `{"ok": false, "message"}`. 422 messages name fields and never echo values. Store failures return 503 with a generic message.
  - snake_case field names throughout.
  - Exactly one `application_request` log line per request. Every application log line, including `POST`, gains a `method` field.
- `POST /application`'s request, responses and dedupe behaviour are unchanged, and so is `POST /jobs`. The `POST` response does not gain a `status` key.

### Open questions (assumed for now)

1. **Status vocabulary and default.** I chose six values with `verified` as the default, to mean "recorded, not yet applied". The client may want different names, such as `saved`, `to_apply` or `ghosted`, or a separate `closed` for postings taken down.
2. **Free transitions.** There is no state machine, so `rejected` can go back to `applied`. A stricter graph would reject impossible moves but also block corrections.
3. **PATCH, not PUT.** A partial update means the client never has to resend `full_job_description` just to change the status. I chose not to add a status-only endpoint such as `POST /application/{id}/status`.
4. **Immutable fields are rejected, not ignored.** If the client sends back the full row it read, the update fails until it strips those four fields. The alternative is to accept them when they equal the stored value. That is friendlier, but it needs a read-compare and the rule is fuzzier.
5. **Hard delete.** This is simple, it drops the private data, and it frees the link for re-recording. The cost is that there is no undo and no record that the posting was ever seen, so Muse could re-record a posting the user deleted on purpose. A soft delete (a `deleted_at` column, with `POST` returning 410 or the old ID) would keep that history.
6. **Minimal responses.** `PATCH` returns the ID and status only, not the full row. There is no `GET /application/{id}` or list endpoint yet. Those would be a separate change if the client needs to read rows back.
7. **DELETE is not idempotent.** A repeat delete returns 404 rather than 200 or 204, so the client can tell "deleted now" from "already gone".
8. **Last write wins.** Concurrent `PATCH`es to one row are not detected. There is no ETag or version check.
9. **Path shape.** The new endpoints use the singular `/application/{application_id}` to match `POST /application`. The client's own path preference is unconfirmed.

## Capabilities

### New Capabilities
<!-- None. The new endpoints extend the existing application HTTP contract and store. -->

### Modified Capabilities
- `application-api`: adds the update and delete endpoints, their field rules, responses and 404 handling, and the status values. Extends auth, store-failure handling and request logging to all application endpoints. Recording now sets the default status.
- `application-store`: rows gain `status` and `updated_at`. Initialisation migrates existing rows to `verified`. Rows can be updated in place and hard-deleted, and IDs stay unique across deletions.

## Impact

- **Code:**
  - `app/models.py`: an `ApplicationStatus` literal and an `ApplicationUpdate` model.
  - `app/applications.py`: schema migration, plus the `update()` and `delete()` methods.
  - `app/main.py`: two routes and an application-ID path parser. The log middleware must also match `/application/{id}`, because today it matches exact paths only.
- **Tests:** `tests/test_applications.py`, `tests/test_models.py` and `tests/test_api.py`.
- **Data:** a one-way, additive migration of `applications.sqlite3`, which adds two columns. Back up the store before deploying. An older build still runs against the migrated file, because it ignores the extra columns.
- **Exposure:** a leaked API key can now also delete or alter recorded applications, not only add them. Rate limiting and a body-size cap remain follow-ups.
- **Docs:** the README endpoint table, the status values, and curl examples for `PATCH` and `DELETE`.
