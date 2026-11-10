## MODIFIED Requirements

### Requirement: Handoff to the form filler
Except for an Easy Apply application, the workflow SHALL finish by running `job-application-form-filler` with the application ID in the same session, and SHALL pass nothing else, no submit instruction and no `review`, so the form filler's own default applies: it fills, reviews, agrees to the standard terms and submits on its own unless a guardrail stops it. If that skill is not installed, the workflow SHALL report the application ID and stop.

#### Scenario: Handoff
- **WHEN** the documents are ready for application `<id>`
- **THEN** the session runs `/job-application-form-filler <id>` and the form filler submits on its own unless one of its guardrails stops it

#### Scenario: Form filler missing
- **WHEN** the form filler skill is not installed
- **THEN** the workflow reports the application ID and that the documents are ready

#### Scenario: Easy Apply application
- **WHEN** the resume is ready for an application with `posting_source_type` `linkedin_easy_apply`
- **THEN** the form filler is not run
