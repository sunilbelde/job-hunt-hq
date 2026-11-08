# Spec Delta

## MODIFIED Requirements

### Requirement: Public HTTPS access through Tailscale Funnel
The service SHALL be reachable over HTTPS at the Mac's Tailscale hostname from both tailnet devices and the public internet, through Tailscale Funnel, while the process itself keeps listening only on loopback. Over this public address it SHALL serve only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter`; the three `POST` endpoints SHALL still require the API key, and generated files SHALL NOT be retrievable over it.

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
- **WHEN** an authenticated client outside the tailnet, such as the off-Mac n8n workflow once assumed, sends `POST /application/email-status` with a `Rejected` email for a company and role that match one application
- **THEN** it receives the unknown-path 404 and the application's status is unchanged; the email workflow calls the local listener instead

#### Scenario: Email status without API key
- **WHEN** a client outside the tailnet sends `POST /application/email-status` without a valid `X-API-Key`
- **THEN** it receives the same unknown-path 404 as with a valid key, not 401, and no application changes

#### Scenario: LAN still refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

### Requirement: Public listener serves only the Funnel endpoints
The installed service's public listener SHALL serve only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter`. Every other path and method SHALL be handled exactly as an unknown path would be, whatever `X-API-Key` or forwarding headers the request carries, and SHALL change no data. The restriction SHALL be set in code, not by `.env`.

#### Scenario: Local-only endpoints answer 404
- **WHEN** a client with a valid `X-API-Key` sends `GET /healthz`, `GET /applications`, `PATCH /application/<id>`, `DELETE /application/<id>`, `POST /application/email-status`, `GET /resume/<id>/status` or `GET /cover-letter/<id>/status` to the public listener, for an existing application with a finished job
- **THEN** each responds 404 with no job state, application field or file name, and the application still exists unchanged

#### Scenario: Same 404 with or without a key
- **WHEN** a client sends `GET /resume/<id>/status` or `POST /application/email-status` to the public listener without `X-API-Key`
- **THEN** it gets the same 404 as with a valid key, not 401, so the response does not reveal the endpoint exists elsewhere

#### Scenario: Other methods on the email status path
- **WHEN** a client sends `GET`, `PATCH` or `DELETE` to `/application/email-status` on the public listener
- **THEN** it gets the unknown-path 404, not 405

#### Scenario: Smoke test checks the moved endpoints
- **WHEN** the owner runs the smoke test
- **THEN** it fails if, on the public base URL, `GET /healthz`, `GET /applications`, `GET /resume/<zero uuid>/status`, `GET /cover-letter/<zero uuid>/status`, `POST /application/email-status`, or `PATCH` or `DELETE /application/<zero uuid>` with the API key, answers anything other than 404, where `<zero uuid>` is `00000000-0000-0000-0000-000000000000`

#### Scenario: Smoke test checks the email status endpoint
- **WHEN** the owner runs the smoke test
- **THEN** it sends an authenticated `Applied` email for a company and role no application has to `POST /application/email-status` on the local listener, and fails unless the response is 404 with `reason` `no_match`

#### Scenario: Development server unchanged
- **WHEN** the service is run with `uvicorn app.main:create_app --factory`, with or without `API_DOCS_ENABLED`
- **THEN** every API endpoint, `GET /healthz`, the status endpoints and `POST /application/email-status` included, is served as before

### Requirement: Loopback-only local listener
The installed service SHALL serve the API reference pages, the OpenAPI document, the resume viewer with its endpoints, and the full API on a second loopback port, the docs port, that is reached only from the Mac itself. Requests on this port SHALL behave like the same requests on the public port where both serve them, and both ports SHALL share one application store and output folder.

#### Scenario: Docs on the Mac itself
- **WHEN** the owner opens `http://127.0.0.1:<docs port>/docs` on the Mac mini
- **THEN** the interactive API reference loads

#### Scenario: Viewer on the Mac itself
- **WHEN** the owner opens `http://127.0.0.1:<docs port>/viewer` on the Mac mini
- **THEN** the resume viewer lists the applications without asking for the API key, and every request the page makes goes to `http://127.0.0.1:<docs port>`

#### Scenario: Status and edits on the Mac
- **WHEN** an authenticated client on the Mac calls `GET /resume/<id>/status`, `PATCH /application/<id>` or `DELETE /application/<id>` on the docs port
- **THEN** it gets the same response as those endpoints gave before this change

#### Scenario: Local email workflow updates a status
- **WHEN** the owner's email workflow on the Mac (Hermes) sends `POST /application/email-status` with a valid `X-API-Key` and a `Rejected` email for a company and role that match one application to `http://127.0.0.1:<docs port>`
- **THEN** it gets 200 and that application's status becomes `rejected`; without a valid key it gets 401 and nothing changes

#### Scenario: Not reachable from the tailnet
- **WHEN** the README setup is followed and a tailnet device connects to the Mac's Tailscale hostname on any HTTPS port other than the Funnel one
- **THEN** it gets no response from the docs listener

#### Scenario: Try it out uses the same API
- **WHEN** a request to an endpoint the public port also serves is sent from the reference page on the docs port
- **THEN** it gets the same status, body and API key check as the same request on the public port, and logs exactly one structured line as it would there

#### Scenario: Shared data
- **WHEN** an application is recorded through the public port
- **THEN** it is visible in the viewer and to requests on the docs port, because both use the same application store and output folder
