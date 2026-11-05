# Spec Delta

## ADDED Requirements

### Requirement: How an application was added
`POST /application` SHALL accept `added_via` as exactly `link` or `manual`, case-sensitive, defaulting to `manual` when absent. Any other value SHALL be rejected with 422 naming `added_via`, without writing to the store.

#### Scenario: Recorded by the workflow
- **WHEN** a body sets `added_via` to `link`
- **THEN** the row's `added_via` is `link`

#### Scenario: Not sent
- **WHEN** a body has no `added_via`
- **THEN** the row's `added_via` is `manual`

#### Scenario: Unknown value
- **WHEN** a body sets `added_via` to "linkedin"
- **THEN** the system responds 422 naming `added_via`, does not echo the value, and creates no row

#### Scenario: Wrong type or case
- **WHEN** a body sets `added_via` to null, a number or "Link"
- **THEN** the system responds 422 naming `added_via`

#### Scenario: Duplicate keeps the origin
- **WHEN** a posting recorded as `manual` is posted again with `added_via` `link`
- **THEN** the response is 200 with the existing ID and the row's `added_via` is still `manual`

### Requirement: Origin fixed once recorded
`added_via` SHALL NOT be updatable. A `PATCH /application/{application_id}` body containing it SHALL be rejected with 422 naming `added_via`, leaving the row unchanged, as for the other fields fixed at recording.

#### Scenario: Update refused
- **WHEN** an authenticated client sends `{"added_via": "link"}` to an existing application
- **THEN** the system responds 422 naming `added_via` and the row is unchanged

## MODIFIED Requirements

### Requirement: Application field rules
The body SHALL require `company`, `role` and `job_link` as non-empty strings, plus `posting_source_type`, `verification_method` and `official_apply_url` as strings. It SHALL accept `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain` and `full_job_description` as optional strings, and `added_via` as optional. Unknown fields SHALL be ignored, and no value SHALL be parsed or normalized.

#### Scenario: Client example accepted
- **WHEN** an authenticated client sends the client's example body with all fifteen fields as strings
- **THEN** the system accepts it

#### Scenario: Optional fields omitted
- **WHEN** a body contains only the required fields
- **THEN** it is accepted

#### Scenario: Missing job_link
- **WHEN** `job_link` is absent or an empty string
- **THEN** the system responds 422 naming `job_link`, and no row is created

#### Scenario: Wrong type
- **WHEN** `salary` is a number or `company` is null
- **THEN** the system responds 422 and no row is created

#### Scenario: Unknown field ignored
- **WHEN** a body includes an extra field such as `found: true`
- **THEN** it is accepted and the extra field is not stored

#### Scenario: Example without added_via still accepted
- **WHEN** a body has the fifteen fields and no `added_via`
- **THEN** it is accepted and the row's `added_via` is `manual`
