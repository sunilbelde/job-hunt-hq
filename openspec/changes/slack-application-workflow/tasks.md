# Tasks

## 1. Settings and Slack client

- [x] 1.1 Add `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_OWNER_USER_ID` and `SLACK_API_BASE` (all optional) to `app/settings.py` and `.env.example`. Verify with `tests/test_settings.py`: the defaults, and that a missing token leaves Slack disabled.
- [x] 1.2 Create `app/slack.py` with a small stdlib client: `post_message(channel, text, thread_ts=None, blocks=None) -> ts` and `thread_replies(channel, thread_ts) -> list[message]`. It raises `SlackError` on HTTP errors, `ok: false` and timeouts, and never puts the token or the text in an exception message. Verify with `tests/test_slack.py` against a local fake Slack HTTP server, using `SLACK_API_BASE`.
- [x] 1.3 Add the report and reply formatters (`format_report(application, jobs, report)`, `format_job_reply(kind, outcome)`, `format_batch(batch)`) and the splitter for 3,500 characters on line boundaries. Verify the formatter output against the spec scenarios: the `App ID` line, empty fields left out, document states, lettered options, and splitting.

## 2. Store

- [x] 2.1 Add the `slack_threads(application_id PK, channel, thread_ts NULL, claimed_at)` and `fill_questions` tables, with the columns from the design. Create them idempotently on open, as the existing tables are. Verify with store tests that an existing database upgrades in place.
- [x] 2.2 Add `claim_slack_report(id)` under `BEGIN IMMEDIATE`. It returns the application, its jobs and its report only when the resume is `done`, no job is `running` and no thread exists. Add `set_thread_ts`, `release_claim` and `get_thread`. Verify with a threaded test where two claims race and exactly one wins, and with each condition failing alone.
- [x] 2.3 Add question store methods: `add_batch` (which cancels older pending batches), `get_batch`, `pending_batch`, `answer_batch` (pending → answered only, under the lock), and `cancel_batch`. Verify with tests for supersede, answer twice (conflict) and the answer count mismatch.

## 3. Notifier hook

- [x] 3.1 Add `SlackNotifier.after_job(application_id, kind, outcome)`. It sends the report when the claim succeeds, a reply when a thread exists, and releases the claim when a post fails. It logs `slack_post` lines with no text. Call it from `run_job` after `finish_job` inside its own `try/except Exception` (`app/main.py`), and inject it through `create_app` so tests can use a fake. Verify with tests for each "Ready report" and "Follow-up posts" scenario, including Slack failure, which must leave the job `done`, and Slack not configured, which must make no calls.
- [x] 3.2 Add `POST /application/{id}/slack-report` (keyed). Verify the 200 new, 200 already posted, 409 `resume_not_ready`, 404 and 502 cases.

## 4. Fill and relay endpoints

- [x] 4.1 Make `fill_command` and `FormFillLauncher.start` take `mode` (`None` or `"slack"`). The only change to the command is the fixed word `slack` added after the ID. Verify in `tests/test_form_filler.py` that the viewer command is unchanged and the Slack command is quoted as a single argument.
- [x] 4.2 Add `POST /application/{id}/fill` (keyed, local only), with 404, 409 `no_thread`, 503 Herdr and 503 Slack-not-configured responses and a thread line on success. Verify with API tests using the fake runner and the fake Slack.
- [x] 4.3 Add the question endpoints (`POST`, `GET` one, `GET ?status=pending`, `DELETE`, and `POST .../answers`) with the Pydantic models for batches and answers. Verify with tests covering every "Question batches" and "Recording answers" scenario, and that no question or answer text appears in logs.
- [x] 4.4 Implement approval verification in the answers endpoint: `thread_replies`, the owner, newer than the batch's `slack_ts`, and the text rule. Verify with the fake Slack for each passing and failing case in "Verified submit approval", plus 503 when the owner ID is unset.
- [x] 4.5 Add `POST /application/{id}/slack-update` with splitting. Verify the 2-message case and 409 `no_thread`.
- [x] 4.6 Document every new operation in OpenAPI (summary, API-key scheme, responses). Update the operation count and the security assertions in `tests/test_docs.py`, and update `scripts/smoke_test.sh` and its test for the new count. In `tests/test_serve.py`, assert that each new path is 404 on the public listener.

## 5. Form filler skill

- [x] 5.1 Add `scripts/ask_slack.py` with `post <id> <batch.json|->`, `wait <id> <qid> [--timeout 540]` (exit code 0 with the answers as JSON, 3 when still pending, 1 on error) and `cancel <id> <qid>`. It reads `API_KEY` from `.env` and never prints it. Verify with tests against a running test app.
- [x] 5.2 Add a "Slack mode" section to `.claude/skills/job-application-form-filler/SKILL.md`. Cover: the `slack` argument; the AskUserQuestion → `ask_slack.py` mapping (same batch shape, `kind: approval` for the two Step 7 approval questions); waiting again on exit code 3; posting the Step 6 report and the final report through `slack-update`; and cancelling on takeover. All other rules stay unchanged. Verify with `tests/test_form_filler_skill.py` assertions on the new section.

## 6. Documentation

- [x] 6.1 Add a README "Slack workflow" section. Cover the settings, the bot scopes needed (`chat:write`, `groups:history` for a private channel, `channels:history` for a public one), inviting the bot to the channel, the thread flow, the approval rule, and that the bot token must be rotated in both `.env` files.

## 7. Hermes side (outside this repo, after the backend is merged)

- [ ] 7.1 Switch Hermes chat to Claude with an Anthropic API key (`hermes model`). Keep `cron.model` on local `qwen3.5:9b`.
- [ ] 7.2 Write the `~/.hermes/skills/job-hunt/SKILL.md` skill. It covers: reading `App ID` from the thread's root report; "fill form" → `POST /fill`; on any owner reply, `GET ?status=pending`, then mapping the reply to answers and `POST .../answers` with the reply's `ts`; status questions → `GET /application/{id}`; and never claiming an approval the owner didn't write. The key comes from Keychain item `job-mail-agent-backend`.
- [ ] 7.3 Bind the skill to `#job-hunt-announcements` (`slack.channel_skill_bindings`). Add the owner's user ID to the allowlist and invite the bot to the channel.
- [ ] 7.4 End-to-end check: generate documents for a test application, see the report, reply "@Hermes fill form", answer one question in the thread, and confirm the form filler received it. Stop before submitting.

## 8. Integration check

- [ ] 8.1 Run `pytest`, `bash scripts/test_smoke_test.sh` and `bash scripts/test_install_service.sh`, then `openspec validate slack-application-workflow --strict`.
