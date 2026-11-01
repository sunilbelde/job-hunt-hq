# Spec Delta

## ADDED Requirements

### Requirement: Reference says where endpoints are served
The OpenAPI document's descriptions SHALL say that only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter` are served on the public address, and that every other operation is served only on the Mac's local listener. No description SHALL say an operation is served on the tailnet or that the status endpoints are served on the public address.

#### Scenario: Service description
- **WHEN** the OpenAPI document is fetched
- **THEN** the top-level description names the four public operations and says the rest are local-only

#### Scenario: Status endpoints described as local
- **WHEN** the OpenAPI document is fetched
- **THEN** the `GET /resume/{application_id}/status` and `GET /cover-letter/{application_id}/status` descriptions say they are served only on the local listener, and no description contains the word "tailnet"
