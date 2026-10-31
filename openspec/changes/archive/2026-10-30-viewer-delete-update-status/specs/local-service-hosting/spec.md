# Spec Delta

## MODIFIED Requirements

### Requirement: Public address serves no API docs
The installed service's public listener, the one published through Funnel, SHALL always run with API docs disabled, whatever `.env` contains, so the public Funnel address never serves the API reference pages, the OpenAPI document, the resume viewer, the viewer's read endpoints or the viewer's write endpoints.

#### Scenario: Env file enables docs
- **WHEN** `.env` sets `API_DOCS_ENABLED=true` and the owner runs the install script
- **THEN** the public listener responds 404 to `GET /docs`, `GET /redoc`, `GET /openapi.json` and `GET /viewer`

#### Scenario: Internet client probes docs
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/docs` or `https://<mac-tailscale-name>/openapi.json`
- **THEN** it receives 404, with no endpoint list or schema

#### Scenario: Internet client probes the viewer
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/applications`, `/application/<id>`, `/application/<id>/resume.pdf` or `/resume/base.pdf`, with or without a valid `X-API-Key`
- **THEN** it receives 404, with no application, report or file content

#### Scenario: Internet client tries a viewer write
- **WHEN** a client outside the tailnet sends `PATCH` or `DELETE` to `https://<mac-tailscale-name>/viewer/application/<id>` for an existing application, with or without a valid `X-API-Key`
- **THEN** it receives 404 and the application is unchanged

#### Scenario: Forged headers do not reach the docs
- **WHEN** a client sends `GET /docs` to the public listener with any `Host`, `X-Forwarded-*` or `Tailscale-*` headers
- **THEN** it receives 404

#### Scenario: Smoke test checks docs are off
- **WHEN** the owner runs the smoke test against the installed service
- **THEN** it fails if `GET /docs`, `GET /openapi.json` or `GET /viewer` on the public base URL responds with anything other than 404

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the seventeen documented operations, in addition to its public-address checks.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the seventeen operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

#### Scenario: Wrong operation count
- **WHEN** the docs listener's OpenAPI document lists any number of operations other than seventeen, such as the fifteen from before the viewer write endpoints
- **THEN** the smoke test fails before creating any application
