## ADDED Requirements

### Requirement: Submit by default
`/job-application-form-filler <id>` SHALL submit the application on its own by default, including when started by the viewer's Fill form button or the apply-from-link handoff. No submit word in the request SHALL be needed. Permission SHALL NOT carry over to another run, form or conversation beyond this standing default.

#### Scenario: Plain invocation
- **WHEN** the owner or the Fill form button runs `/job-application-form-filler <id>` and no guardrail stops the run
- **THEN** the form filler fills the form, ticks the required agreement boxes, submits it once, confirms it went through and marks the application applied

#### Scenario: Started from apply-from-link
- **WHEN** the apply-from-link handoff runs the form filler with only the ID
- **THEN** the same submit-by-default flow applies

### Requirement: Review-first opt-out
`/job-application-form-filler <id> review` SHALL keep the review-first flow: fill the form, report, leave agreement boxes unticked, and submit only after the owner reviews the form and approves the exact boxes through AskUserQuestion.

#### Scenario: Review keyword
- **WHEN** the request is `/job-application-form-filler <id> review`
- **THEN** the form filler does not submit or tick agreement boxes before the owner's approval

### Requirement: Agreement boxes ticked by the form filler
In submit-by-default mode the form filler SHALL tick the consent, privacy, GDPR, terms and "I certify" boxes the form needs, and read each state back. It SHALL leave optional marketing opt-ins unticked: job alerts, newsletters, SMS, talent community and sharing with other employers.

#### Scenario: Required terms box
- **WHEN** the form will not submit without a terms or "I certify" box ticked
- **THEN** the form filler ticks it and reads the state back

#### Scenario: Marketing opt-in
- **WHEN** the form offers an optional job alerts, newsletter, SMS, talent community or share-with-other-employers box
- **THEN** the form filler leaves it unticked

### Requirement: Self-review before submitting
Before submitting, the form filler SHALL read back every field's final value and check each drafted open-ended answer against the sources and the drafting style rules, including no dashes as punctuation, and fix what fails. Drafted answers SHALL be submitted without the owner's review and SHALL be listed in full in the final report.

#### Scenario: Draft breaks a style rule
- **WHEN** a drafted answer contains an em dash or states a fact no source gives
- **THEN** the form filler corrects it before submitting

#### Scenario: Final report
- **WHEN** a form is submitted
- **THEN** the final report lists every drafted open-ended answer in full

### Requirement: Guardrails stop the run
In submit-by-default mode the form filler SHALL NOT submit, and SHALL ask the owner with AskUserQuestion, when any of these holds: a required answer the sources do not give (a required salary question included); a red flag from the report's red-flag list (pay below the floor, sponsorship refused, not the company's site or its ATS, wrong company or role, an attached document's contact email mismatch, a cover letter field with no generated letter); files not attached for this application ID; a sign-in, CAPTCHA or bot check; a validation error that does not clear after one fix; an agreement beyond the standard application terms, meaning anything that costs money, an employment contract or a non-compete.

#### Scenario: Required salary question
- **WHEN** the form requires a salary answer the sources do not give
- **THEN** the form filler asks with AskUserQuestion and does not submit

#### Scenario: Red flag
- **WHEN** the base pay is below the profile document's pay floor
- **THEN** the form filler does not submit and asks the owner

#### Scenario: Files not attached
- **WHEN** the Tailored Attach status is not for this application ID
- **THEN** the form filler does not submit and asks the owner

#### Scenario: CAPTCHA
- **WHEN** the form shows a CAPTCHA or bot check
- **THEN** the form filler does not solve it and asks the owner

#### Scenario: Beyond standard terms
- **WHEN** the form asks the applicant to agree to a fee, an employment contract or a non-compete
- **THEN** the form filler does not tick it, does not submit, and asks the owner

### Requirement: Confirmation, applied status and wrap up
After submitting once, the form filler SHALL confirm from the page that the application went through. Only then SHALL it mark the application applied, update the profile document with any new answers, close the form's Chrome tab and its own Herdr tab as today. On an error or an unclear page it SHALL NOT retry, SHALL NOT mark it applied, and SHALL report what the page shows.

#### Scenario: Confirmed
- **WHEN** the page shows a thank-you or received confirmation after submitting
- **THEN** the application is marked applied and the wrap-up runs

#### Scenario: Unclear result
- **WHEN** the page shows nothing clear after submitting
- **THEN** the application is not marked applied and the form is not submitted again
