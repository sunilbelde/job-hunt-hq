# Design

## Context

- **Generation.** Generation runs on daemon threads. `run_job` (`app/main.py`) calls `applications.finish_job(...)` and then logs one line. Resume and cover letter are independent rows in `generation_jobs`, and nothing records that both are done. `GET /applications` already returns each kind's job state through `list_with_reports`.
- **Form filler.** It is an interactive `claude --chrome '/job-application-form-filler <id>'` session in a Herdr tab, opened by `FormFillLauncher.start` (`app/form_filler.py`). Every question to the owner goes through AskUserQuestion in that tab (`SKILL.md`, "Asking the user"). The session has `Bash` and reads the API key from the repo's `.env`.
- **Hermes.** Hermes runs on the same Mac and is connected to Slack through Socket Mode with its own bot. In a channel it answers only when @mentioned. After that it follows the thread. When it is first mentioned in a thread, it loads the thread's earlier messages (including bot posts) as context. Its own bot's messages never start a turn.
- **Listeners.** Port 8081 is local-only. Port 8080 is public through Funnel and passes only the five allowlisted pairs.

## Goals / Non-Goals

**Goals:**
- One Slack thread per application, created by the service. The service is the only place that knows which thread belongs to which application.
- A fill started from Slack can be answered from Slack end to end, and the Herdr tab and Chrome stay available to the owner at any time.
- Submission still needs the owner's own words. A relaying LLM can't fake an approval.

**Non-Goals:**
- Replacing Hermes's Slack connection. The service only posts and reads; it never receives Slack events.
- Changing the viewer's Fill form flow, or anything on the public listener.

## Decisions

### The service posts to Slack directly, with the Hermes bot's token
The service calls `chat.postMessage` itself (stdlib `urllib`, as in `tailoring.py`'s subprocess style: no new dependency) using the same bot token Hermes uses. Posting via `hermes send` was considered: it needs no token in this repo, but it does not return the message `ts`, and the service needs the root `ts` to thread later posts. Because the poster is Hermes's own bot, Hermes treats these posts as its own: they never trigger a turn, but they do appear in the thread context it loads.

### "Documents finished" is decided after every job, under the store lock, and claimed once
After `finish_job`, `run_job` calls `notifier.after_job(application_id)`, guarded so that no exception escapes. The notifier calls `ApplicationStore.claim_slack_report(application_id)`, which runs under `BEGIN IMMEDIATE`. The claim succeeds only if all of these hold:
- the resume job is `done`;
- no job for the application is `running`;
- no `slack_threads` row exists for the application.

On success it inserts a row with `thread_ts` NULL and returns the application with its jobs and report. A concurrent second job that finishes therefore cannot post a second report. The notifier then posts the report and stores the `ts`. If the post fails, the notifier deletes the claim row, so the next job end (or a manual `POST /application/{id}/slack-report`) can retry. If the application already has a thread, any later job end is posted as a reply instead: for example "Cover letter generated" or "Resume regenerated: match 72 → 81" or "Cover letter failed: <recorded error>".

Why not wait for both documents? The viewer can generate only a resume, and Muse's cover letter can fail or be refused with 422. "Resume done and nothing still running" reports as soon as the owner has something to review. A cover letter that finishes later appears in the thread.

### Report format
The report is plain `mrkdwn` text with a short `blocks` section, following the owner's email-summary style:

```
*Ready for review:* Applied AI Engineer at Ramp
*App ID:* `0f6c…`  ·  *Match:* 64 → 82
*Why it fits:* …
*Location:* NYC (Hybrid) · *Salary:* $180–220k · *Sponsorship:* yes
*Posting:* <job_link>  ·  *Viewer:* http://127.0.0.1:8081/viewer#<id>
Documents: resume ✓ · cover letter ✓ (or "not generated" / "failed")
Reply here with "@Hermes fill form" to start the application.
```

The full `App ID` always appears on its own line in the same pattern, so Hermes, and a test, can read it from the thread's root message. Empty fields are left out. The viewer link works only on the Mac, as the owner accepted.

### Fill from Slack reuses the launcher
`POST /application/{application_id}/fill` takes the key and the body `{"mode": "slack"}`; `mode` is optional and defaults to `slack`. It needs an existing Slack thread for the application, otherwise it returns 409 `no_thread`. It calls `FormFillLauncher.start(..., mode="slack")`, which runs `claude --chrome '/job-application-form-filler <id> slack'`. The command is still built only from a parsed UUID and a fixed word. If a tab for the ID is already open, the endpoint returns `already_open: true`, and the service posts "A form-filling session is already open for this application" in the thread. The route is local-only, like the viewer's route, but keyed, because Hermes is an API client and not a same-origin page.

### Question relay: a store-backed queue, with Hermes as the relay
New table `fill_questions` with these columns:
- `id` (UUID)
- `application_id`
- `batch` (JSON: up to 4 questions, each with `question`, `header`, `options[]` of 2 to 4 `{label, description}`, `multi_select`, `kind` `normal|approval`)
- `status` (`pending|answered|cancelled`)
- `slack_ts`, the posted message
- `answers` (JSON: one entry per question, each a list of chosen labels or free text)
- `approval_message_ts`
- `created_at`, `answered_at`

Endpoints, all keyed and on 8081 only:
- `POST /application/{id}/questions`: the form filler posts a batch. The service stores it and posts it in the thread as a numbered list ("1. *Rula form: years of Python?* a) 3–5 (from your resume) b) 5+ ..."). It returns 201 `{question_id}`. A new batch cancels any older pending batch for the same application, so only one batch is pending per application.
- `GET /application/{id}/questions/{qid}`: the form filler polls this. It returns `status`, plus `answers` when answered.
- `GET /application/{id}/questions?status=pending`: Hermes reads what is waiting.
- `POST /application/{id}/questions/{qid}/answers`: Hermes records `{answers: [...], slack_message_ts}`. A second answer to an answered batch returns 409.
- `POST /application/{id}/slack-update`: the form filler posts `{text}` (the Step 6 report, progress, the final report) into the thread. Text is capped at 3,500 characters per message and split if longer.

Hermes interprets the owner's free-text reply ("2, and say 5 years for Python") into the structured answers. That is what an LLM is good at, and it avoids requiring a rigid reply format.

Alternatives considered:
- (a) Hermes drives the Herdr pane directly, reading the terminal's question UI and typing keys. Rejected as fragile.
- (b) The service polls `conversations.replies` and parses answers itself. Rejected, because it duplicates Hermes, and Hermes would answer the same reply anyway.

### Approval answers are verified against Slack, not trusted from Hermes
A batch with `kind: approval` covers the Step 7 "agree and submit" question and the "mark applied anyway" question. Its answer should include `slack_message_ts`. When the relay cannot name the reply (Hermes may not show the model Slack message IDs), the service uses the owner's latest reply after the question instead. Before accepting it, the service checks all of these:
1. It calls `conversations.replies` for the thread and finds that `ts`.
2. The message's `user` is `SLACK_OWNER_USER_ID`.
3. The message is newer than the batch's posted `slack_ts`.
4. The message's text, lowercased and trimmed, starts with `yes`, `approve` or `submit`, or names the option label of the approving answer. A declining answer (a label starting with "No") needs only checks 1 to 3: refusing never needs proof.

If any check fails, the service returns 422 `approval_not_verified` and the batch stays pending. As a result, Hermes, or text injected into a form page, cannot submit an application without a real owner message saying so. The non-approval questions are trusted from Hermes, as they would be from the terminal today.

### Waiting in the form filler: `scripts/ask_slack.py`
The skill's Bash tool calls are limited in length, so `ask_slack.py post <id> <batch.json>` posts the batch and prints the `question_id`. Then `ask_slack.py wait <id> <qid> --timeout 540` polls every 5 s and prints the answers as JSON. If nothing arrives in time, it exits with code 3 and prints `pending`. The skill says to call `wait` again on exit code 3, indefinitely. The owner may answer hours later, and the Herdr tab just waits. The script reads the key from `.env` the same way the skill already does, and never prints it.

### Settings
These are in `app/settings.py`, all optional:
- `SLACK_BOT_TOKEN` (`xoxb-…`), `SLACK_CHANNEL_ID` (`C…`), `SLACK_OWNER_USER_ID` (`U…`).
- `SLACK_API_BASE`, defaulting to `https://slack.com/api`; tests point it at a fake.

When the token or channel is missing, the notifier is a no-op and the `/fill`, `/questions` and `/slack-update` routes return 503 `slack_not_configured`. When `SLACK_OWNER_USER_ID` is missing, approvals cannot be verified, so those return 503 too.

### Logging
The service logs one JSON line per Slack call: `{"event":"slack_post","application_id","kind":"report|reply|questions|update","ok":bool,"error"?}`. It never logs message text, question text, answers or tokens.

## Risks / Trade-offs

- **The bot token now lives in two places** (Hermes's `.env` and this repo's `.env`). Both are gitignored and on the same Mac. Rotating the token means updating both, and the README says so.
- **Slack is down or the token is revoked.** Then the report fails, the claim is released, and the failure is logged. Generation itself is unaffected. The next job end, or `POST /application/{id}/slack-report`, retries.
- **The owner answers in the Herdr tab while a Slack batch is pending.** In Slack mode the skill never shows AskUserQuestion, so this cannot happen. The owner can still type in the tab to stop or redirect the session. If they do, the skill cancels its pending batch (`DELETE /application/{id}/questions/{qid}`) so it does not linger in Slack.
- **Hermes misreads a normal answer.** That carries the same risk as a typo in the terminal. Each filled value still appears in the Step 6 report in the thread, and submission still needs a verified approval.
- **Several applications in flight.** Each has its own thread and pending batch. Hermes takes the App ID from the thread it is in, never from another one.
