# Spec Delta

## MODIFIED Requirements

### Requirement: Smoke test never starts a Claude run
The smoke test SHALL generate its resume for an application with no posting text. It SHALL check that `POST /resume` answers 202, then poll `GET /resume/{application_id}/status` on the public address until the job is `done`, with a bounded wait. It SHALL check that `match.status` is `no_job_description` and that the resume is a PDF. If it reuses a leftover application with posting text, it SHALL clear that text first. It SHALL request a cover letter and check for 422 and no cover letter file.

#### Scenario: Fresh smoke test
- **WHEN** the smoke test runs against a service with no leftover smoke-test application
- **THEN** `POST /resume` answers 202, the status endpoint reaches `done` without a Claude run, `match.status` is `no_job_description`, and the PDF is found under `OUTPUT_DIR` from the returned file name

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

## ADDED Requirements

### Requirement: Smoke test finds the PDF from its file name
The smoke test SHALL require `saved_path` to be exactly `SUNIL BELDE.pdf`, with no `/`. It SHALL check that the file at `<OUTPUT_DIR>/Smoke Test Co/<application_id>/<saved_path>` is a PDF, taking `OUTPUT_DIR` from the environment and defaulting to the service's default.

#### Scenario: Status returns a path
- **WHEN** the status endpoint's `saved_path` contains `/`
- **THEN** the smoke test fails, because the service is exposing a host path

#### Scenario: No file under OUTPUT_DIR
- **WHEN** no PDF exists at `<OUTPUT_DIR>/Smoke Test Co/<application_id>/<saved_path>`, for example because `OUTPUT_DIR` differs from the service's
- **THEN** the smoke test fails, says that `OUTPUT_DIR` must match the service's, and still deletes the application it created
