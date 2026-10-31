# Spec Delta

## ADDED Requirements

### Requirement: Viewer write endpoints documented
The OpenAPI document SHALL tag `PATCH /viewer/application/{application_id}` and `DELETE /viewer/application/{application_id}` `viewer`, mark them as needing no API key, and describe the status-only request body with its allowed values. Their descriptions SHALL say they are served only where the viewer is, refuse cross-site browser requests, and that the delete keeps generated files.

#### Scenario: Write endpoints listed
- **WHEN** the OpenAPI document is fetched
- **THEN** both viewer write operations are tagged `viewer`, have no security requirement, and their descriptions say they are served only with the viewer and refuse cross-site requests

#### Scenario: Status body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `PATCH /viewer/application/{application_id}` request body requires `status` and lists exactly `verified`, `applied`, `interviewing`, `offer`, `rejected` and `withdrawn`, with an example the endpoint accepts

#### Scenario: Error statuses
- **WHEN** the OpenAPI document is fetched
- **THEN** `PATCH /viewer/application/{application_id}` lists 200, 403, 404, 422 and 503, and `DELETE /viewer/application/{application_id}` lists 200, 403, 404 and 503

#### Scenario: Delete keeps files
- **WHEN** the OpenAPI document is fetched
- **THEN** the `DELETE /viewer/application/{application_id}` description says generated resume and cover letter files are kept

## MODIFIED Requirements

### Requirement: Docs disabled by default
When API docs are disabled, which is the default, the system SHALL NOT serve `/docs`, `/redoc`, `/docs/oauth2-redirect`, `/openapi.json`, `/viewer`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `GET /resume/base.pdf`, `GET /cover-letter/base.pdf`, `PATCH /viewer/application/{application_id}` or `DELETE /viewer/application/{application_id}`. A request to any of them SHALL be handled as an unknown path.

#### Scenario: Default configuration
- **WHEN** the service runs without API docs enabled and a client requests `GET /docs`, `GET /redoc` or `GET /openapi.json`
- **THEN** each responds 404 and reveals no endpoint list or schema

#### Scenario: Viewer and read endpoints off
- **WHEN** the service runs without API docs enabled and a client sends a valid `X-API-Key` to `GET /viewer`, `GET /applications`, `GET /application/{id}`, `GET /application/{id}/resume.pdf`, `GET /application/{id}/cover-letter.pdf`, `GET /resume/base.pdf` or `GET /cover-letter/base.pdf`
- **THEN** each responds 404 and returns no application, report or file content

#### Scenario: Viewer writes off
- **WHEN** the service runs without API docs enabled and a client sends `PATCH /viewer/application/{id}` or `DELETE /viewer/application/{id}` for an existing application, with or without a valid `X-API-Key`
- **THEN** each responds 404 and the application is unchanged

#### Scenario: API unaffected when disabled
- **WHEN** API docs are disabled
- **THEN** `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume` and `POST /cover-letter` behave exactly as they do with docs enabled

### Requirement: Documented endpoint coverage
The OpenAPI document SHALL describe `GET /health`, `GET /healthz`, `POST /application`, `PATCH /application/{application_id}`, `DELETE /application/{application_id}`, `POST /resume`, `GET /resume/{application_id}/status`, `POST /cover-letter`, `GET /cover-letter/{application_id}/status`, `GET /applications`, `GET /application/{application_id}`, `GET /application/{application_id}/resume.pdf`, `GET /application/{application_id}/cover-letter.pdf`, `GET /resume/base.pdf`, `GET /cover-letter/base.pdf`, `PATCH /viewer/application/{application_id}` and `DELETE /viewer/application/{application_id}`, each with a summary, a description and a tag that groups it with related endpoints, and SHALL describe no other operations.

#### Scenario: All endpoints listed
- **WHEN** the OpenAPI document is fetched
- **THEN** it contains exactly those seventeen operations, each with a non-empty summary, description and tag

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
