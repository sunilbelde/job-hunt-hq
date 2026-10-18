# Proposal

## Why

Muse, the external client that already calls `POST /jobs` through the public Funnel URL, finds job postings and checks that they are genuine before the user applies. It needs somewhere to record each verified posting, and it needs a stable ID back for each one. The service stores nothing about postings today: `POST /jobs` renders a PDF and forgets the request. Muse also re-sends postings it has seen before, so recording has to be idempotent on the posting's link.

## What Changes

- New authenticated endpoint `POST /application` (path as given in the client's example request). It takes a JSON body with the same snake_case fields as `POST /jobs`, plus five verification fields: `company_careers_url`, `official_employer_domain`, `posting_source_type`, `verification_method` and `official_apply_url`.
- `posting_source_type` is limited to `recruiting_platform` or `employer_site`. `verification_method` is limited to `official_apply_match` or `employer_site`. `official_apply_url` must be the empty string when `posting_source_type` is `employer_site`.
- `job_link` is required. Dedupe uses a normalized form of it: the scheme and host are lowercased, the fragment, trailing slashes and known tracking parameters are dropped, and the remaining query parameters are kept. If a row with the same normalized link already exists, the endpoint returns that row's ID and creates no new row. `job_link` is stored exactly as sent.
- When `verification_method` is `official_apply_match`, `official_apply_url` must equal `job_link` byte-for-byte.
- A successful response is `{"ok": true, "application_id": <int>}`. `application_id` is the local store's row ID, or the existing row's ID on a duplicate.
- Error responses from this endpoint are `{"ok": false, "message": "<text>"}` with a 4xx status for validation failures. The message names fields but never echoes submitted values.
- New local application store: a SQLite file in `OUTPUT_DIR`. It is not subject to the output retention cleanup, and it survives restarts and reinstalls.
- No `found` flag. Muse only sends verified postings, so the service treats every accepted row as verified.
- `POST /jobs` is not changed.

### Client decisions

The client reviewed the fields inferred from their example and from `POST /jobs` / `JobRow`. Their answers:

1. **Required vs optional — confirmed.** Required: `company`, `role`, `job_link`, `posting_source_type`, `verification_method` and `official_apply_url` (the key must be present, though it may be `""`). Every other field, including `full_job_description`, is an optional string. The client always sends the description, because its fetch workflow drops postings without one. On the rare row that lacks it, the client's resume flow has to handle the 422 from `/jobs`. This service does not link the two endpoints.
2. **Source type and method pairing — confirmed.** Only `recruiting_platform` + `official_apply_match` and `employer_site` + `employer_site` are valid. Any other combination is rejected with 422.
3. **Apply URL equality — changed.** The meaning of `official_apply_match` is that `official_apply_url` equals `job_link` byte-for-byte, so the server enforces that with a 422. Without the check, a mismatched pair would be stored as verified.
4. **Status codes — confirmed.** 201 for a new row and 200 for a duplicate, with the same body. The client treats 200 as "already tracked".
5. **Duplicates never update — confirmed for now.** A refetched posting whose salary or description changed leaves the row stale. An update path can be added later.
6. **Path — confirmed.** `/application`, exactly as sent, with no alias.
7. **`job_link` matching — changed.** Exact matching would duplicate ATS links that appear with and without a trailing slash or with tracking parameters (`?gh_src=`, `?utm_source=`). The server normalizes the link for the dedupe check only and stores it as sent. The client asked for the whole query string to be stripped. That would merge different postings whose job ID is itself a query parameter, such as `?gh_jid=`, `?token=` or `?jobId=`, which is common on employer-hosted careers pages. So only known tracking parameters are stripped.
8. **401 envelope — confirmed.** A bad key on this endpoint returns `{"ok": false, "message": ...}`.

## Capabilities

### New Capabilities
- `application-api`: The HTTP contract for recording verified job applications: auth, body fields and their rules, dedupe semantics, response and error shapes, and request logging.
- `application-store`: Durable local persistence of application rows. Covers ID assignment, uniqueness on the normalized `job_link`, location, permissions, and behaviour across restarts and retention cleanup.

### Modified Capabilities
<!-- None. POST /jobs, output storage, config and hosting requirements are unchanged; the store lives in the existing OUTPUT_DIR and needs no new setting. -->

## Impact

- **Code:** `app/main.py` (new route, its error handling and log middleware), `app/models.py` (new `ApplicationRow` model), new `app/applications.py` (SQLite store and link normalization), and wiring in `create_app`.
- **Tests:** new `tests/test_applications.py` (store) and API tests for the new route. A fixture provides a temporary store.
- **Dependencies:** none new. The store uses the standard-library `sqlite3`.
- **Data:** new file `<OUTPUT_DIR>/applications.sqlite3`, mode `0600`, in the directory that already has mode `0700`. It contains posting text, so it carries the same sensitivity as the generated outputs.
- **Exposure:** the endpoint is reachable from the public internet through Tailscale Funnel. The API key is its only guard, and there is no rate limiting. That is the same exposure as `/jobs`, but this endpoint writes durable rows, so a leaked key could fill the disk. Rate limiting and a body-size cap remain follow-ups.
- **Docs:** README endpoint table and request-body section.
