# Spec Delta

## MODIFIED Requirements

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the eleven documented operations, in addition to its public-address checks.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the eleven operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

### Requirement: Smoke test never starts a Claude run
The smoke test SHALL generate its resume for an application with no posting text and check that `match.status` is `no_job_description`. If it reuses a leftover application that has posting text, it SHALL clear that text before generating, so it never starts a Claude run. For the same application it SHALL request a cover letter and check that the service answers 422 and writes no cover letter file.

#### Scenario: Fresh smoke test
- **WHEN** the smoke test runs against a service with no leftover smoke-test application
- **THEN** the resume is generated without a Claude run and `match.status` is `no_job_description`

#### Scenario: Leftover application with posting text
- **WHEN** an earlier version of the smoke test left its application with posting text
- **THEN** the smoke test clears that text before requesting the resume

#### Scenario: Cover letter refused without posting text
- **WHEN** the smoke test requests a cover letter for its application
- **THEN** the service answers 422, no Claude run starts, and no cover letter file appears in the application's folder
