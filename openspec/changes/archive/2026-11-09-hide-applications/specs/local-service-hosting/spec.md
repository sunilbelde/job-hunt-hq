# Spec Delta

## MODIFIED Requirements

### Requirement: Smoke test checks the docs listener
The smoke test SHALL check that the docs listener serves the reference page, the viewer page and an OpenAPI document with the twenty-three documented operations, in addition to its public-address checks. The docs listener SHALL be required: `DOCS_URL=off` SHALL be refused.

#### Scenario: Docs listener healthy
- **WHEN** the smoke test runs and the docs listener answers `/docs` and `/viewer` with 200 and `/openapi.json` with the twenty-three operations
- **THEN** the docs check passes

#### Scenario: Docs listener missing
- **WHEN** the docs listener does not answer `/docs` with 200
- **THEN** the smoke test fails before creating any application

#### Scenario: Wrong operation count
- **WHEN** the docs listener's OpenAPI document lists any number of operations other than twenty-three, such as the twenty-two from before the hide endpoint
- **THEN** the smoke test fails before creating any application

#### Scenario: Docs listener turned off
- **WHEN** the smoke test runs with `DOCS_URL=off`
- **THEN** it exits non-zero with a usage message before sending any request
