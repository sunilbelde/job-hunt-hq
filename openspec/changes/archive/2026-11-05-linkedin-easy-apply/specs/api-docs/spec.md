# Spec Delta

## ADDED Requirements

### Requirement: Easy Apply values documented
The OpenAPI document SHALL list `linkedin_easy_apply` among the allowed `posting_source_type` values and `owner_confirmed` among the allowed `verification_method` values in the `POST /application` body, SHALL state their pairing and empty `official_apply_url` in that operation's description, and SHALL list `posting_source_type` in the `GET /applications` entry schema. The number of documented operations SHALL NOT change.

#### Scenario: Recording body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `POST /application` body's `posting_source_type` values are `recruiting_platform`, `employer_site` and `linkedin_easy_apply`, and its `verification_method` values are `official_apply_match`, `employer_site` and `owner_confirmed`

#### Scenario: Pairing rule
- **WHEN** the `POST /application` description is read
- **THEN** it says `linkedin_easy_apply` requires `owner_confirmed` and an empty `official_apply_url`

#### Scenario: List entry
- **WHEN** the OpenAPI document is fetched
- **THEN** the `GET /applications` entry schema lists `posting_source_type`

#### Scenario: Update body
- **WHEN** the OpenAPI document is fetched
- **THEN** the `PATCH /application/{application_id}` body does not list `posting_source_type` or `verification_method`
