# Spec Delta

## MODIFIED Requirements

### Requirement: Posting source and verification method values
`posting_source_type` SHALL be exactly `recruiting_platform`, `employer_site` or `linkedin_easy_apply`, and `verification_method` SHALL be exactly `official_apply_match`, `employer_site` or `owner_confirmed`. Any other value SHALL be rejected with 422.

#### Scenario: Unknown source type
- **WHEN** `posting_source_type` is "linkedin"
- **THEN** the system responds 422 naming `posting_source_type`

#### Scenario: Case-sensitive values
- **WHEN** `verification_method` is "Official_Apply_Match"
- **THEN** the system responds 422 naming `verification_method`

### Requirement: Source type and method consistency
`recruiting_platform` SHALL be paired only with `official_apply_match`, and `official_apply_url` SHALL then equal `job_link` byte-for-byte. `employer_site` SHALL be paired only with `employer_site`, and `official_apply_url` SHALL then be the empty string. `linkedin_easy_apply` SHALL be paired only with `owner_confirmed`, and `official_apply_url` SHALL then be the empty string. Any other combination SHALL be rejected with 422.

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

#### Scenario: Easy Apply with empty apply URL
- **WHEN** `posting_source_type` is `linkedin_easy_apply`, `verification_method` is `owner_confirmed` and `official_apply_url` is ""
- **THEN** the body is accepted and the row keeps those values

#### Scenario: Easy Apply with apply URL
- **WHEN** `posting_source_type` is `linkedin_easy_apply` and `official_apply_url` is non-empty
- **THEN** the system responds 422 naming `official_apply_url`

#### Scenario: Easy Apply with another method
- **WHEN** `posting_source_type` is `linkedin_easy_apply` and `verification_method` is `official_apply_match`
- **THEN** the system responds 422 naming `verification_method`

#### Scenario: Owner confirmed on another source
- **WHEN** `verification_method` is `owner_confirmed` and `posting_source_type` is `recruiting_platform` or `employer_site`
- **THEN** the system responds 422 naming `verification_method`
