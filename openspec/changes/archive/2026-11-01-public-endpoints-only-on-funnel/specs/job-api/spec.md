# Spec Delta

## MODIFIED Requirements

### Requirement: Health endpoints
The system SHALL expose `GET /healthz` and `GET /health`, each returning 200 `{"status": "ok"}` without authentication and without touching storage. The installed service's public listener SHALL serve only `GET /health`; `GET /healthz` there SHALL be handled as an unknown path.

#### Scenario: Health check
- **WHEN** any client sends `GET /healthz` or `GET /health` to the docs port or to a development server
- **THEN** the system responds 200 `{"status": "ok"}` and makes no storage call

#### Scenario: Public listener health
- **WHEN** a client sends `GET /health` to the public listener
- **THEN** it responds 200 `{"status": "ok"}`

#### Scenario: Alias not public
- **WHEN** a client sends `GET /healthz` to the public listener
- **THEN** it responds 404
