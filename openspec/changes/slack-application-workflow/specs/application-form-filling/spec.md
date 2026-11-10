# Spec Delta

## ADDED Requirements

### Requirement: Slack mode questions
When invoked as `/job-application-form-filler <id> slack`, the form filler SHALL ask every question through `scripts/ask_slack.py` instead of AskUserQuestion. It SHALL `post` the batch it would have passed to AskUserQuestion, then `wait` for the answers, calling `wait` again each time it exits with code 3. Every other rule of the skill SHALL stay as it is: what may be submitted, which boxes may be ticked, and when the application is marked applied.

#### Scenario: Missing answer in Slack mode
- **WHEN** the form has a required question the sources don't answer, in a Slack-mode run
- **THEN** the skill posts it through `ask_slack.py post`, waits with `ask_slack.py wait`, and fills the answer it receives, with no AskUserQuestion call

#### Scenario: Long wait
- **WHEN** `ask_slack.py wait` exits with code 3 because no answer arrived within its timeout
- **THEN** the skill calls `wait` again for the same question ID and does not ask again or give up

### Requirement: Slack mode reports
In Slack mode the form filler SHALL post its Step 6 report and its final report to the application's thread through `POST /application/{id}/slack-update`, in addition to writing them in the session.

#### Scenario: Report reaches the thread
- **WHEN** a Slack-mode run reaches Step 6
- **THEN** the report is posted to the thread through `slack-update`

### Requirement: Approval questions marked in Slack mode
In Slack mode, the Step 7 "agree and submit" question and the "mark it applied anyway" question SHALL be posted with `kind` `approval`. The skill SHALL act on an approving answer only if it came back from the relay, which verifies it against the owner's Slack message.

#### Scenario: Agree and submit from Slack
- **WHEN** the owner has reviewed the form and Step 7 asks to tick the listed boxes and submit, in Slack mode
- **THEN** the question is posted with `kind` `approval`, and the skill ticks the boxes and submits only after `wait` returns "Yes, agree and submit"

### Requirement: Cancel on takeover
If the owner types in the Herdr tab while a Slack batch is pending, the skill SHALL cancel that batch with `DELETE /application/{id}/questions/{question_id}` before following the owner's typed instruction.

#### Scenario: Owner steps in at the Mac
- **WHEN** a batch is pending and the owner types "stop, I'll finish it" in the tab
- **THEN** the batch is cancelled and the skill stops as instructed
