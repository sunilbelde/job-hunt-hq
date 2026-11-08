# Proposal

## Why

The owner's n8n workflow classifies job emails (Applied / Rejected / Response) but runs off the Mac and reaches the service only through the Tailscale Funnel address, where just four endpoints are served. It cannot call `PATCH /application/{application_id}` or `GET /applications`, and it does not know application IDs anyway, so application statuses go stale unless the owner updates them by hand in the viewer.

## What Changes

- Add `POST /application/email-status`, an API-key-protected endpoint that takes `company`, `role`, an optional `job_link` and an email `status` (`Applied`, `Rejected` or `Response`), finds the one matching application on the server and updates its status.
- Matching tolerates small name differences (case, punctuation, whitespace, accents, `&`/`and`, common company suffixes such as Inc or LLC). A `job_link` that identifies a stored posting is used first. When zero or several applications match, the endpoint changes nothing and returns a distinct error (404 `no_match`, 409 `ambiguous`) so n8n can flag the email.
- Email status mapping:
  - `Applied` confirms only: it never writes, and reports the application's current status.
  - `Rejected` sets `rejected`.
  - `Response` sets `interviewing`. No new status value is added.
  - Statuses never move backwards: `Response` does not change an application already at `interviewing`, `offer`, `rejected` or `withdrawn`, and `Rejected` does not change a `withdrawn` one.
- Publish the endpoint through Funnel: the public allowlist grows from four to five method and path pairs. `GET /applications` and `PATCH /application/{application_id}` stay local-only.
- Update the OpenAPI document (twenty-two operations), the docs tests, the smoke test's operation count and public-address probes, the install script's public-port wording, and the README.

## Capabilities

### New Capabilities
- `email-status-updates`: the email-driven status endpoint, covering its request body, application matching, the email-status-to-application-status mapping, its responses and errors, auth, store failure handling and logging.

### Modified Capabilities
- `local-service-hosting`: the public Funnel address serves five endpoints instead of four, and the smoke test expects twenty-two documented operations and checks the new endpoint on the public address.
- `api-docs`: the documented operation list grows to twenty-two, the new endpoint needs the API-key scheme, and the reference names five public operations.

## Impact

- `app/main.py`: new route, top-level description, logging (already covered by the `/application/` path prefix).
- `app/models.py`: request and response models for the new endpoint.
- `app/applications.py`: a matching query, plus a guarded status update that runs in one transaction.
- `app/serve.py`: `PUBLIC_ROUTES` gains `("POST", "/application/email-status")`.
- Tests: `tests/test_api.py` or a new `tests/test_email_status.py`, `tests/test_applications.py`, `tests/test_serve.py`, `tests/test_docs.py`.
- Scripts: `scripts/smoke_test.sh` (count 21 → 22, public probe), `scripts/test_smoke_test.sh`, `scripts/install_service.sh` comments and messages.
- `README.md`: public endpoint list and an n8n usage section.
- n8n must send `X-API-Key` and map its parsed email fields to the JSON body. The exposure is one more keyed write on the public address. That write can change only `status`, and only to `rejected` or `interviewing`.
