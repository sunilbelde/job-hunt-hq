# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Installed service serves no API docs`
- TO: `### Requirement: Public address serves no API docs`

## MODIFIED Requirements

### Requirement: Loopback-only listener
The service process SHALL listen only on the loopback interface, on its public service port and on its docs port, so neither is reachable directly from the LAN or the internet.

#### Scenario: LAN access refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

#### Scenario: Docs port not on the LAN
- **WHEN** another device on the local network connects to the Mac's LAN address on the docs port
- **THEN** the connection is refused

### Requirement: Public address serves no API docs
The installed service's public listener, the one published through Funnel, SHALL always run with API docs disabled, whatever `.env` contains, so the public Funnel address never serves the API reference pages or the OpenAPI document.

#### Scenario: Env file enables docs
- **WHEN** `.env` sets `API_DOCS_ENABLED=true` and the owner runs the install script
- **THEN** the public listener responds 404 to `GET /docs`, `GET /redoc` and `GET /openapi.json`

#### Scenario: Internet client probes docs
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/docs` or `https://<mac-tailscale-name>/openapi.json`
- **THEN** it receives 404, with no endpoint list or schema

#### Scenario: Forged headers do not reach the docs
- **WHEN** a client sends `GET /docs` to the public listener with any `Host`, `X-Forwarded-*` or `Tailscale-*` headers
- **THEN** it receives 404

#### Scenario: Smoke test checks docs are off
- **WHEN** the owner runs the smoke test against the installed service
- **THEN** it fails if `GET /docs` or `GET /openapi.json` on the public base URL responds with anything other than 404

## ADDED Requirements

### Requirement: Tailnet-only API docs listener
The installed service SHALL serve the API reference pages, the OpenAPI document and the full API on a second loopback port, the docs port, which Tailscale publishes to the owner's tailnet only, on an HTTPS port that Funnel cannot expose. Requests on this port SHALL behave like those on the public port, apart from serving docs.

#### Scenario: Docs on the Mac itself
- **WHEN** the owner opens `http://127.0.0.1:<docs port>/docs` on the Mac mini
- **THEN** the interactive API reference loads

#### Scenario: Docs from a tailnet device
- **WHEN** a device signed into the owner's tailnet opens `https://<mac-tailscale-name>:<docs https port>/docs`, with the docs mapping set up as the README describes
- **THEN** the interactive API reference loads

#### Scenario: Docs port not public
- **WHEN** a client outside the tailnet connects to `https://<mac-tailscale-name>:<docs https port>/`
- **THEN** it gets no response from the service

#### Scenario: Try it out uses the same API
- **WHEN** a request is sent from the reference page on the docs port
- **THEN** it gets the same status, body and API key check as the same request on the public port, and logs exactly one structured line as it would there

#### Scenario: Shared data
- **WHEN** an application is recorded through the docs port
- **THEN** it is visible to requests on the public port, because both use the same application store and output folder

### Requirement: Install configures and checks the docs listener
The install script SHALL configure the docs port (default 8081, overridable, or turned off), refuse a docs port equal to the service port, check after start that the public port answers 404 and the docs port answers 200 for `/docs`, and print the URLs to open. It SHALL warn when Tailscale does not proxy the docs port and when the docs mapping is Funnel-enabled.

#### Scenario: Default install
- **WHEN** the owner runs the install script without a docs port setting
- **THEN** the service listens on the docs port 8081 and the script prints the local and tailnet docs URLs

#### Scenario: Same port refused
- **WHEN** the install script runs with the docs port equal to the service port
- **THEN** it exits non-zero, names the conflict and installs nothing

#### Scenario: Docs turned off
- **WHEN** the install script runs with the docs listener turned off
- **THEN** the service runs only the public listener and no docs URL is printed

#### Scenario: Docs served on the public port
- **WHEN** after start the public port answers `GET /docs` with anything other than 404
- **THEN** the install script exits non-zero

#### Scenario: Serve mapping missing
- **WHEN** Tailscale is installed but does not proxy the docs port
- **THEN** the install script warns and prints the `tailscale serve` command to run

#### Scenario: Docs mapping published through Funnel
- **WHEN** the Tailscale configuration has Funnel enabled for the docs mapping's HTTPS port
- **THEN** the install script and the status script warn that the docs are public

### Requirement: Status reports the docs listener
The status script SHALL report whether the docs port answers `/docs`, alongside the existing health check.

#### Scenario: Docs listener up
- **WHEN** the owner runs the status script and the docs port answers `GET /docs` with 200
- **THEN** the status output shows the docs listener as ok with its local URL

#### Scenario: Docs listener down
- **WHEN** the docs port is configured but does not answer
- **THEN** the status output shows the docs listener as failing and the script exits non-zero

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page and an OpenAPI document with the six documented operations, in addition to its public-address checks.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` with 200 and `/openapi.json` with the six operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application
