# local-service-hosting Specification

## Purpose

Defines how the service runs as an always-on process on the owner's Mac mini: how it is started, kept alive, logged, installed and removed, and how it is reached privately from the owner's devices without any cloud hosting.

## Requirements

### Requirement: Starts at boot without login
The service SHALL be installed as a system launchd job that starts automatically when the Mac boots, without requiring any user to log in, and runs as the owner's non-root user account.

#### Scenario: Reboot
- **WHEN** the Mac mini restarts and nobody logs in
- **THEN** `GET /health` on the service responds 200 within two minutes of boot

#### Scenario: Not root
- **WHEN** the service process is running
- **THEN** its effective user is the owner's account, not root

### Requirement: Restarts after failure
The service SHALL be restarted automatically if its process exits unexpectedly, with a throttle that prevents a tight crash loop.

#### Scenario: Process killed
- **WHEN** the running service process is killed
- **THEN** a new process is serving `GET /health` within 30 seconds

### Requirement: Loopback-only listener
The service process SHALL listen only on the loopback interface, on its public service port and on its docs port, so neither is reachable directly from the LAN or the internet.

#### Scenario: LAN access refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

#### Scenario: Docs port not on the LAN
- **WHEN** another device on the local network connects to the Mac's LAN address on the docs port
- **THEN** the connection is refused

### Requirement: Persistent log files
The service SHALL write its logs, including startup errors and crash output, to files under the owner's `~/Library/Logs/job-hunt-hq/` directory. The main service log SHALL be rotated by size so it does not grow without bound.

#### Scenario: Request logged
- **WHEN** a `POST /resume` request completes
- **THEN** its structured log line appears in the service log file

#### Scenario: Rotation
- **WHEN** the main service log exceeds its configured size limit
- **THEN** it is rotated and older rotations beyond the kept count are removed

### Requirement: Install, uninstall and status scripts
The repository SHALL provide idempotent scripts to install the service, uninstall it, and report its status, so setup on a fresh Mac needs no hand-edited system files.

#### Scenario: Fresh install
- **WHEN** the owner runs the install script after completing the README prerequisites and filling in `.env`
- **THEN** the service is loaded into launchd and `GET /health` responds 200

#### Scenario: Reinstall
- **WHEN** the install script is run again on an already-installed service
- **THEN** it replaces the job definition, restarts the service, and does not fail

#### Scenario: Uninstall
- **WHEN** the owner runs the uninstall script
- **THEN** the service stops, will not start at the next boot, and stored output files are left in place

#### Scenario: Status
- **WHEN** the owner runs the status script
- **THEN** it reports whether the launchd job is loaded, the process id if running, and the result of a health check

### Requirement: Install refuses unsafe configuration
The install script SHALL refuse to install when `.env` is missing, readable by users other than its owner, or rejected by the service's startup validation, and SHALL name the problem without printing secret values.

#### Scenario: World-readable env file
- **WHEN** `.env` has permissions that let other users read it
- **THEN** the install script exits non-zero, explains how to fix the permissions, and installs nothing

### Requirement: Public HTTPS access through Tailscale Funnel
The service SHALL be reachable over HTTPS at the Mac's Tailscale hostname from both tailnet devices and the public internet, through Tailscale Funnel, while the process itself keeps listening only on loopback. Resume generation and the application endpoints SHALL still require the API key, and generated files SHALL NOT be retrievable over this public address.

#### Scenario: Tailnet device
- **WHEN** a device signed into the owner's tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/health`
- **THEN** it receives 200 `{"status": "ok"}`

#### Scenario: Internet client without API key
- **WHEN** a client outside the tailnet sends `POST /resume` without a valid `X-API-Key`
- **THEN** it receives 401 and nothing is generated or stored

#### Scenario: LAN still refused
- **WHEN** another device on the local network connects to the Mac's LAN address on the service port
- **THEN** the connection is refused

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

### Requirement: Install configures and checks the docs listener
The install script SHALL configure the docs port (default 8081, overridable, or turned off), refuse a docs port equal to the service port, check after start that the public port answers 404 and the docs port answers 200 for `/docs` and `/viewer`, and print the docs and viewer URLs to open. It SHALL warn when Tailscale does not proxy the docs port and when the docs mapping is Funnel-enabled.

#### Scenario: Default install
- **WHEN** the owner runs the install script without a docs port setting
- **THEN** the service listens on the docs port 8081 and the script prints the local and tailnet docs and viewer URLs

#### Scenario: Same port refused
- **WHEN** the install script runs with the docs port equal to the service port
- **THEN** it exits non-zero, names the conflict and installs nothing

#### Scenario: Docs turned off
- **WHEN** the install script runs with the docs listener turned off
- **THEN** the service runs only the public listener and no docs or viewer URL is printed

#### Scenario: Docs served on the public port
- **WHEN** after start the public port answers `GET /docs` or `GET /viewer` with anything other than 404
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
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the ten documented operations, in addition to its public-address checks.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the ten operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

### Requirement: Service runs Claude with its own configuration
The installed service SHALL run the Claude Code CLI found when it was installed. It SHALL give Claude runs a private configuration of the service's own, so the owner's personal Claude Code settings, login, plugins, hooks, MCP servers, memory and shell startup files are never used by service runs.

#### Scenario: CLI outside the service PATH
- **WHEN** the owner's Claude Code CLI is installed in `~/.local/bin`, which the launchd job's default `PATH` does not include
- **THEN** the installed service still finds and runs it

#### Scenario: Personal hooks not run
- **WHEN** the owner's own Claude Code configuration defines a hook or an MCP server
- **THEN** service Claude runs neither execute the hook nor connect to the server

#### Scenario: Shell profile not loaded
- **WHEN** the owner's `~/.zshrc` defines an alias or exports a variable
- **THEN** commands in service Claude runs see neither

### Requirement: Install checks tailoring prerequisites
The install script SHALL warn, without failing, when the Claude Code CLI cannot be found, when `.env` sets no Claude credential, or when one minimal live request shows the credential is rejected. Each warning SHALL say how to fix it and SHALL never print a credential.

#### Scenario: CLI missing
- **WHEN** the install script runs and no `claude` command is found
- **THEN** it completes the install, warns that resumes needing tailoring will fail, and says how to install Claude Code

#### Scenario: No credential
- **WHEN** `.env` sets neither `CLAUDE_CODE_OAUTH_TOKEN` nor `ANTHROPIC_API_KEY`
- **THEN** the install script warns and names `claude setup-token` and `ANTHROPIC_API_KEY` as the two ways to configure one

#### Scenario: Credential rejected
- **WHEN** `.env` sets a `CLAUDE_CODE_OAUTH_TOKEN` that the API rejects, such as one pasted across two lines
- **THEN** the install completes, warns that the credential was rejected, and says to paste the token from `claude setup-token` as one line

### Requirement: Status reports tailoring readiness
The status script SHALL report whether tailoring is ready: the Claude CLI path and version, which kind of credential is configured (subscription token or API key) and the model, without printing the credential.

#### Scenario: Ready
- **WHEN** the CLI is installed and `.env` sets `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** the status output shows tailoring as ready with a subscription token and the configured model

#### Scenario: Not configured
- **WHEN** no Claude credential is configured
- **THEN** the status output shows tailoring as not configured

### Requirement: Smoke test never starts a Claude run
The smoke test SHALL generate its resume for an application with no posting text and check that `match.status` is `no_job_description`. If it reuses a leftover application that has posting text, it SHALL clear that text before generating, so it never starts a Claude run.

#### Scenario: Fresh smoke test
- **WHEN** the smoke test runs against a service with no leftover smoke-test application
- **THEN** the resume is generated without a Claude run and `match.status` is `no_job_description`

#### Scenario: Leftover application with posting text
- **WHEN** an earlier version of the smoke test left its application with posting text
- **THEN** the smoke test clears that text before requesting the resume
