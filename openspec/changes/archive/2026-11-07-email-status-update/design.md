# Design

## Context

- The public listener is guarded by `public_only` in `app/serve.py`. It checks an exact `(method, path)` allowlist, `PUBLIC_ROUTES`, before any routing, so a new public endpoint needs a fixed path with no path parameters.
- Application rows live in SQLite (`app/applications.py`). `ApplicationStore.update` writes fields by ID. `dedupe_key` normalizes job links. `_connect` opens a fresh connection per call with Python's default deferred transactions.
- Keyed handlers in `app/main.py` check the key inline and return `{"ok": false, "message"}` errors. They read bodies by hand and validate them with Pydantic models from `app/models.py`. They are registered in the OpenAPI document via `json_body(...)` and `errors(...)`. The `log_request` middleware already logs every `/application/...` path as `application_request` and adds `request.state.application_id` when set.
- The store holds a few hundred rows at most, so scanning every row in Python is cheap.
- See proposal.md for why, and `specs/email-status-updates/spec.md` for the behavior contract.

## Goals / Non-Goals

**Goals:**
- One narrow, keyed write that n8n can call over Funnel, and that can change nothing but `status`.
- Deterministic matching that never picks among equal candidates.

**Non-Goals:**
- Storing email notes, received times or an email history on the application.
- Matching on anything other than `job_link`, company and role (no sender domain, no recruiter names).
- Moving a status to `offer` or `withdrawn` from email, or adding new status values.
- Changes to the viewer: `interviewing` and `rejected` already display there.

## Decisions

### Path `POST /application/email-status`
The endpoint uses a fixed path so it fits the exact-match allowlist, and sits under `/application` so the existing logging middleware covers it. It is a `POST` rather than a `PATCH` because the client names a match, not a resource. FastAPI also has no route that conflicts with it: `GET /application/{application_id}` is only a `GET`, and `PATCH /application/{id}` is a different method. Alternative considered: `POST /email-status`. Rejected because it would need another `request_event` branch, and `/application/...` keeps it grouped with the other application endpoints.

### `Response` maps to `interviewing`, not a new status
`interviewing` already sits between `applied` and `offer`, and the viewer's status list, the `ApplicationStatus` literal, the docs and every status test already cover it. A new `responded` status would touch all of those. It would also make the owner reclassify most responses by hand anyway, since a response is usually a screen or interview invite. Trade-off: a "please take this assessment" email also becomes `interviewing`. That is acceptable, because the owner can still set any status in the viewer.

### `Applied` never writes
The form filler already marks `applied` on submit, as the user asked. Even a row still at `verified` is not advanced. The response's `changed: false` and `status` let n8n see the discrepancy and flag it. This is the one place where a future change might advance `verified` to `applied`. Doing so needs only a mapping change.

### Forward-only transitions
Status rank: `verified`/`applied` < `interviewing` < `offer`. `rejected` and `withdrawn` are terminal for email updates. `Rejected` sets `rejected` from anything except `withdrawn`, including `offer`, which covers rescinded offers. `Response` moves only `verified` or `applied` to `interviewing`. This keeps the endpoint idempotent and safe against out-of-order email delivery. The concurrent-emails scenario in the spec then holds whatever the order.

### Matching algorithm
A pure function in `app/applications.py`, `match_applications(rows, company, role, job_link)`, keeps the logic unit-testable without HTTP:
1. If `job_link` is a non-empty string and `dedupe_key(job_link)` equals a row's `job_link_key`, return that row alone.
2. Normalize names with `normalize_name(s, kind)`. Apply Unicode NFKD and drop combining marks, then casefold, replace `&` with ` and `, turn every non-alphanumeric run into a single space, and strip. For companies, drop a leading `the` and repeatedly drop trailing tokens in {`inc`, `incorporated`, `llc`, `ltd`, `limited`, `corp`, `corporation`, `co`, `company`, `plc`, `gmbh`, `ag`, `sa`, `bv`, `pbc`}, but never drop the last token. For roles, map the tokens `sr` to `senior` and `jr` to `junior`.
3. Company tier: rows whose normalized company equals the request's. If there are none, use rows whose `difflib.SequenceMatcher` ratio is at least 0.9.
4. Role tier, applied to the company tier the same way: exact first, otherwise ratio ≥ 0.9.
5. Return the resulting list. The handler maps zero rows to 404 `no_match`, one row to an update, and more than one to 409 `ambiguous`.

`difflib` is in the standard library, so no new dependency is needed. Alternative considered: `rapidfuzz` token-set ratio. Rejected, because it adds a dependency and token-set scoring is too lenient: `Applied AI Engineer` would match `Applied AI Engineer, Agents`.

### Atomic match-and-update
`ApplicationStore.apply_email_status(company, role, job_link, email_status)` opens one connection and runs `BEGIN IMMEDIATE` to take SQLite's write lock before reading. It then reads `id, job_link_key, company, role, status`, runs `match_applications` and computes the target status. It updates `status` and `updated_at` only when the status changes, then commits. It returns a small result: `no_match`, `ambiguous(count)` or `updated(row, previous, current, changed)`. Holding the write lock across the read means a concurrent PATCH, delete or second email cannot slip between the match and the write. Alternative considered: read with `list_with_reports`, then call `update`. Rejected, because that is a check-then-act race and violates the spec's concurrency scenario.

### Request and response models
`EmailStatusRequest` (Pydantic, `extra="ignore"`) has these fields:
- `company` and `role` as `StrictStr` with `min_length=1`. Whitespace-only values fail after a strip in a validator.
- `status` as a string, run through a `before` validator that strips and title-cases it before the check against `Literal["Applied", "Rejected", "Response"]`.
- `job_link`, `received_at` and `note` as `StrictStr | None`.

Validation errors go through the existing `validation_message`, which names fields without echoing values. The response models are:
- `EmailStatusUpdated` for 200.
- `EmailStatusNoMatch`, with `ok`, `message` and `reason: Literal["no_match"]`.
- `EmailStatusAmbiguous`, which adds `reason: Literal["ambiguous"]` and `match_count: int`.

All of them join the documented component schemas. The docs test that "every 4xx refers to the `{ok, message}` shape" must accept these supersets. The tasks call out that adjustment.

### Logging
The middleware already logs the endpoint. The handler sets `request.state.application_id` only for a single match. No new `LOGGED_STATE` fields are added, so the email status, company and role never reach the log.

## Risks / Trade-offs

- [A wrong single match at fuzzy 0.9 could mark the wrong application rejected] → Exact matches win over fuzzy ones, the role must match as well as the company, and the response echoes the stored `company`, `role` and `previous_status` so n8n can include them in the forwarded summary and the owner can spot a wrong match.
- [Same role reposted at one company (two rows) always gives 409] → This is intended. n8n flags the email, and sending `job_link` when the email has one resolves it.
- [New public write on the internet] → It sits behind the same API key as the other public `POST`s, can change only `status`, only to `rejected` or `interviewing`, and never backwards. 404 and 409 responses reveal no IDs or fields of other applications.
- [The email classifier sends `Interview` or `Offer`] → It gets 422 naming `status`, and n8n flags the email. Nothing is silently dropped.
- [The `BEGIN IMMEDIATE` lock wait under contention] → `_connect` already has a 5 s timeout. A timeout surfaces as `ApplicationStoreError` → 503, and n8n can retry.

## Migration Plan

1. Merge the change, then run `scripts/install_service.sh` to restart the service with the new `PUBLIC_ROUTES`, followed by `scripts/smoke_test.sh`.
2. In n8n, add an HTTP Request node: `POST https://<mac>.ts.net/application/email-status` with the `X-API-Key` header and a JSON body built from the parsed email fields. Route 404 and 409 responses (and 422) to a "flag email" branch.
3. Rollback: revert the commit and reinstall. The endpoint disappears from the allowlist, no schema or data migration happened, and statuses already written stay valid values.
