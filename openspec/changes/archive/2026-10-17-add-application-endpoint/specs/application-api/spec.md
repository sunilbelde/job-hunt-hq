# Spec Delta

## Purpose

Defines the HTTP interface through which an authenticated client records verified job applications and receives a stable local ID for each, deduplicated on the posting's link.

## ADDED Requirements

### Requirement: API key authentication on application recording
The system SHALL require the `X-API-Key` header on `POST /application` to equal the configured API key, and SHALL respond 401 with `{"ok": false, "message": ...}` otherwise, before reading the body or touching the application store.

#### Scenario: Missing key
- **WHEN** a client sends `POST /application` without `X-API-Key`
- **THEN** the system responds 401 with `ok` false and a `message`
- **AND** no row is created

#### Scenario: Wrong key with malformed body
- **WHEN** a client sends `POST /application` with a wrong `X-API-Key` and a body that is not JSON
- **THEN** the system responds 401, not a validation error

### Requirement: Application body validation
The system SHALL accept as the `POST /application` body only a JSON object that satisfies the application field rules, and SHALL reject non-JSON, non-object or invalid bodies with 422 and `{"ok": false, "message": ...}` without writing to the store.

#### Scenario: Malformed JSON
- **WHEN** an authenticated client sends a body that is not valid JSON
- **THEN** the system responds 422 with `ok` false and a `message`, and no row is created

#### Scenario: Non-object JSON
- **WHEN** an authenticated client sends a JSON array, string, number or null
- **THEN** the system responds 422 with `ok` false and a `message`, and no row is created

#### Scenario: Message names fields, never values
- **WHEN** a request fails validation on `posting_source_type` with value "secret-ish-value"
- **THEN** the `message` names `posting_source_type`
- **AND** the response body does not contain "secret-ish-value"

### Requirement: Application field rules
The body SHALL require `company`, `role` and `job_link` as non-empty strings, plus `posting_source_type`, `verification_method` and `official_apply_url` as strings. It SHALL accept `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain` and `full_job_description` as optional strings. Unknown fields SHALL be ignored, and no value SHALL be parsed or normalized.

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

### Requirement: Posting source and verification method values
`posting_source_type` SHALL be exactly `recruiting_platform` or `employer_site`, and `verification_method` SHALL be exactly `official_apply_match` or `employer_site`. Any other value SHALL be rejected with 422.

#### Scenario: Unknown source type
- **WHEN** `posting_source_type` is "linkedin"
- **THEN** the system responds 422 naming `posting_source_type`

#### Scenario: Case-sensitive values
- **WHEN** `verification_method` is "Official_Apply_Match"
- **THEN** the system responds 422 naming `verification_method`

### Requirement: Source type and method consistency
`recruiting_platform` SHALL be paired only with `official_apply_match`, and `official_apply_url` SHALL then equal `job_link` byte-for-byte. `employer_site` SHALL be paired only with `employer_site`, and `official_apply_url` SHALL then be the empty string. Any other combination SHALL be rejected with 422.

#### Scenario: Recruiting platform with apply match
- **WHEN** `posting_source_type` is `recruiting_platform`, `verification_method` is `official_apply_match` and `official_apply_url` equals `job_link`
- **THEN** the body is accepted

#### Scenario: Apply URL differs from job_link
- **WHEN** `verification_method` is `official_apply_match` and `official_apply_url` differs from `job_link` in any byte, including only a trailing slash
- **THEN** the system responds 422 naming `official_apply_url`, and no row is created

#### Scenario: Employer site with empty apply URL
- **WHEN** `posting_source_type` and `verification_method` are both `employer_site` and `official_apply_url` is ""
- **THEN** the body is accepted

#### Scenario: Employer site with apply URL
- **WHEN** `posting_source_type` is `employer_site` and `official_apply_url` is non-empty
- **THEN** the system responds 422 naming `official_apply_url`

#### Scenario: Recruiting platform without apply URL
- **WHEN** `posting_source_type` is `recruiting_platform` and `official_apply_url` is ""
- **THEN** the system responds 422 naming `official_apply_url`

#### Scenario: Mismatched method
- **WHEN** `posting_source_type` is `recruiting_platform` and `verification_method` is `employer_site`
- **THEN** the system responds 422 naming `verification_method`

### Requirement: Application recording response
For a `job_link` not yet stored, `POST /application` SHALL create a row and respond 201 with exactly `{"ok": true, "application_id": <integer>}`, where `application_id` is the new row's ID.

#### Scenario: New application
- **WHEN** an authenticated client posts a valid body whose `job_link` is not in the store
- **THEN** the system responds 201 with `ok` true and an integer `application_id`
- **AND** the body has no other keys

### Requirement: Deduplication on job_link
When a row whose `job_link` has the same dedupe key already exists, `POST /application` SHALL respond 200 with `{"ok": true, "application_id": <existing ID>}`, SHALL NOT create a row, and SHALL NOT modify the existing row.

#### Scenario: Duplicate posting
- **WHEN** a valid body is posted twice with the same `job_link`
- **THEN** the second response is 200 with the same `application_id` as the first
- **AND** the store holds one row for that `job_link`

#### Scenario: Duplicate with different details
- **WHEN** a second request has the same `job_link` but a different `salary`
- **THEN** the response carries the existing `application_id` and the stored `salary` is unchanged

#### Scenario: Concurrent duplicates
- **WHEN** two requests with the same new `job_link` arrive at the same time
- **THEN** both succeed with the same `application_id` and only one row exists

#### Scenario: Same posting, decorated links
- **WHEN** requests carry `https://job-boards.greenhouse.io/acme/jobs/123`, `https://job-boards.greenhouse.io/acme/jobs/123/`, `https://job-boards.greenhouse.io/acme/jobs/123?gh_src=x&utm_source=y` and `HTTPS://Job-Boards.Greenhouse.io/acme/jobs/123#apply`
- **THEN** all four receive the same `application_id`

#### Scenario: Job ID in the query string
- **WHEN** requests carry `https://www.acme.com/careers?gh_jid=111` and `https://www.acme.com/careers?gh_jid=222`
- **THEN** they receive different IDs

#### Scenario: Stored link is the first one sent
- **WHEN** a posting is first recorded with `job_link` ending in `/123` and later re-sent as `/123/?utm_source=x`
- **THEN** the second response carries the existing ID and the stored `job_link` still ends in `/123`

### Requirement: Dedupe key normalization
The dedupe key of an http(s) `job_link` SHALL lowercase the scheme and host, drop a default port, drop the fragment and trailing path slashes, remove the query parameters `utm_*` (any case), `gh_src`, `source`, `src`, `ref`, `lever-source`, `lever-origin` and `trk`, and keep all other parameters byte-for-byte, sorted. Path case SHALL be kept. Any other value SHALL be its own key.

#### Scenario: Parameter order ignored
- **WHEN** two links differ only in the order of non-tracking query parameters `for=acme&token=12`
- **THEN** they have the same dedupe key

#### Scenario: Path case preserved
- **WHEN** two links differ only in the case of a path segment
- **THEN** they have different dedupe keys

#### Scenario: Encoded values untouched
- **WHEN** a kept parameter value contains `%2F`
- **THEN** the key contains `%2F` unchanged, so it differs from a link whose value contains a literal `/`

#### Scenario: Non-URL link
- **WHEN** `job_link` is "not a url"
- **THEN** it is accepted and deduplicated on the exact value

### Requirement: Application store failure handling
When the application store cannot be read or written, `POST /application` SHALL respond 503 with `{"ok": false, "message": ...}` using a generic message that exposes no path or exception text, and SHALL log the details server-side.

#### Scenario: Store unavailable
- **WHEN** writing the row raises a database or filesystem error
- **THEN** the system responds 503 with `ok` false and a generic `message`
- **AND** the body contains no filesystem path or exception text

### Requirement: Per-request application logging
The system SHALL emit exactly one structured log line per `POST /application` request with event `application_request`, HTTP status, duration and, when known, `application_id` and whether it was a duplicate. It SHALL NOT log the API key or any request body field.

#### Scenario: New application log
- **WHEN** a new application is recorded
- **THEN** one log line records status 201, the `application_id`, `duplicate` false and the duration

#### Scenario: Rejected request log
- **WHEN** a request fails authentication or validation
- **THEN** one log line records the status and duration, with no key or body content

#### Scenario: Job requests unaffected
- **WHEN** a client calls `POST /application`
- **THEN** no `job_request` log line is emitted
