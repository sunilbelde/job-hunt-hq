## MODIFIED Requirements

### Requirement: Tailnet-only API docs listener
The installed service SHALL serve the API reference pages, the OpenAPI document, the resume viewer with its read endpoints, and the full API on a second loopback port, the docs port, which Tailscale publishes to the owner's tailnet only, on an HTTPS port that Funnel cannot expose. Requests on this port SHALL behave like those on the public port, apart from serving docs and the viewer.

#### Scenario: Docs on the Mac itself
- **WHEN** the owner opens `http://127.0.0.1:<docs port>/docs` on the Mac mini
- **THEN** the interactive API reference loads

#### Scenario: Docs from a tailnet device
- **WHEN** a device signed into the owner's tailnet opens `https://<mac-tailscale-name>:<docs https port>/docs`, with the docs mapping set up as the README describes
- **THEN** the interactive API reference loads

#### Scenario: Viewer from a tailnet device
- **WHEN** a device signed into the owner's tailnet opens `https://<mac-tailscale-name>:<docs https port>/viewer`
- **THEN** the resume viewer lists the applications without asking for the API key

#### Scenario: Docs port not public
- **WHEN** a client outside the tailnet connects to `https://<mac-tailscale-name>:<docs https port>/`
- **THEN** it gets no response from the service

#### Scenario: Try it out uses the same API
- **WHEN** a request is sent from the reference page on the docs port
- **THEN** it gets the same status, body and API key check as the same request on the public port, and logs exactly one structured line as it would there

#### Scenario: Shared data
- **WHEN** an application is recorded through the docs port
- **THEN** it is visible to requests on the public port, because both use the same application store and output folder

### Requirement: Public address serves no API docs
The installed service's public listener, the one published through Funnel, SHALL always run with API docs disabled, whatever `.env` contains, so the public Funnel address never serves the API reference pages, the OpenAPI document, the resume viewer or the viewer's read endpoints.

#### Scenario: Env file enables docs
- **WHEN** `.env` sets `API_DOCS_ENABLED=true` and the owner runs the install script
- **THEN** the public listener responds 404 to `GET /docs`, `GET /redoc`, `GET /openapi.json` and `GET /viewer`

#### Scenario: Internet client probes docs
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/docs` or `https://<mac-tailscale-name>/openapi.json`
- **THEN** it receives 404, with no endpoint list or schema

#### Scenario: Internet client probes the viewer
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/applications`, `/application/<id>`, `/application/<id>/resume.pdf` or `/resume/base.pdf`, with or without a valid `X-API-Key`
- **THEN** it receives 404, with no application, report or file content

#### Scenario: Forged headers do not reach the docs
- **WHEN** a client sends `GET /docs` to the public listener with any `Host`, `X-Forwarded-*` or `Tailscale-*` headers
- **THEN** it receives 404

#### Scenario: Smoke test checks docs are off
- **WHEN** the owner runs the smoke test against the installed service
- **THEN** it fails if `GET /docs`, `GET /openapi.json` or `GET /viewer` on the public base URL responds with anything other than 404
