# Spec Delta

## ADDED Requirements

### Requirement: Viewer apply-from-link endpoint documented
The OpenAPI document SHALL tag `POST /viewer/apply-from-link` `viewer`, mark it as needing no API key, describe its request body and its 200 response, and list 200, 403, 422 and 503. Its description SHALL name the Herdr workspace, the tab label format and the command it runs, say that the session never submits unless asked in it, and explain `already_open`.

#### Scenario: Endpoint listed
- **WHEN** the OpenAPI document is fetched
- **THEN** the operation is tagged `viewer`, has no security requirement, and its description says it is served only where the viewer is, refuses cross-site requests, and names `Claude-Jobs-Automation`, `ByLink-<host>-<hash>` and `/apply-from-link <link>`

#### Scenario: Request body
- **WHEN** the OpenAPI document is fetched
- **THEN** the request body requires a string `link`, says it must be an `http` or `https` URL of at most 2048 characters, and has an example the endpoint accepts

### Requirement: Application origin documented
The OpenAPI document SHALL list `added_via` with its allowed values `link` and `manual` and its default `manual` in the `POST /application` body, and in the `GET /applications` entry and `GET /application/{application_id}` schemas. It SHALL NOT list it as updatable in either `PATCH` body. The `POST /application` body's documented example SHALL stay accepted.

#### Scenario: Recording body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /application` body lists `added_via` as optional, with values `link` and `manual`

#### Scenario: Update body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `PATCH /application/{application_id}` body does not list `added_via`

### Requirement: Link filter documented
The OpenAPI document SHALL describe the optional `job_link` query parameter of `GET /applications`, saying that it returns at most the one application with the same dedupe key, and that a posting not stored gives an empty list.

#### Scenario: Parameter listed
- **WHEN** the OpenAPI document is fetched
- **THEN** `GET /applications` lists an optional string query parameter `job_link` with that description

## MODIFIED Requirements

### Requirement: Documented endpoint coverage
The OpenAPI document SHALL describe `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume`, `GET /resume/{application_id}/status`, `POST /cover-letter`, `GET /cover-letter/{application_id}/status`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `GET /resume/base.pdf`, `GET /cover-letter/base.pdf`, `PATCH /viewer/application/{application_id}`, `DELETE /viewer/application/{application_id}`, `POST /viewer/application/{application_id}/fill`, `POST /viewer/application/{application_id}/resume`, `POST /viewer/application/{application_id}/cover-letter` and `POST /viewer/apply-from-link`, each with a summary, a description and a tag that groups it with related endpoints, and SHALL describe no other operations.

#### Scenario: All endpoints listed
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains exactly those twenty-one operations, each with a non-empty summary, description and tag

#### Scenario: Health alias
- **WHEN** the OpenAPI document is fetched
- **THEN** `GET /healthz` and `GET /health` are both present, and their descriptions say they are equivalent

#### Scenario: Viewer page not an operation
- **WHEN** the OpenAPI document is fetched
- **THEN** it does not list `/viewer`

#### Scenario: Cover letter description
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /cover-letter` description says it always tailors to the posting, needs posting text, saves the PDF beside the resume, runs in the background and returns 202, and that the letter's path and text come from `GET /cover-letter/{application_id}/status`

#### Scenario: Background generation described
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /resume` and `POST /cover-letter` descriptions say the run continues after the response, that a request while a run is in progress starts no second run, and that the client polls the matching status endpoint, and neither tells the client to use a 10-minute timeout

#### Scenario: Status endpoints described
- **WHEN** the OpenAPI document is fetched
- **THEN** the two status endpoints are tagged with their POST endpoint (`resumes` and `cover letters`), require the API key, and their descriptions list the job states, say a restart marks a running job `failed`, and say they return no posting text

#### Scenario: Cover letter reads described
- **WHEN** the OpenAPI document is fetched
- **THEN** the `GET /application/{application_id}/cover-letter.pdf` description says where the letter is looked for, and the `GET /cover-letter/base.pdf` description says it serves the committed base letter unchanged and is never generated by the service; both are tagged with the other viewer reads
