## MODIFIED Requirements

### Requirement: Per-request application logging
The system SHALL emit exactly one structured log line per `POST /application`, `PATCH /application/{application_id}` or `DELETE /application/{application_id}` request with event `application_request`, the HTTP `method`, HTTP status, duration and, when known, `application_id` and (for `POST`) whether it was a duplicate. It SHALL NOT log the API key or any request body field.

#### Scenario: New application log
- **WHEN** a new application is recorded
- **THEN** one log line records method `POST`, status 201, the `application_id`, `duplicate` false and the duration

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records the status and duration, with no key or body content

#### Scenario: Update log
- **WHEN** application 7 is updated to status `applied`
- **THEN** one log line records method `PATCH`, status 200, `application_id` 7 and the duration
- **AND** the line does not contain `applied` or any other body value

#### Scenario: Delete of unknown ID log
- **WHEN** an authenticated client deletes an ID that does not exist
- **THEN** one log line records method `DELETE` and status 404

#### Scenario: Job requests unaffected
- **WHEN** a client calls any application endpoint
- **THEN** no `resume_request` log line is emitted
- **AND** a `POST /resume` request emits no `application_request` log line
