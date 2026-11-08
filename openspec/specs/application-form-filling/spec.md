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
