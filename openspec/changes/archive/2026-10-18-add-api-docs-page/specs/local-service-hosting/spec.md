# Spec Delta

## ADDED Requirements

### Requirement: Installed service serves no API docs
The installed launchd service SHALL always run with API docs disabled, whatever `.env` contains, so the public Funnel address never serves the API reference pages or the OpenAPI document.

#### Scenario: Env file enables docs
- **WHEN** `.env` sets `API_DOCS_ENABLED=true` and the owner runs the install script
- **THEN** the running service responds 404 to `GET /docs`, `GET /redoc` and `GET /openapi.json`

#### Scenario: Internet client probes docs
- **WHEN** a client outside the tailnet requests `https://<mac-tailscale-name>/docs` or `https://<mac-tailscale-name>/openapi.json`
- **THEN** it receives 404, with no endpoint list or schema

#### Scenario: Smoke test checks docs are off
- **WHEN** the owner runs the smoke test against the installed service
- **THEN** it fails if `GET /docs` or `GET /openapi.json` responds with anything other than 404
