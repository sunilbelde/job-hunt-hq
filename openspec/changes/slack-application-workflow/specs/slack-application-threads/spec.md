# Spec Delta

## Purpose

Lets the owner run an application from one Slack thread: the service posts a report when the application's documents are ready, a fill can be started from the thread, and the form filler's questions and reports travel through the thread.

## ADDED Requirements

### Requirement: Slack settings
The service SHALL read the optional settings `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_OWNER_USER_ID` and `SLACK_API_BASE` (default `https://slack.com/api`). When the token or the channel is unset, the service SHALL post nothing to Slack, and every endpoint in this capability SHALL respond 503 with `{"ok": false, "reason": "slack_not_configured", "message": ...}`. Generation and the viewer SHALL work as before.

#### Scenario: Slack not configured
- **WHEN** `SLACK_BOT_TOKEN` is unset and a resume job finishes `done`
- **THEN** the job is recorded as before, no Slack call is made, and nothing is logged as a Slack error

#### Scenario: Fill without Slack configured
- **WHEN** an authenticated client calls `POST /application/{id}/fill` and `SLACK_CHANNEL_ID` is unset
- **THEN** the system responds 503 with `reason` `slack_not_configured`

### Requirement: Ready report trigger
After any generation job ends, the service SHALL post one report for the application to `SLACK_CHANNEL_ID` when its resume job is `done`, no generation job for it is `running`, and it has no Slack thread yet. Deciding and claiming SHALL happen in one store transaction, so an application never gets two reports. The service SHALL store the posted message's `ts` as the application's thread. A Slack failure SHALL never change the job's recorded outcome.

#### Scenario: Both documents finish
- **WHEN** an application's cover letter job ends `done` while its resume job is already `done`
- **THEN** one report is posted whose text contains the company, role, `App ID` line, viewer link and "resume ✓ · cover letter ✓", and the thread's `ts` is stored

#### Scenario: Resume done while cover letter still running
- **WHEN** a resume job ends `done` while the cover letter job is `running`
- **THEN** no report is posted yet

#### Scenario: Concurrent finishes
- **WHEN** the resume and cover letter jobs of one application finish at the same moment on two threads
- **THEN** exactly one report is posted

#### Scenario: Resume failed
- **WHEN** the resume job ends `failed` and the application has no thread
- **THEN** no report is posted

#### Scenario: Slack rejects the post
- **WHEN** Slack answers the report post with `ok: false` or the request fails
- **THEN** the job stays recorded as `done`, the failure is logged without message text, and no thread is stored, so a later job end can post the report

### Requirement: Ready report content
The report SHALL contain the company, the role, and the full application ID on its own line as `*App ID:* \`<id>\``. It SHALL show each document's state. It SHALL include whichever of these are present: match score (base → tailored), why it fits, location, work type, salary, sponsorship, posting link, and `http://127.0.0.1:8081/viewer#<id>`.

#### Scenario: Sparse application
- **WHEN** an application has no salary and no sponsorship information
- **THEN** the report leaves those lines out and still shows the `App ID` line and the viewer link

### Requirement: Follow-up posts in the thread
When a generation job ends for an application that already has a thread, the service SHALL reply in that thread with the job's kind and outcome (`done` with the new match score for a resume, or `failed` with the recorded error), and SHALL NOT post a new report.

#### Scenario: Regenerated resume
- **WHEN** a resume job ends `done` for an application that has a thread
- **THEN** a reply in that thread names the new match score and no new top-level message is posted

### Requirement: Manual report retry
`POST /application/{application_id}/slack-report` SHALL require the API key, SHALL post the report if the application has none and its resume job is `done`, and SHALL respond 200 with `{"ok": true, "thread_ts": ...}`. It SHALL respond 200 with the existing `thread_ts` and `"already_posted": true` when a thread exists, 409 `resume_not_ready` when the resume job is not `done`, 404 for an unknown ID, and 502 `slack_error` when Slack rejects the post.

#### Scenario: Retry after a Slack outage
- **WHEN** a report post failed earlier and the owner calls the endpoint with the key
- **THEN** the report is posted and its `thread_ts` returned

### Requirement: Fill from Slack
`POST /application/{application_id}/fill` SHALL require the API key and SHALL be served only on the local listener. It SHALL open (or find) the application's form-filling tab the same way the viewer's Fill form does, with the skill arguments `<id> slack`. It SHALL respond 200 `{"ok": true, "application_id", "tab_id", "tab_label", "already_open"}` and post a line in the thread saying the fill started, or that a session was already open.

#### Scenario: Owner asks Hermes to fill
- **WHEN** Hermes calls the endpoint with the key for an application with a thread and no open tab
- **THEN** a Herdr tab runs `claude --chrome '/job-application-form-filler <id> slack'`, the response has `already_open` false, and the thread gets a "fill started" line

#### Scenario: Public listener
- **WHEN** any client sends `POST /application/{id}/fill` to the public address
- **THEN** it receives 404

### Requirement: Fill errors
`POST /application/{application_id}/fill` SHALL respond 404 for an unknown ID, 409 `no_thread` when the application has no Slack thread, and 503 when Herdr is unavailable. In each of these cases it SHALL open no tab.

#### Scenario: No thread yet
- **WHEN** Hermes calls the endpoint for an application whose report was never posted
- **THEN** the system responds 409 with `reason` `no_thread` and no tab opens

### Requirement: Question batches
`POST /application/{application_id}/questions` SHALL require the API key and accept `{"questions": [...]}` with 1 to 4 questions. Each question has `question`, `header` (at most 12 characters), `options` (2 to 4, each with a `label` and an optional `description`), `multi_select` (default false) and `kind` (`normal` or `approval`, default `normal`). The service SHALL store the batch as `pending`, post it in the thread as a numbered list with lettered options, and respond 201 with `question_id`.

#### Scenario: Form filler asks two questions
- **WHEN** the form filler posts a batch of two normal questions
- **THEN** the response is 201 with a `question_id`, the thread shows both questions with lettered options, and `GET ...?status=pending` returns that batch

#### Scenario: Newer batch supersedes
- **WHEN** a second batch is posted while the first is pending
- **THEN** the first batch's status becomes `cancelled`

#### Scenario: Invalid batch
- **WHEN** a batch has five questions, or a question with one option
- **THEN** the system responds 422 naming the field, and nothing is posted

### Requirement: Question batch lifecycle
Posting a batch SHALL cancel any older pending batch for the same application. `GET /application/{id}/questions/{question_id}` SHALL return `status`, plus `answers` once answered. `GET /application/{id}/questions?status=pending` SHALL return the pending batch, if any. `DELETE /application/{id}/questions/{question_id}` SHALL cancel a pending batch. Question and answer text SHALL never be logged.

#### Scenario: Cancelled by the form filler
- **WHEN** the form filler deletes a pending batch
- **THEN** its status becomes `cancelled` and `GET ...?status=pending` returns none

### Requirement: Recording answers
`POST /application/{application_id}/questions/{question_id}/answers` SHALL require the API key and accept `{"answers": [...], "slack_message_ts": "..."}`, with one entry per question: a list of chosen option labels or free-text strings. It SHALL respond 409 `not_pending` for a batch that is not pending, and 422 when the number of answers differs from the number of questions. On success the batch SHALL become `answered` with `answered_at` set.

#### Scenario: Normal answer recorded
- **WHEN** Hermes records answers for a pending normal batch
- **THEN** the batch is `answered`, and the form filler's next `GET` returns the answers

#### Scenario: Answered twice
- **WHEN** Hermes records answers for a batch that is already answered
- **THEN** the system responds 409 and the stored answers are unchanged

### Requirement: Verified submit approval
For a batch with an `approval` question, the service SHALL read the message named by `slack_message_ts` from the thread through `conversations.replies` before accepting answers. It SHALL accept only a message from `SLACK_OWNER_USER_ID`, newer than the batch's post, whose text starts with `yes`, `approve` or `submit` or contains the chosen label; a declining answer (label starting `No`) needs only that message. Otherwise it SHALL respond 422 `approval_not_verified` and leave the batch pending.

#### Scenario: Owner declines
- **WHEN** the owner replies "no, I'll do it" and Hermes records "No, I'll do it myself" with that message's `ts`
- **THEN** the batch becomes `answered`

#### Scenario: Owner ID not configured
- **WHEN** `SLACK_OWNER_USER_ID` is unset and Hermes records an approval
- **THEN** the system responds 503 and the batch stays pending

#### Scenario: Owner approves
- **WHEN** the owner replies "yes, submit it" in the thread and Hermes records "Yes, agree and submit" with that message's `ts`
- **THEN** the batch becomes `answered`

#### Scenario: Relay claims approval without the owner
- **WHEN** Hermes records an approval with a `slack_message_ts` that belongs to a bot message, to another user, to a message older than the question, or that does not exist
- **THEN** the system responds 422 `approval_not_verified` and the batch stays pending

### Requirement: Updates into the thread
`POST /application/{application_id}/slack-update` SHALL require the API key and accept `{"text": "..."}` (non-empty, at most 20,000 characters). It SHALL post the text in the application's thread, split into messages of at most 3,500 characters on line boundaries, and SHALL respond 200 `{"ok": true, "messages": <count>}`, or 409 `no_thread` when there is no thread.

#### Scenario: Step 6 report posted
- **WHEN** the form filler posts a 5,000-character report
- **THEN** two messages appear in the thread in order, and the response says 2

### Requirement: New endpoints are local only and documented
Every endpoint in this capability SHALL be served only on the local listener, SHALL be absent from the public allowlist, and SHALL appear in the OpenAPI document with the API-key security scheme and its responses.

#### Scenario: Docs list the new operations
- **WHEN** a client reads `/openapi.json` on the local listener
- **THEN** each new operation is present with the API-key scheme
