# Spec Delta

## MODIFIED Requirements

### Requirement: Reference says where endpoints are served
The OpenAPI document's descriptions SHALL say that only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter` are served on the public address, and that every other operation is served only on the Mac's local listener. No description SHALL say an operation is served on the tailnet or that the status endpoints or the email status endpoint are served on the public address.

#### Scenario: Service description
- **WHEN** the OpenAPI document is fetched
- **THEN** the top-level description names the four public operations, does not name `POST /application/email-status` among them, and says the rest are local-only

#### Scenario: Status endpoints described as local
- **WHEN** the OpenAPI document is fetched
- **THEN** the `GET /resume/{application_id}/status` and `GET /cover-letter/{application_id}/status` descriptions say they are served only on the local listener, and no description contains the word "tailnet"

#### Scenario: Email status endpoint described as local
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /application/email-status` description says it is served only on the local listener and that the public address answers 404, and does not say it is served on the public address

### Requirement: Email status endpoint documented
The OpenAPI document SHALL tag `POST /application/email-status` `applications` and give it a JSON request body schema listing `company`, `role`, `status` (with its three allowed values), `job_link`, `received_at` and `note`, with an example body the endpoint accepts. Its description SHALL state the status mapping, that `Applied` never writes, that statuses never move backwards, and that a zero or ambiguous match changes nothing. It SHALL name a local email workflow as the caller, not n8n.

#### Scenario: Body documented
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /application/email-status` request body requires `company`, `role` and `status`, lists `Applied`, `Rejected` and `Response` for `status`, and its example is accepted by the endpoint

#### Scenario: Mapping described
- **WHEN** the OpenAPI document is fetched
- **THEN** the operation's description says `Rejected` sets `rejected`, `Response` sets `interviewing`, `Applied` changes nothing, statuses never move backwards, and 404 and 409 leave every application unchanged

#### Scenario: Caller described
- **WHEN** the OpenAPI document is fetched
- **THEN** the operation's description names a local email workflow such as Hermes, and no description contains the word "n8n"
