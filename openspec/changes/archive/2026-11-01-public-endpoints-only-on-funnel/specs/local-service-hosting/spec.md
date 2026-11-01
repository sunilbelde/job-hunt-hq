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

#### Scenario: LAN still refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

### Requirement: Install configures and checks the docs listener
The install script SHALL always configure the local listener on the docs port (default 8081, overridable), refuse a docs port equal to the service port or set to `off`, check after start that the public port answers 404 and the docs port 200 for `/docs` and `/viewer`, that a local-only endpoint answers 404 on the public port, and print the local docs and viewer URLs. It SHALL warn when any Tailscale serve or Funnel mapping proxies the docs port.

#### Scenario: Default install
- **WHEN** the owner runs the install script without a docs port setting
- **THEN** the service listens on the docs port 8081 and the script prints `http://127.0.0.1:8081/docs` and `http://127.0.0.1:8081/viewer`, and no tailnet URL

#### Scenario: Same port refused
- **WHEN** the install script runs with the docs port equal to the service port
- **THEN** it exits non-zero, names the conflict and installs nothing

#### Scenario: Docs turned off
- **WHEN** the install script runs with `DOCS_PORT=off`
- **THEN** it exits non-zero, says the local listener is required for job status and the viewer, and installs nothing

#### Scenario: Docs served on the public port
- **WHEN** after start the public port answers `GET /docs` or `GET /viewer` with anything other than 404
- **THEN** the install script exits non-zero

#### Scenario: Local-only endpoint on the public port
- **WHEN** after start the public port answers `GET /healthz` or `GET /resume/00000000-0000-0000-0000-000000000000/status` with anything other than 404
- **THEN** the install script exits non-zero, naming the path

#### Scenario: Serve mapping missing
- **WHEN** Tailscale is installed and no serve or Funnel mapping proxies the docs port
- **THEN** the install script prints no warning about the docs port and suggests no `tailscale serve` command for it

#### Scenario: Leftover tailnet mapping
- **WHEN** a tailnet-only `tailscale serve` mapping still proxies the docs port, such as the `:8444` mapping from an earlier install
- **THEN** the install script completes, warns that the docs and viewer are reachable from the tailnet, and prints the `tailscale serve --https=<port> off` command that removes it

#### Scenario: Docs mapping published through Funnel
- **WHEN** the Tailscale configuration has Funnel enabled for a mapping that proxies the docs port
- **THEN** the install script and the status script warn that the docs are public and print the command that turns it off

### Requirement: Status reports the docs listener
The status script SHALL report whether the docs port answers `/docs` on loopback, alongside the existing health check, and SHALL warn when any Tailscale serve or Funnel mapping proxies the docs port.

#### Scenario: Docs listener up
- **WHEN** the owner runs the status script and the docs port answers `GET /docs` with 200
- **THEN** the status output shows the docs listener as ok with its local URL

#### Scenario: Docs listener down
- **WHEN** the docs port is configured but does not answer
- **THEN** the status output shows the docs listener as failing and the script exits non-zero

#### Scenario: Local only
- **WHEN** no Tailscale mapping proxies the docs port
- **THEN** the status output shows the docs listener as local only, with no tailnet URL

#### Scenario: Mapping still present
- **WHEN** a Tailscale serve mapping proxies the docs port
- **THEN** the status output warns that the docs listener is reachable from the tailnet and names the command that removes the mapping

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the eighteen documented operations, in addition to its public-address checks. The docs listener SHALL be required: `DOCS_URL=off` SHALL be refused.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the eighteen operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

#### Scenario: Wrong operation count
- **WHEN** the docs listener's OpenAPI document lists any number of operations other than eighteen, such as the seventeen from before the fill endpoint
- **THEN** the smoke test fails before creating any application

#### Scenario: Docs listener turned off
- **WHEN** the smoke test runs with `DOCS_URL=off`
- **THEN** it exits non-zero with a usage message before sending any request

### Requirement: Smoke test never starts a Claude run
The smoke test SHALL generate its resume for an application with no posting text. It SHALL record the application and request the resume on the public address, check that `POST /resume` answers 202, then poll `GET /resume/{application_id}/status` on the docs listener until the job is `done`, with a bounded wait. It SHALL check that `match.status` is `no_job_description` and that the resume is a PDF. If it reuses a leftover application with posting text, it SHALL clear that text first, through the docs listener. It SHALL request a cover letter on the public address and check for 422 and no cover letter file.

#### Scenario: Fresh smoke test
- **WHEN** the smoke test runs against a service with no leftover smoke-test application
- **THEN** `POST /resume` on the public address answers 202, the status endpoint on the docs listener reaches `done` without a Claude run, `match.status` is `no_job_description`, and the PDF is found under `OUTPUT_DIR` from the returned file name

#### Scenario: Leftover application with posting text
- **WHEN** an earlier version of the smoke test left its application with posting text
- **THEN** the smoke test clears that text with `PATCH /application/{id}` on the docs listener before requesting the resume

#### Scenario: Job fails or never finishes
- **WHEN** the resume job is reported `failed`, or is still `running` when the wait runs out
- **THEN** the smoke test fails and still deletes the application it created, through the docs listener

#### Scenario: Status endpoint missing on the public address
- **WHEN** the smoke test polls the resume job
- **THEN** it polls the docs listener only, since the public address no longer serves `GET /resume/{application_id}/status`

#### Scenario: Status endpoint missing on the docs listener
- **WHEN** `GET /resume/{application_id}/status` on the docs listener answers 404 for the application the smoke test just requested a resume for
- **THEN** the smoke test fails

#### Scenario: Cover letter refused without posting text
- **WHEN** the smoke test requests a cover letter for its application
- **THEN** the service answers 422, no Claude run starts, and no cover letter file appears in the application's folder

## ADDED Requirements

### Requirement: Public listener serves only the Funnel endpoints
The installed service's public listener SHALL serve only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter`. Every other path and method SHALL be handled exactly as an unknown path would be, whatever `X-API-Key` or forwarding headers the request carries, and SHALL change no data. The restriction SHALL be set in code, not by `.env`.

#### Scenario: Local-only endpoints answer 404
- **WHEN** a client with a valid `X-API-Key` sends `GET /healthz`, `PATCH /application/<id>`, `DELETE /application/<id>`, `GET /resume/<id>/status` or `GET /cover-letter/<id>/status` to the public listener, for an existing application with a finished job
- **THEN** each responds 404 with no job state, application field or file name, and the application still exists unchanged

#### Scenario: Same 404 with or without a key
- **WHEN** a client sends `GET /resume/<id>/status` to the public listener without `X-API-Key`
- **THEN** it gets the same 404 as with a valid key, not 401, so the response does not reveal the endpoint exists elsewhere

#### Scenario: Smoke test checks the moved endpoints
- **WHEN** the owner runs the smoke test
- **THEN** it fails if, on the public base URL, `GET /healthz`, `GET /resume/<zero uuid>/status`, `GET /cover-letter/<zero uuid>/status`, or `PATCH` or `DELETE /application/<zero uuid>` with the API key, answers anything other than 404, where `<zero uuid>` is `00000000-0000-0000-0000-000000000000`

#### Scenario: Development server unchanged
- **WHEN** the service is run with `uvicorn app.main:create_app --factory`, with or without `API_DOCS_ENABLED`
- **THEN** every API endpoint, `GET /healthz` and the status endpoints included, is served as before

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

#### Scenario: Not reachable from the tailnet
- **WHEN** the README setup is followed and a tailnet device connects to the Mac's Tailscale hostname on any HTTPS port other than the Funnel one
- **THEN** it gets no response from the docs listener

#### Scenario: Try it out uses the same API
- **WHEN** a request to an endpoint the public port also serves is sent from the reference page on the docs port
- **THEN** it gets the same status, body and API key check as the same request on the public port, and logs exactly one structured line as it would there

#### Scenario: Shared data
- **WHEN** an application is recorded through the public port
- **THEN** it is visible in the viewer and to requests on the docs port, because both use the same application store and output folder

## REMOVED Requirements

### Requirement: Tailnet-only API docs listener
**Reason**: The owner now uses the docs and viewer only on the Mac mini, so publishing the docs port to the tailnet is surface with no user. Replaced by "Loopback-only local listener".
**Migration**: Open `http://127.0.0.1:8081/docs` and `/viewer` on the Mac mini. Remove the old mapping with `tailscale serve --https=8444 off`; the install and status scripts warn until it is gone.
