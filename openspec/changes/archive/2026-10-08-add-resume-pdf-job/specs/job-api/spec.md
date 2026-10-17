# Spec Delta

## MODIFIED Requirements

### Requirement: Job creation response
On success, `POST /jobs` SHALL respond 201 with a JSON body containing `job_id`, `url`, `expires_at` and `key`, where `url` is a pre-signed download link for the stored file and `key` is its object key.

#### Scenario: Successful job
- **WHEN** an authenticated client posts a valid job posting
- **THEN** the system responds 201 with `job_id`, `url`, `expires_at` (UTC, ISO 8601) and `key`
- **AND** opening `url` in a browser downloads the generated PDF before expiry

### Requirement: Stubbed output generation
For this release the system SHALL produce a PDF by rendering the baseline resume, without altering it based on the posting, via a generation interface that accepts the validated job posting and returns content bytes, a content type and a file extension.

#### Scenario: Stub output content
- **WHEN** a valid job is processed
- **THEN** the stored file is `application/pdf` with extension `pdf`
- **AND** it is a valid PDF whose content matches the baseline resume

## ADDED Requirements

### Requirement: Job posting body validation
The system SHALL accept as the `POST /jobs` body only a JSON object that validates as a job posting, and SHALL reject non-JSON, non-object, or invalid bodies with a 4xx status (422 for validation failures) without generating or storing anything.

#### Scenario: Malformed JSON
- **WHEN** an authenticated client sends a body that is not valid JSON
- **THEN** the system responds 4xx and no file is stored

#### Scenario: Non-object JSON
- **WHEN** an authenticated client sends a JSON array, string, number or null
- **THEN** the system responds 4xx and no file is stored

#### Scenario: Minimal valid posting accepted
- **WHEN** an authenticated client sends an object with only `company`, `role` and `full_job_description` as non-empty strings
- **THEN** the system accepts it for processing

#### Scenario: Arbitrary object rejected
- **WHEN** an authenticated client sends an object missing a required field, such as `{}`
- **THEN** the system responds 422 and no file is stored

### Requirement: Job posting field rules
The job posting body SHALL require `company`, `role` and `full_job_description` as non-empty strings and SHALL accept `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits` and `job_link` as optional strings, without parsing or normalizing any value.

#### Scenario: Optional fields omitted
- **WHEN** a posting omits every optional field
- **THEN** it is accepted

#### Scenario: Free-form values pass through
- **WHEN** `salary` is "$120k-$150k + equity", `date_posted` is "yesterday" and `job_link` is "not a url"
- **THEN** the posting is accepted unchanged

#### Scenario: Missing required field
- **WHEN** `role` is absent
- **THEN** the system responds 422 identifying the field and nothing is stored

#### Scenario: Empty required field
- **WHEN** `company` is an empty string
- **THEN** the system responds 422 and nothing is stored

#### Scenario: Wrong type
- **WHEN** a field such as `salary` is a number or `company` is null
- **THEN** the system responds 422 and nothing is stored

### Requirement: Render failure handling
When PDF rendering fails or exceeds its time limit, the system SHALL respond 500 with a generic message exposing no TeX output or paths, SHALL log the details server-side, and SHALL NOT upload anything.

#### Scenario: Render error
- **WHEN** the TeX compilation fails
- **THEN** the system responds 500 with a generic error body
- **AND** no object is written to storage
- **AND** the failure details are logged with the job id

## REMOVED Requirements

### Requirement: JSON object body validation
**Reason**: Any JSON object is no longer accepted; the body must now be a valid job posting.
**Migration**: Send the fields defined by "Job posting body validation" and "Job posting field rules"; arbitrary objects now return 422.
