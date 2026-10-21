# Spec Delta

## ADDED Requirements

### Requirement: Score breakdown from the gate
Whenever the service's own copy of the scripts scores a resume, it SHALL return, besides the score, the keyword and requirement coverage, each posting keyword with its importance and whether that resume covers it, and each requirement with its text, importance, assessed status, counted status and quoted evidence. When tailoring, it SHALL also return the keywords the judge rejected with the reason.

#### Scenario: Base kept
- **WHEN** the base resume scores at or above the threshold
- **THEN** the service has the base resume's full breakdown

#### Scenario: Tailored
- **WHEN** a tailored resume passes the gate
- **THEN** the service has the full breakdown for both the base and the tailored resume, the added keywords and the rejected keywords

#### Scenario: Unverified evidence
- **WHEN** a requirement is assessed `met` but its quote is not in the resume
- **THEN** its breakdown shows assessed status `met`, counted status `missing` and the reason

### Requirement: Generation report stored
After a resume is saved, the service SHALL store a report for the application holding the generation time, match status, threshold, the saved path, each scored resume's breakdown, the added keywords and the rejected keywords, replacing any earlier report. A generation that fails, or whose file cannot be saved, SHALL leave any earlier report unchanged.

#### Scenario: Tailored generation
- **WHEN** `POST /resume` saves a tailored resume
- **THEN** the application's report holds status `tailored`, both breakdowns, the added and the rejected keywords, and the saved path

#### Scenario: No posting text
- **WHEN** `POST /resume` saves the base resume because the posting text is missing or too short
- **THEN** the application's report holds status `no_job_description`, the saved path and no breakdown

#### Scenario: Failed regeneration
- **WHEN** an application already has a report and a new generation fails
- **THEN** its report is unchanged

### Requirement: Report storage does not change the resume response
Storing the report SHALL NOT change the `POST /resume` response body, status or log line. A failure to store the report after the PDF was saved SHALL be logged as a `report_store_error` event, with no report content, and SHALL NOT fail the request.

#### Scenario: Response unchanged
- **WHEN** `POST /resume` succeeds
- **THEN** its response body has the same fields and values as before reports were stored

#### Scenario: Report write fails
- **WHEN** the resume is saved but the report cannot be written
- **THEN** the response is still 201, and a `report_store_error` line without posting or resume text is logged

### Requirement: Breakdown is never logged
No log line SHALL contain keyword terms, requirement text or evidence quotes from a breakdown or a report.

#### Scenario: Tailoring logged
- **WHEN** a tailored generation completes
- **THEN** its log line carries only the existing scores, counts and codes
