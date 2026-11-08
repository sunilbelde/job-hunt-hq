# Spec Delta

## MODIFIED Requirements

### Requirement: Public HTTPS access through Tailscale Funnel
The service SHALL be reachable over HTTPS at the Mac's Tailscale hostname from both tailnet devices and the public internet, through Tailscale Funnel, while the process itself keeps listening only on loopback. Over this public address it SHALL serve only `GET /health`, `POST /application`, `POST /application/email-status`, `POST /resume` and `POST /cover-letter`; the four `POST` endpoints SHALL still require the API key, and generated files SHALL NOT be retrievable over it.

#### Scenario: Tailnet device
- **WHEN** a device signed into the owner's tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client without API key
- **WHEN** a client outside the tailnet sends `POST /resume` without a valid `X-API-Key`
- **THEN** it receives 401 and nothing is generated or stored

#### Scenario: Muse records and generates
- **WHEN** an authenticated client sends `POST /application`, then `POST /resume` and `POST /cover-letter` for the returned ID, to the public address
- **THEN** it gets 201 (or 200 for a link already recorded), then 202 and 202, exactly as on the local listener

#### Scenario: n8n updates a status
- **WHEN** an authenticated client outside the tailnet sends `POST /application/email-status` with a `Rejected` email for a company and role that match one application
- **THEN** it gets 200 and that application's status becomes `rejected`, exactly as on the local listener

#### Scenario: Email status without API key
- **WHEN** a client outside the tailnet sends `POST /application/email-status` without a valid `X-API-Key`
- **THEN** it receives 401 and no application changes

#### Scenario: LAN still refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the twenty-two documented operations, in addition to its public-address checks. The docs listener SHALL be required: `DOCS_URL=off` SHALL be refused.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the twenty-two operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

#### Scenario: Wrong operation count
- **WHEN** the docs listener's OpenAPI document lists any number of operations other than twenty-two, such as the twenty-one from before the email status endpoint
- **THEN** the smoke test fails before creating any application

#### Scenario: Docs listener turned off
- **WHEN** the smoke test runs with `DOCS_URL=off`
- **THEN** it exits non-zero with a usage message before sending any request

### Requirement: Public listener serves only the Funnel endpoints
The installed service's public listener SHALL serve only `GET /health`, `POST /application`, `POST /application/email-status`, `POST /resume` and `POST /cover-letter`. Every other path and method SHALL be handled exactly as an unknown path would be, whatever `X-API-Key` or forwarding headers the request carries, and SHALL change no data. The restriction SHALL be set in code, not by `.env`.

#### Scenario: Local-only endpoints answer 404
- **WHEN** a client with a valid `X-API-Key` sends `GET /healthz`, `GET /applications`, `PATCH /application/<id>`, `DELETE /application/<id>`, `GET /resume/<id>/status` or `GET /cover-letter/<id>/status` to the public listener, for an existing application with a finished job
- **THEN** each responds 404 with no job state, application field or file name, and the application still exists unchanged

#### Scenario: Same 404 with or without a key
- **WHEN** a client sends `GET /resume/<id>/status` to the public listener without `X-API-Key`
- **THEN** it gets the same 404 as with a valid key, not 401, so the response does not reveal the endpoint exists elsewhere

#### Scenario: Other methods on the email status path
- **WHEN** a client sends `GET`, `PATCH` or `DELETE` to `/application/email-status` on the public listener
- **THEN** it gets the unknown-path 404, not 405

#### Scenario: Smoke test checks the moved endpoints
- **WHEN** the owner runs the smoke test
- **THEN** it fails if, on the public base URL, `GET /healthz`, `GET /applications`, `GET /resume/<zero uuid>/status`, `GET /cover-letter/<zero uuid>/status`, or `PATCH` or `DELETE /application/<zero uuid>` with the API key, answers anything other than 404, where `<zero uuid>` is `00000000-0000-0000-0000-000000000000`

#### Scenario: Smoke test checks the email status endpoint
- **WHEN** the owner runs the smoke test
- **THEN** it sends an authenticated `Applied` email for a company and role no application has to `POST /application/email-status` on the public base URL, and fails unless the response is 404 with `reason` `no_match`

#### Scenario: Development server unchanged
- **WHEN** the service is run with `uvicorn app.main:create_app --factory`, with or without `API_DOCS_ENABLED`
- **THEN** every API endpoint, `GET /healthz` and the status endpoints included, is served as before
