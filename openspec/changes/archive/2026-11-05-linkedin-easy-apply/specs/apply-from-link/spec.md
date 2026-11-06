# Spec Delta

## ADDED Requirements

### Requirement: LinkedIn links in one form
The workflow SHALL reduce a LinkedIn job link to `https://www.linkedin.com/jobs/view/<job id>/` before the stored check, whichever host or path it arrived on, so that every copy of one posting has one row. A LinkedIn link with no job ID SHALL be used as given.

#### Scenario: Link with a job view path
- **WHEN** the link is `https://in.linkedin.com/jobs/view/staff-engineer-at-acme-4012345678?trk=public`
- **THEN** the stored check uses `https://www.linkedin.com/jobs/view/4012345678/`

#### Scenario: Link from a search or recommendations page
- **WHEN** the link is `https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4012345678`
- **THEN** the stored check uses `https://www.linkedin.com/jobs/view/4012345678/`

### Requirement: Easy Apply exception to the official posting filter
When the owner chooses Easy Apply, the workflow SHALL NOT apply the profile document's official careers page filter, even though that section otherwise outranks the workflow's own list. Every other hard filter SHALL still apply, read from the LinkedIn posting.

#### Scenario: Official careers page filter skipped
- **WHEN** the owner chooses Easy Apply for a posting with no official posting
- **THEN** the posting is not dropped for lacking an official careers page, and the report says Easy Apply was accepted in its place

#### Scenario: Staffing firm on Easy Apply
- **WHEN** the owner chooses Easy Apply and the LinkedIn posting comes from a staffing firm for an unnamed client
- **THEN** the workflow drops it, reports why, and records nothing

#### Scenario: No full description
- **WHEN** the owner chooses Easy Apply and the full posting text cannot be read from the public page
- **THEN** the workflow drops it and records nothing

### Requirement: Easy Apply ends after the resume
For an application whose `posting_source_type` is `linkedin_easy_apply`, new or already stored, the workflow SHALL stop after the resume. It SHALL NOT open any application form, SHALL NOT run the form filler, and SHALL NOT start Easy Apply or submit anything on LinkedIn. The owner applies.

#### Scenario: Newly recorded
- **WHEN** the resume is done for a newly recorded Easy Apply application
- **THEN** no cover letter check runs, the form filler is not run, and the workflow goes to its report and the Submitted question

#### Scenario: Stored application
- **WHEN** the link matches a stored `verified` application with `posting_source_type` `linkedin_easy_apply` and a saved resume
- **THEN** no official posting search runs, no resume is generated, and the workflow goes to its report and the Submitted question

### Requirement: Submitted question for Easy Apply
After its report, which SHALL name the saved resume file and its folder, the Easy Apply path SHALL ask through AskUserQuestion whether the owner has submitted the application, with the options "Yes, I submitted it" and "No, not submitted". The owner's answer SHALL be enough: the workflow SHALL NOT try to confirm it on LinkedIn.

#### Scenario: Question asked
- **WHEN** the report for an Easy Apply application at Acme has been given
- **THEN** the session asks "Have you submitted the Acme application?" with those two options

#### Scenario: Not submitted
- **WHEN** the owner answers "No, not submitted"
- **THEN** the status stays `verified`, both tabs stay open, and the session says running `/apply-from-link` on the link again asks once more

### Requirement: Easy Apply wrap-up
On "Yes, I submitted it" the workflow SHALL, in order, set the status to `applied`, close the Chrome tab this run opened, give a short final report, and close its Herdr tab if that tab's label ends with the application ID. It SHALL stop at the first step that fails, reporting it and leaving the tabs open, and SHALL close no other tab.

#### Scenario: Confirmed
- **WHEN** the owner confirms submission and the status update answers `applied`
- **THEN** the run's Chrome tab closes, the final report is given, and the Herdr tab closes last

#### Scenario: Status update fails
- **WHEN** the status update answers anything other than `applied`
- **THEN** the answer is reported with no API key in it and both tabs stay open

#### Scenario: Run opened no Chrome tab
- **WHEN** the workflow reached the question from a stored application without opening a Chrome tab
- **THEN** it skips that step and carries on with the rest of the wrap-up

#### Scenario: Outside Herdr
- **WHEN** the session is not running in Herdr, or its tab's label does not end with the application ID
- **THEN** no Herdr tab is closed and the session says so

## MODIFIED Requirements

### Requirement: Stored check before any work
The workflow SHALL look up the given link in the application store before reading the posting, and SHALL look up the official link again once it is resolved, using the dedupe key both times. A stored application SHALL skip resolving, filtering and recording, and SHALL continue with whichever documents it is missing.

#### Scenario: Link already stored
- **WHEN** the given link matches a stored application that has a saved resume, and it is not an Easy Apply application
- **THEN** no new application is recorded, no resume is generated, and the workflow continues at the cover letter check

#### Scenario: Stored without a resume
- **WHEN** the given link matches a stored application with no saved resume
- **THEN** the workflow generates its resume and continues

#### Scenario: Stored under its official link
- **WHEN** a LinkedIn link does not match, but the official posting it resolves to does
- **THEN** the workflow uses that stored application and records nothing new

#### Scenario: Already in progress or finished
- **WHEN** the stored application's status is anything other than `verified`
- **THEN** the workflow reports the status and stops without generating or filling anything

### Requirement: Resume generated before the form
The workflow SHALL generate the resume through `POST /resume` when the application has none, and SHALL wait until the job's status is `done` before going further. A `failed` job SHALL stop the workflow with the job's error reported.

#### Scenario: Resume done
- **WHEN** `GET /resume/<id>/status` reports `done` and it is not an Easy Apply application
- **THEN** the workflow continues to the cover letter check

#### Scenario: Resume failed
- **WHEN** the job reports `failed`
- **THEN** the workflow reports the error, does not open the form filler, and leaves the application recorded

### Requirement: Cover letter only when the form asks for one
The workflow SHALL open the form and generate a cover letter through `POST /cover-letter` only when the form has a cover letter field, required or optional, and the application has no saved letter. A form with no such field SHALL get no letter. An Easy Apply application has no form the workflow can open, and SHALL get no letter from the workflow.

#### Scenario: Form has the field
- **WHEN** the form has an optional cover letter field and no letter is saved
- **THEN** the workflow generates the letter and waits for `done` before the handoff

#### Scenario: No field
- **WHEN** the form has no cover letter field
- **THEN** no cover letter job is started

#### Scenario: Letter already saved
- **WHEN** the form has the field and the application already has a saved letter
- **THEN** no cover letter job is started

#### Scenario: Letter failed
- **WHEN** the cover letter job reports `failed`
- **THEN** the workflow reports the error and hands off, so the form filler's report shows the missing letter

#### Scenario: Field found while filling
- **WHEN** the field first appears on a later page of a multi-page form
- **THEN** the workflow generates the letter and attaches it, or gives the owner its file to attach by hand

#### Scenario: Easy Apply application
- **WHEN** the application is an Easy Apply application
- **THEN** no form is opened and no cover letter job is started

### Requirement: Unresolved posting goes to the owner
When no official posting is found, the workflow SHALL ask the owner to supply the official link, to sign in to the source site in the Chrome window and retry, or to drop the posting. For a LinkedIn link it SHALL also offer the option that the posting is LinkedIn Easy Apply. This answer SHALL be the only way Easy Apply is detected, and the workflow SHALL NOT infer it from the page. It SHALL NOT type or ask for a password, and SHALL record nothing until an official posting is found or the owner chooses Easy Apply.

#### Scenario: Owner supplies the link
- **WHEN** no official posting is found and the owner supplies an official link
- **THEN** the workflow continues with that link, starting with the stored check

#### Scenario: Owner drops it
- **WHEN** the owner chooses to drop the posting
- **THEN** nothing is recorded and the workflow stops

#### Scenario: Owner chooses Easy Apply
- **WHEN** no official posting is found for a LinkedIn link and the owner chooses Easy Apply
- **THEN** the workflow continues to the hard filters with the LinkedIn posting

#### Scenario: Aggregator link
- **WHEN** no official posting is found for an Indeed link
- **THEN** the question does not offer Easy Apply

#### Scenario: Official posting found
- **WHEN** an official posting matching the LinkedIn link's company and role is found
- **THEN** the workflow uses it, does not ask the question, and records nothing as Easy Apply

### Requirement: Hard filters applied before recording
The workflow SHALL apply the hard filters to the official posting, or to the LinkedIn posting when the owner chose Easy Apply, before recording it, and SHALL take the pay floor and other thresholds from the profile document's Hard filters section. If the profile document cannot be read, it SHALL stop without recording.

#### Scenario: Profile document missing
- **WHEN** the profile document cannot be read
- **THEN** the workflow stops, says so, and records nothing

### Requirement: Application recorded with its origin
The workflow SHALL record a posting that passes the filters through `POST /application` with `added_via` `link`, the official link as `job_link` and the full posting text as `full_job_description`. An applicant tracking system posting SHALL use `recruiting_platform`, `official_apply_match` and an `official_apply_url` equal to `job_link`. An employer site posting SHALL use `employer_site`, `employer_site` and an empty `official_apply_url`. An Easy Apply posting SHALL use the reduced LinkedIn link as `job_link`, with `linkedin_easy_apply`, `owner_confirmed` and an empty `official_apply_url`.

#### Scenario: Ashby posting
- **WHEN** the official posting is on `jobs.ashbyhq.com`
- **THEN** the row has `posting_source_type` `recruiting_platform` and `official_apply_url` equal to `job_link`

#### Scenario: Custom careers page
- **WHEN** the official posting is on the employer's own careers page
- **THEN** the row has `posting_source_type` `employer_site` and an empty `official_apply_url`

#### Scenario: Easy Apply posting
- **WHEN** the owner chose Easy Apply and the posting passed the filters
- **THEN** the row has `added_via` `link`, `posting_source_type` `linkedin_easy_apply`, `verification_method` `owner_confirmed`, an empty `official_apply_url` and the LinkedIn link as `job_link`

#### Scenario: Recording fails
- **WHEN** `POST /application` answers anything but 200 or 201
- **THEN** the workflow reports the answer, with no API key in it, and stops

### Requirement: Handoff to the form filler
Except for an Easy Apply application, the workflow SHALL finish by running `job-application-form-filler` with the application ID in the same session, and SHALL pass no submit instruction, so the form filler's own rules for filling, review and submitting apply. If that skill is not installed, the workflow SHALL report the application ID and stop.

#### Scenario: Handoff
- **WHEN** the documents are ready for application `<id>`
- **THEN** the session runs `/job-application-form-filler <id>` and nothing is submitted unless the owner approves it there

#### Scenario: Form filler missing
- **WHEN** the form filler skill is not installed
- **THEN** the workflow reports the application ID and that the documents are ready

#### Scenario: Easy Apply application
- **WHEN** the resume is ready for an application with `posting_source_type` `linkedin_easy_apply`
- **THEN** the session does not run the form filler

### Requirement: Workflow report
The workflow SHALL say in its session which link it started from, which official posting it used, how it was resolved, each filter's outcome, the application ID, and whether the application was new or already stored. For Easy Apply it SHALL say the owner chose Easy Apply in place of an official posting, and that no cover letter was generated.

#### Scenario: Passed
- **WHEN** a LinkedIn link resolves to an Ashby posting and passes every filter
- **THEN** the session shows both links, the filter outcomes and the new application ID before the handoff

#### Scenario: Easy Apply
- **WHEN** an Easy Apply posting passes the other filters and its resume is done
- **THEN** the session shows the LinkedIn link, the filter outcomes, the application ID and the resume file before the Submitted question
