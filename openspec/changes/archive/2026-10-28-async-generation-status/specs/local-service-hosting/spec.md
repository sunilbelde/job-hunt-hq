# Spec Delta

## MODIFIED Requirements

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the fifteen documented operations, in addition to its public-address checks.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the fifteen operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

#### Scenario: Wrong operation count
- **WHEN** the docs listener's OpenAPI document lists any number of operations other than fifteen, such as the thirteen from before the status endpoints
- **THEN** the smoke test fails before creating any application

### Requirement: Smoke test never starts a Claude run
The smoke test SHALL generate its resume for an application with no posting text. It SHALL check that `POST /resume` answers 202, then poll `GET /resume/{application_id}/status` on the public address until the job is `done`, with a bounded wait. It SHALL check that `match.status` is `no_job_description` and that `saved_path` is a PDF. If it reuses a leftover application with posting text, it SHALL clear that text first. It SHALL request a cover letter and check for 422 and no cover letter file.

#### Scenario: Fresh smoke test
- **WHEN** the smoke test runs against a service with no leftover smoke-test application
- **THEN** `POST /resume` answers 202, the status endpoint reaches `done` without a Claude run, and `match.status` is `no_job_description`

#### Scenario: Leftover application with posting text
- **WHEN** an earlier version of the smoke test left its application with posting text
- **THEN** the smoke test clears that text before requesting the resume

#### Scenario: Job fails or never finishes
- **WHEN** the resume job is reported `failed`, or is still `running` when the wait runs out
- **THEN** the smoke test fails and still deletes the application it created

#### Scenario: Status endpoint missing on the public address
- **WHEN** `GET /resume/{application_id}/status` on the public address answers 404 for the application the smoke test just requested a resume for
- **THEN** the smoke test fails

#### Scenario: Cover letter refused without posting text
- **WHEN** the smoke test requests a cover letter for its application
- **THEN** the service answers 422, no Claude run starts, and no cover letter file appears in the application's folder
