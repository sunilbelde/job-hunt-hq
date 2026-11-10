# application-form-filling Specification

## Purpose

How the job application form filler takes the owner's contact details from the profile document, and checks that the
documents it attaches agree with them before the owner submits.

## Requirements

### Requirement: Contact email from the profile document
The form filler SHALL fill every email field on an application form with the `Email` row of the owner's profile
document, even when the tailored resume, cover letter, `PROFILE.md` or `BASE.tex` shows a different address.

#### Scenario: Profile document has the new address
- **WHEN** the profile document's `Email` row holds the new address and the form has an email field
- **THEN** the form filler types the new address into it

#### Scenario: Attached resume still shows an older address
- **WHEN** the tailored resume shows an address that differs from the profile document's `Email` row
- **THEN** the email field still gets the profile document's address

### Requirement: Attached documents checked against the contact email
The form filler SHALL compare the contact email shown on the tailored resume and on the cover letter, if one is
attached, with the profile document's `Email` row. Any mismatch SHALL be listed among the review report's red flags,
naming the document, with a suggestion to generate it again before submitting.

#### Scenario: Resume email differs
- **WHEN** the tailored resume's header shows an email other than the profile document's `Email` row
- **THEN** the red flags include a contact email mismatch for the resume and suggest generating the resume again

#### Scenario: Cover letter email differs
- **WHEN** an attached cover letter's header shows an email other than the profile document's `Email` row
- **THEN** the red flags include a contact email mismatch for the cover letter

#### Scenario: Documents agree
- **WHEN** every attached document shows the profile document's email
- **THEN** no contact email red flag is reported

#### Scenario: Email not readable from a document
- **WHEN** no email address can be read from an attached document
- **THEN** the report says the check could not be made for that document, and no mismatch is reported for it

### Requirement: No personal contact details in the skill
The form filler's skill file SHALL NOT contain the owner's email address, old or new. The address SHALL be read from
the profile document every time the skill runs.

#### Scenario: Skill file contents
- **WHEN** the skill file is searched for an email address belonging to the owner
- **THEN** none is found

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
