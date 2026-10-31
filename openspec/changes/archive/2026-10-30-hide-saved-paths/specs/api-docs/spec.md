# Spec Delta

## ADDED Requirements

### Requirement: Saved file fields documented as file names
The OpenAPI document SHALL describe the `saved_path` field of both job status responses and of the application detail's report as the saved PDF's file name only, with no directory or path on the service host. No description or example in the document SHALL show an absolute path for it.

#### Scenario: Status field description
- **WHEN** the OpenAPI document is fetched
- **THEN** the `saved_path` property of the `GET /resume/{application_id}/status` and `GET /cover-letter/{application_id}/status` 200 responses is described as the file name only, null unless the job is `done`

#### Scenario: Report field description
- **WHEN** the OpenAPI document is fetched
- **THEN** the `saved_path` property of the `GET /application/{application_id}` report is described as the file name only

#### Scenario: No path in descriptions
- **WHEN** the OpenAPI document is fetched
- **THEN** no description of a `saved_path` property contains `/` or the words "absolute path"
