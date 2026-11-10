## MODIFIED Requirements

### Requirement: Viewer fill endpoint documented
The OpenAPI document SHALL tag `POST /viewer/application/{application_id}/fill` `viewer`, mark it as needing no API key and taking no request body, and list 200, 403, 404 and 503. Its description SHALL name the Herdr workspace, the tab label format and the command it runs, say that the session submits the application on its own unless one of its guardrails stops it and it asks in that tab, and explain `already_open`. It SHALL NOT say the session never submits. The 503 description SHALL mention `Herdr unavailable`.

#### Scenario: Fill endpoint listed
- **WHEN** the OpenAPI document is fetched
- **THEN** the fill operation is tagged `viewer`, has no security requirement and no request body, and its description says it is served only where the viewer is, refuses cross-site requests, and names `Claude-Jobs-Automation`, `<Company>-<Role>-<application_id>` and `/job-application-form-filler <application_id>`

#### Scenario: Submit behavior described
- **WHEN** the OpenAPI document is fetched
- **THEN** the fill description says the session submits on its own unless it stops to ask, and does not contain "never submits"

### Requirement: Viewer apply-from-link endpoint documented
The OpenAPI document SHALL tag `POST /viewer/apply-from-link` `viewer`, mark it as needing no API key, describe its request body and its 200 response, and list 200, 403, 422 and 503. Its description SHALL name the Herdr workspace, the tab label format and the command it runs, say that the session submits the application on its own unless one of its guardrails stops it and it asks in that tab, and explain `already_open`. It SHALL NOT say the session never submits.

#### Scenario: Endpoint listed
- **WHEN** the OpenAPI document is fetched
- **THEN** the operation is tagged `viewer`, has no security requirement, and its description says it is served only where the viewer is, refuses cross-site requests, and names `Claude-Jobs-Automation`, `ByLink-<host>-<hash>` and `/apply-from-link <link>`

#### Scenario: Submit behavior described
- **WHEN** the OpenAPI document is fetched
- **THEN** the apply-from-link description says the session submits on its own unless it stops to ask, and does not contain "never submits"

#### Scenario: Request body
- **WHEN** the OpenAPI document is fetched
- **THEN** the request body requires a string `link`, says it must be an `http` or `https` URL of at most 2048 characters, and has an example the endpoint accepts
