# Proposal

## Why

Today the owner runs the whole application workflow from the Mac. Muse or a pasted link creates an application, the viewer shows when the tailored resume and cover letter are ready, the owner clicks **Fill form**, and then answers the form filler's questions in its Herdr tab. Nothing tells the owner when an application is ready for review, and every follow-up question needs the owner at the Mac.

The owner wants to run this loop from Slack, through the Hermes agent that is already connected to the workspace. Each application should get one thread in `#job-hunt-announcements`. The ready report starts the thread. In the thread the owner asks Hermes to fill the form, answers the form filler's questions, and approves the submission.

## What Changes

- **Ready report.** When an application's documents finish generating, the service posts one report to the configured Slack channel and remembers its thread. Documents count as finished when the resume job is `done` and no cover letter job is `running`; a cover letter is not expected for `linkedin_easy_apply`. The report shows company, role, App ID, the match score, why it fits, the job details (location, work type, salary, sponsorship, posting link) and a viewer link (`http://127.0.0.1:8081/viewer#<id>`). Later generation results for the same application, such as a regenerated resume or a failed cover letter, are posted as replies in that thread, not as new reports.
- **Fill from Slack.** A keyed, local-only `POST /application/{application_id}/fill` starts the form filler in Slack mode: the same Herdr tab and `claude --chrome` session as the viewer button, with `slack` added to the skill arguments. The viewer button keeps working as today.
- **Question relay.** New keyed, local-only endpoints let the Slack-mode form filler post a batch of questions, which the service writes into the application's thread, and wait for the answers. Hermes reads the pending questions and records the owner's answers from the thread. The service also posts the form filler's progress and its Step 6 report into the thread.
- **Submit approval is checked against Slack.** The form filler's agree-and-submit question is marked as an approval. The service accepts an answer to it only if it names a Slack message in the thread, written by the configured owner, that the service reads back from Slack itself and finds saying yes. Hermes cannot approve a submission on its own.
- **Form filler skill: Slack mode.** With the `slack` argument, every AskUserQuestion becomes a call to a small helper script that posts the questions and waits for the answers, and each report is also posted to the thread. All other rules stay as they are: what may be submitted, which boxes may be ticked, and marking the application applied.
- **Configuration.** The new settings are `SLACK_BOT_TOKEN` (the Hermes app's bot token), `SLACK_CHANNEL_ID` and `SLACK_OWNER_USER_ID`. With no token or channel set, no reports are posted and the Slack fill endpoints return 503. Nothing else changes.
- **Hermes skill (outside this repo).** A `job-hunt` skill bound to the channel. It finds the App ID in the thread's report, starts a fill, relays answers, and answers status questions. Its key comes from macOS Keychain.

## Capabilities

### New Capabilities
- `slack-application-threads`: the ready report, the thread mapping, follow-up posts, the fill endpoint's Slack mode, the question relay endpoints with their storage, the checked submit approval, and the settings.

### Modified Capabilities
- `application-form-filling`: the form filler's Slack mode (questions through the relay, reports posted to the thread, approval questions marked as approvals).

## Out of scope

- Attaching the PDFs to Slack. The owner chose the viewer link instead.
- Starting applications from Slack (pasting a link in the channel). The apply-from-link flow runs as today. Its documents still get a ready report, but its form filler runs in its own tab as now.
- The public Funnel listener. None of the new endpoints are public.
- Slack interactive buttons. Answers are plain thread replies.

## Impact

- `app/slack.py` (new): Slack Web API client (`chat.postMessage`, `conversations.replies`), report formatting, and the notifier.
- `app/applications.py`: the `slack_threads` and `fill_questions` tables, plus the claim-once and question store methods.
- `app/main.py`: the hook after `finish_job` in `run_job`, the new keyed routes, and OpenAPI entries.
- `app/models.py`, `app/settings.py`, `.env.example`: new models and settings.
- `app/form_filler.py`: `fill_command` takes a mode.
- `.claude/skills/job-application-form-filler/SKILL.md` and `scripts/ask_slack.py` (new): Slack mode.
- Tests: new `tests/test_slack.py` and `tests/test_fill_questions.py`, plus updates to `tests/test_form_filler.py`, `tests/test_docs.py` (operation count), `tests/test_serve.py` (new paths are 404 on the public listener) and `tests/test_form_filler_skill.py`.
- `README.md`: a Slack section.
- Outside the repo: the Hermes `job-hunt` skill, Hermes's channel binding for `#job-hunt-announcements`, and Hermes chat switched to Claude.
