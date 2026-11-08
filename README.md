# job-hunt-hq

A small FastAPI service that runs on a Mac mini used as a personal server. `POST /application` records a job posting, and `POST /resume` renders a resume PDF for a recorded application and saves it on the Mac's disk at `OUTPUT_DIR/<company>/<application id>/<name>.pdf`, `<name>` being the `\name{...}` in your `data/BASE.tex`. Nothing depends on a cloud service: storage, secrets and the process all live on the Mac, and four of its endpoints are published over HTTPS through [Tailscale](https://tailscale.com) Funnel, so outside tools (such as Muse) can call them. Everything else, the API reference and the resume viewer included, is served only on the Mac itself.

Each resume is matched against the application's posting. Claude scores the base resume (`data/BASE.tex` + `data/resume.cls`, compiled with [tectonic](https://tectonic-typesetting.github.io/)). Below 70 it reworks the wording, order and emphasis of the base resume's own facts, plus the extra facts about each job in your profile (`data/PROFILE.md`), into the same one-page template, requirement by requirement and in your own words. Scripts check every rule. Posting keywords the base resume lacks get in only when a profile fact states them or a separate Claude judge finds them in your resume or profile. See [How resumes are tailored](#how-resumes-are-tailored). For the applications that ask for one, `POST /cover-letter` writes a one-page cover letter tailored to the posting from the same facts. See [How cover letters are written](#how-cover-letters-are-written).

On the installed service only `GET /health`, `POST /application`, `POST /resume` and `POST /cover-letter` are served on the public (Funnel) address. Every other endpoint below, and those in the [API reference](#development), is served only on the local listener, `http://127.0.0.1:8081` on the Mac mini, and answers 404 on the public address.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /healthz`, `GET /health` | none | `200 {"status": "ok"}`, no storage access |
| `POST /resume` | `X-API-Key` | Body `{"application_id": "<uuid>"}`. Starts a background job that scores the base resume against the stored posting, tailors it below 70, and saves it, and returns at once with `202 {"ok": true, "application_id", "status": "running", "started_at"}`. Poll `GET /resume/{application_id}/status` for the result. The job takes about 1–5 minutes when it runs Claude (capped at about 10) and keeps running if the client disconnects. Sending it again while the job runs starts no second run and returns the same 202, so a retry is safe. It never writes a cover letter (see `POST /cover-letter`). Errors are `{"ok": false, "message"}`: 401 bad key, 404 unknown application, 422 bad body, 503 store failure |
| `GET /resume/{application_id}/status` | `X-API-Key` | The application's latest resume job: `200 {"ok": true, "application_id", "status", "started_at", "finished_at", "saved_path", "match", "error"}`. `status` is `running`, `done` (`saved_path` is the resume's file name, `<name>.pdf`, never a path on the Mac, and `match` is `{"status", "threshold", "base_score", "tailored_score", "added_terms"}`) or `failed` (`error` is `Resume generation failed`, `Storage service unavailable` or `Interrupted by a service restart`, and any earlier resume is kept). Poll every 10–15 seconds and give up after about 12 minutes. Served only on the local listener, and returns no posting text. 401 bad key, 404 unknown application or `No job for this application`, 503 store failure |
| `POST /cover-letter` | `X-API-Key` | Body `{"application_id": "<uuid>"}`. Starts a background job that writes a cover letter tailored to the stored posting and saves it beside the resume as `<name> - Cover Letter.pdf`, replacing any earlier one, and returns `202` like `POST /resume`. Poll `GET /cover-letter/{application_id}/status`. Call it only for applications that ask for a letter; it needs no resume. The job takes about 1–3 minutes. Always tailored: an application without usable posting text (missing, under 50 words or over 60,000 characters) gets a 422 and no job. Errors are `{"ok": false, "message"}`: 401 bad key, 404 unknown application, 422 bad body or no posting text, 503 store failure |
| `GET /cover-letter/{application_id}/status` | `X-API-Key` | The application's latest cover letter job, as for the resume, with `saved_path` `<name> - Cover Letter.pdf` when done and `text` (the same letter as plain text, for forms that take pasted text) in place of `match`. A failed job's `error` is `Cover letter generation failed`, `Storage service unavailable` or `Interrupted by a service restart` |
| `POST /application` | `X-API-Key` | Records a verified posting. `201 {"ok": true, "application_id"}` for a new one, `200` with the existing ID if its `job_link` is already stored. Errors are `{"ok": false, "message"}`: 401 bad key, 422 bad body, 503 store failure |
| `POST /application/email-status` | `X-API-Key` | Updates the status of the one application a job email is about, found by `company` and `role` (or `job_link`). `200 {"ok": true, "application_id", "company", "role", "previous_status", "status", "changed"}`. 404 `no_match` or 409 `ambiguous` when zero or several applications match, and nothing changes. 401 bad key, 422 bad body, 503 store failure. Served only on the local listener. See [Email status updates (Hermes)](#email-status-updates-hermes) |
| `PATCH /application/{application_id}` | `X-API-Key` | Changes the fields sent, e.g. `{"status": "applied"}`. `200 {"ok": true, "application_id", "status"}`. 401 bad key, 404 unknown ID, 422 bad body, 503 store failure |
| `DELETE /application/{application_id}` | `X-API-Key` | Permanently removes the row. `200 {"ok": true, "application_id"}`. 401 bad key, 404 unknown or already-deleted ID, 503 store failure |

Code layout: `app/main.py` (HTTP), `app/serve.py` (launcher for the installed service: the public listener's four-endpoint allowlist and the local listener), `app/viewer.py` (the resume viewer page, the cached base resume and the base cover letter it serves), `app/models.py` (`ResumeRequest`, `StoredApplication`, `ApplicationRow`, `ApplicationUpdate`, and the response shapes shown in the API docs), `app/applications.py` (application store and link dedupe), `app/generation.py` (picks the base or tailored resume), `app/tailoring.py` (runs the tailor-resume skill and its judge headlessly, and the final gate), `.claude/skills/tailor-resume/` (the skill and its scripts), `.claude/skills/judge-resume-terms/` (the judge), `.claude/skills/apply-from-link/` (the job link workflow, run in a Claude Code session), `app/form_filler.py` (opens the Herdr tabs for Fill form and the link box), `app/rendering.py` (TeX to PDF), `app/storage.py` (resume file layout and atomic writes), `app/settings.py` (config), `app/log_filters.py` (keeps query strings out of access logs), `data/` (resume template assets and your profile), `deploy/` (launchd and logging templates, check for a leftover Tailscale mapping to the local listener), `scripts/` (install, uninstall, status, smoke test).

### Request body (`POST /resume`)

`{"application_id": "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"}`: the ID returned by `POST /application`, as a JSON string. Everything else (company, role, job description and so on) is read from the stored application, so record or `PATCH` the posting first. Extra fields are ignored. A missing or non-string ID (`7`, `7.5`, `true`) is a 422; a string that is not a UUID or names no stored application is a 404. Generating a resume never changes the application, its status included, and works for any status.

### Request body (`POST /cover-letter`)

The same as `POST /resume`: `{"application_id": "<uuid>"}`, with the same 422 and 404 rules. Company, role and posting text come from the stored application. Writing a letter never changes the application or its resume.

### Request body (`ApplicationRow`)

Strings only, extra fields ignored, and a 422 message names fields but never values.

| Field | Required |
|---|---|
| `company`, `role`, `job_link` | yes (non-empty) |
| `posting_source_type` | yes: `recruiting_platform`, `employer_site` or `linkedin_easy_apply` |
| `verification_method` | yes: `official_apply_match`, `employer_site` or `owner_confirmed` |
| `official_apply_url` | yes (may be `""`) |
| `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain`, `full_job_description` | no |
| `added_via` | no: `link` when the apply-from-link workflow records the posting, otherwise `manual` (the default). Fixed once recorded |

Only three combinations are accepted, and anything else is a 422:

- `recruiting_platform` + `official_apply_match`, with `official_apply_url` equal to `job_link` byte-for-byte
- `employer_site` + `employer_site`, with `official_apply_url` set to `""`
- `linkedin_easy_apply` + `owner_confirmed`, with `official_apply_url` set to `""`, for a LinkedIn Easy Apply posting with no official posting. The owner vouches for it rather than a link check

**Dedupe.** A posting counts as already stored when its `job_link` matches after normalization:
- the scheme and host are lowercased
- the default port, the `#fragment` and trailing slashes are dropped
- the tracking parameters `utm_*`, `gh_src`, `source`, `src`, `ref`, `lever-source`, `lever-origin` and `trk` are removed

Other query parameters are kept, so `?gh_jid=111` and `?gh_jid=222` stay separate postings. Path case is kept. A duplicate never changes the stored row, and `job_link` is stored as first sent. To strip a new tracking parameter, add it to `TRACKING_PARAMS` in `app/applications.py`.

**Status.** Every application has a `status`:

| Status | Meaning |
|---|---|
| `verified` | Recorded, not yet applied. The default for new rows and for rows stored before statuses existed |
| `applied`, `interviewing`, `offer` | Progress |
| `rejected`, `withdrawn` | Closed: by the employer, or by you |

Values are exact and case-sensitive, and any status can change to any other. Re-posting a stored link never changes its status.

**Updating.** `PATCH /application/{application_id}` writes only the fields in the body:
- `status`, `company` and `role` must be non-empty strings
- `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain` and `full_job_description` take a string, or `null` to clear them
- `job_link`, `posting_source_type`, `verification_method`, `official_apply_url` and `added_via` can't be changed. A body that contains any of them is a 422, even if the value matches
- unknown fields are ignored, and a body with nothing to update is a 422

An unknown ID returns 404, checked before the body, and a bad key returns 401 before either.

**IDs** are random UUIDs (version 4), returned in lower case, such as `3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13`. They say nothing about how many applications exist or in what order they were recorded; sort by `created_at` if you need order. Paths and bodies accept the hyphenated form in any letter case. Any other path value, including an old integer ID, is a 404; in the `POST /resume` body a JSON number is a 422.

**Deleting** is permanent and frees the link: posting it again creates a new row with a new ID. To stop tracking a posting but keep its record, set `status` to `withdrawn` instead.

Rows live in `OUTPUT_DIR/applications.sqlite3` (mode 600). To back it up while the service runs:

```sh
sqlite3 ~/Library/Application\ Support/job-hunt-hq/applications.sqlite3 ".backup applications-backup.sqlite3"
```

### Email status updates (Hermes)

The local Hermes workflow on the Mac mini, which classifies job emails, moves an application's status through `POST /application/email-status` on the local listener. The endpoint is not published through Funnel: the public address answers 404 for it. It doesn't need the application ID:

```sh
curl -sS -X POST http://127.0.0.1:8081/application/email-status \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"company": "Acme Corp", "role": "Applied AI Engineer", "status": "Rejected", "received_at": "Nov 7, 2026 9:21 PM", "note": "Acme has decided to move forward with other candidates."}'
```

- `company`, `role` and `status` are required. `status` is `Applied`, `Rejected` or `Response`, in any letter case. `job_link` is optional. `received_at` and `note` are accepted but never stored or logged.
- **Matching.** A `job_link` that identifies a recorded posting decides on its own. Otherwise the company and role must both match. Case, accents, punctuation and spacing are ignored, `&` reads as `and`, company suffixes such as Inc or LLC are dropped, and `Sr`/`Jr` read as `Senior`/`Junior`. A name at least 90% similar to a stored one counts only when no name matches exactly.
- **Mapping.** `Applied` changes nothing: the form filler already marks applications applied, so it only confirms. `Rejected` sets `rejected`, except on a `withdrawn` application. `Response` sets `interviewing`, only from `verified` or `applied`. Statuses never move backwards, so a repeated or late email is harmless, and `changed` says whether this one wrote anything.
- **No guessing.** No match is `404 {"ok": false, "reason": "no_match", "message"}`, and several matches are `409 {"ok": false, "reason": "ambiguous", "match_count", "message"}`. Neither changes anything. In Hermes, route 404, 409 and 422 to a branch that flags the email. Sending `job_link` resolves a 409 when the email has one.

The response carries the matched application's stored `company`, `role` and `previous_status`, so the workflow can show which application it updated.

### Slack workflow

Each application gets one thread in a Slack channel, such as `#job-hunt-announcements`, where the owner reviews it, starts the form filler, answers its questions and approves the submission. Hermes, connected to the same Slack app, handles the conversation. The service posts and reads with that app's bot token and never receives Slack events.

1. **Ready report.** When an application's resume job is `done` and no generation job is running, the service posts a report to `SLACK_CHANNEL_ID`. It shows the company, role, `App ID`, match score, why it fits, job details, posting link and viewer link (`http://127.0.0.1:8081/viewer#<id>`, which works on the Mac only). One application never gets two reports. A later job, such as a cover letter finishing or a resume being regenerated, is posted as a reply in the thread. If Slack is down, the job still counts as done; `POST /application/{id}/slack-report` retries.
2. **Fill from the thread.** "@Hermes fill form" makes Hermes call `POST /application/{id}/fill`. That opens the usual Herdr tab running `claude --chrome "/job-application-form-filler <id> slack"`.
3. **Questions.** In Slack mode the form filler posts each batch through `scripts/ask_slack.py` (`POST /application/{id}/questions`), and the service writes it into the thread. Hermes reads the pending batch (`GET /application/{id}/questions`) and records the owner's reply (`POST .../questions/{question_id}/answers`). The form filler's `wait` picks the answers up.
4. **Approval.** The agree-and-submit and mark-applied questions are `approval` batches. The service accepts their answer only after reading the named reply from Slack itself. The reply must be from `SLACK_OWNER_USER_ID` (not a bot), newer than the question, and start with yes, approve or submit, or name the chosen option. Neither Hermes nor text on a form page can approve a submission.
5. **Reports.** The form filler posts its report and final report with `POST /application/{id}/slack-update`.

Setup:

- In `.env`, set `SLACK_BOT_TOKEN` (the Hermes app's `xoxb-…` token), `SLACK_CHANNEL_ID` (`C…`, from the channel's details) and `SLACK_OWNER_USER_ID` (your member ID, `U…`). Restart the service. Without the token and channel, nothing is posted and the Slack endpoints answer 503.
- The bot needs `chat:write`, plus `groups:history` for a private channel or `channels:history` for a public one, to verify approvals. Invite it to the channel with `/invite @Hermes`.
- The token now lives in both Hermes's `.env` and this one. Rotate it in both places.
- Every Slack endpoint needs the API key and is served on the local listener only. Message, question and answer text is never logged.

### Upgrading from integer IDs

Stores made before IDs were UUIDs are converted the first time the new version starts:

- The store is first copied to `applications.sqlite3.pre-uuid-<timestamp>.bak` (mode 600) beside it.
- Every row gets a new UUID in one transaction; all other fields, statuses and timestamps are kept. If anything fails, the store is left as it was and the service refuses to start.
- The old-to-new mapping stays in the `legacy_application_ids` table: `sqlite3 …/applications.sqlite3 "select * from legacy_application_ids"`.
- Resume folders named by an old ID (`Acme Corp/1/`) are renamed to the new UUID. A folder whose UUID name is already taken is left alone and logged as `legacy_folder_conflict`. An interrupted rename finishes on the next start.
- Old integer IDs stop working. Update any client that stored them (such as Muse) to keep `application_id` as a string.

To roll back: run `scripts/uninstall_service.sh`, copy the `.bak` file over `applications.sqlite3` (deleting any `-wal`/`-shm` files beside it), rename the resume folders back using the mapping, check out the previous commit and reinstall.

Take a backup before upgrading to a build that changes the store. The first start of the status-aware build adds the `status` and `updated_at` columns in place. Older builds ignore them, so rolling back needs no restore.

### How resumes are tailored

`POST /resume` picks the resume to save, and reports which one in `match`:

| `match.status` | When | Saved file |
|---|---|---|
| `no_job_description` | `full_job_description` is missing or under 50 words | the base resume, unscored, in seconds |
| `base_meets_threshold` | the base resume scores 70 or more against the posting | the base resume |
| `tailored` | the base resume scores below 70 | a tailored resume, same template, one page |

The work is done by two Claude Code skills, which the service runs headlessly with `claude -p`: `tailor-resume` (`.claude/skills/tailor-resume/`) and its judge, `judge-resume-terms`. One resume takes up to three runs:

1. **Analysis.** `tailor-resume` lists the posting's keywords and requirements and scores the base resume. At 70 or more the base resume is saved and nothing else runs.
2. **Judge.** If the posting uses keywords the base resume lacks, the judge decides which of them you genuinely have. It runs in a folder of its own and sees your resume, your profile and those keywords, never the posting, so the job can't sway it. It approves a keyword only with evidence, which a script then checks: a passage of your resume or a profile fact that implies it (for example "automated code validation" for testing), or a skill on your profile list. Keywords a profile fact states need no judge. A rejected keyword's report entry carries the judge's reason.
3. **Tailoring.** `tailor-resume` runs again. It first plans, for each requirement the base resume doesn't fully meet, which bullets and profile facts show it, then reworks those bullets so the work is plain to see, and keeps revising (within five builds) while a planned requirement is still not met, even past 70. It uses approved keywords only where their evidence allows; `match.added_terms` lists the ones it used. A bullet that copies a run of the posting's own words gets flagged and reworded.

How it decides:

- **The score.** Claude lists the posting's keywords (searchable terms such as tools, skills and methods, not the posting's own phrasing) and requirements, and marks a requirement met only when every part of it is shown. A script finds the keywords in the resume (whole words, ignoring case, with listed aliases), and accepts a requirement as met only with a quote that really appears in the resume. The score is half keyword coverage and half requirement coverage, with required items counting double.
- **No fabrication.**
  - The name and contact line, education, job headings and certifications are copied from `BASE.tex` and can't change.
  - Skills may be reordered, regrouped under the existing labels, or dropped. The only new items allowed are keywords the judge approved.
  - Every bullet cites the base bullets or profile facts of the same job it comes from, and every number in it must appear in them.
  - A posting keyword the base resume lacks can appear only if a profile fact states it or the judge approved it: in a skills line, or in a bullet that comes from the base bullet or fact holding its evidence. A keyword approved from your profile skills alone goes in a skills line only. No keyword the base resume has can disappear.
- **Your profile.** `data/PROFILE.md` has two parts, and everything in it is treated as true:
  - **Experience:** facts about each job that `BASE.tex` doesn't say, as `- ` lines under a `### <Employer>` heading (the employer as its job heading starts). A tailored bullet of that job may use them like its base bullets. A heading that names no job fails the request before any Claude run.
  - **Skills and abilities:** every other `- ` line. Only the judge reads these. Name the tools you have used: an entry "Browser automation" doesn't tell the judge you have used Playwright.

  A keyword the judge rejects is simply left out, and never fails a request.
- **Same template, one page, used fully.** Claude writes plain text; a script splices it into `BASE.tex`, so preamble, spacing and fonts never change. The result must be exactly one page, fill at least 90% of it and keep every line inside the margins. The skill keeps revising toward 96% fill, and toward no bullet whose last line holds only a word or two.
- **The final gate.** Before saving, the service re-checks the output with its own untouched copy of the scripts and template, and saves only the PDF it rendered itself. It scores against the analysis as it stood when the judge ruled, and allows only the keywords of its own copy of the ruling and the facts of its own copy of your profile, so the tailoring run can't change any of them.
- **Failures.** If Claude isn't configured or available, a run hits the time or spend limit, the judge's output is unusable, or the content fails a check, the request fails with 500 `Resume generation failed`. Nothing is saved, any earlier resume is kept, and the log line `tailoring_error` gives the stage (`analysis`, `judge`, `tailoring` or `verify`) and reason codes.
- **Isolation.** Posting text is treated as untrusted data. Each Claude run works in a temporary folder with an empty `HOME` and its own config folder (`OUTPUT_DIR/.claude-runtime/`). It has no web or MCP tools, can only run the skill's script and read-only commands inside that folder (the judge runs no commands at all), and its commands never see the credential. Your own Claude Code settings, hooks and shell profile are never loaded.
- **Cost and limits.** With `CLAUDE_CODE_OAUTH_TOKEN`, runs use your Claude plan. On Pro that plan's limits are shared with your own Claude Code use, and a run that hits them fails. With `ANTHROPIC_API_KEY`, runs are billed per use: roughly 1–2 USD per tailored resume, less when the base resume already matches. `TAILORING_TIMEOUT_SECONDS` and `TAILORING_MAX_BUDGET_USD` cover all the runs for one resume together. Each `resume_job` log line records the runs' turns and estimated cost, and how many keywords the judge approved and rejected (counts only, never the keywords).

To run the skill by hand on a posting saved to a file, from the repository root:

```sh
.claude/skills/tailor-resume/scripts/run prepare --template data --posting posting.txt --out /tmp/tailor-test
# then, in Claude Code at the repository root:
/tailor-resume /tmp/tailor-test
# if it stops to wait for the judge, run the judge in a terminal (it uses .env's credential):
.venv/bin/python -m app.tailoring --judge /tmp/tailor-test
# then, back in Claude Code, run /tailor-resume /tmp/tailor-test again to tailor
```

Everything it writes, including the draft PDF (`out/build/tailored.pdf`), the check report (`out/check.json`) and the judge's verdicts and ruling (`judge/`), lands in that folder. The interactive session uses your own login and asks before writing.

### How cover letters are written

`POST /cover-letter` runs the `write-cover-letter` skill (`.claude/skills/write-cover-letter/`) once, headlessly, with the same isolation, model, time limit and spend cap as resume tailoring. Its scripts reuse the `tailor-resume` skill's modules.

- **What Claude writes.** Only the paragraphs: an opening, two or three body paragraphs and a closing. It first lists the posting's keywords and requirements, then writes `out/letter.json`. The scripts add the resume's name and contact header, the date, the greeting ("Dear <Company> Hiring Team,") and "Sincerely," with your name.
- **No fabrication.**
  - Each body paragraph cites the base bullets and profile facts it draws on (any job), and every number in it must appear in them. The opening and closing hold no numbers.
  - A posting keyword that appears in the letter must also appear in your resume or profile. There is no judge: a keyword you lack stays out.
  - The opening names the company and role exactly as recorded, and the body paragraphs must address at least two of the posting's required requirements.
- **Need, achievement, improvement.** Each body paragraph goes from one need of the employer to your work that meets it to the measured result it made, and the first two carry your two strongest achievements. A paragraph that leaves out a result its sources state gets a `no_result` warning for Claude to fix (a warning, since not every need has a metric in your record).
- **In your words.** A run of three or more posting words that the paragraph's sources don't share fails the letter (`echoed_phrase`). For resumes this is only a warning. The company and role are exempt. Template lines such as "I am excited to apply" are flagged.
- **Size.** 250–400 words on one page.
- **The final gate.** The service re-checks the letter with its own copy of the scripts, template, profile, posting and company/role, and saves only the PDF and text it rendered itself.
- **Failures.** If any check fails, or Claude isn't configured or available, or the run hits a limit, the job fails with `Cover letter generation failed`. Nothing is saved and any earlier letter is kept. The log line `cover_letter_error` gives the stage (`prepare`, `letter` or `verify`) and the reason codes. Each `cover_letter_job` line records the run's turns and estimated cost, never the letter.

The checks can't catch every overstatement ("led" where your record says "built"), so skim each letter before you send it.

**The base cover letter.** A generic letter, written once with the same rules, is kept for your reference at `data/COVER_LETTER.md` (text) and `data/COVER_LETTER.pdf`. The service never generates or edits it, and tailored letters don't use it; the [resume viewer](#resume-viewer) only shows this PDF beside each generated letter. Both files are local only; `data/samples/` has a made-up pair. To draft it again:

```sh
.claude/skills/write-cover-letter/scripts/run prepare --template data --profile data/PROFILE.md --out /tmp/letter-base
# then, in Claude Code at the repository root:
/write-cover-letter /tmp/letter-base
# after a passing build, write the two files:
.claude/skills/write-cover-letter/scripts/run publish-base --work /tmp/letter-base --data data
# after editing data/COVER_LETTER.md by hand, re-render the PDF:
.claude/skills/write-cover-letter/scripts/run render-base --data data
```

With `--posting posting.txt --company "Acme" --role "ML Engineer"` added to `prepare`, the same session writes a tailored letter into the work folder (`out/letter.pdf`, `out/letter.txt`) instead.

### Resume files

Each resume is saved at `OUTPUT_DIR/<company folder>/<application id>/<name>.pdf`, using the application's company at the time you generate. The folder keeps the company name as written (spaces, case, accents), with `/`, `\`, `:` and control characters replaced by `-`, leading and trailing spaces and dots removed, and the name cut to 100 characters. An empty result becomes `unknown-company`, and a name starting with `applications.sqlite3` gets a leading `_` so it can't collide with the store.

- `<name>` is the `\name{...}` of `data/BASE.tex` as written, read when the service starts (restart it after changing the name), with `/`, `\` and `:` replaced by `-`. Without a readable name the files are `Resume.pdf` and `Resume - Cover Letter.pdf`.
- Generating again for the same application replaces the file in one step; a failed render or write leaves the previous file intact.
- Folders are readable only by your user and files are mode 600. The service serves resumes and cover letters over HTTP only to the [resume viewer](#resume-viewer), on the Mac-only local listener, without the API key.
- Files are kept until you delete them. Deleting an application, or renaming its company, leaves existing resume folders where they are.

### Upgrading from `POST /jobs`

`POST /jobs`, `GET /files/...` and signed download links are gone (both return 404). Record the posting with `POST /application`, then call `POST /resume` with the returned ID, and read errors from `ok`/`message` rather than `detail`. `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL`, `SIGNED_URL_TTL_SECONDS` and `OUTPUT_RETENTION_DAYS` are no longer used: remove them from `.env` (they're ignored if left in). Files under `OUTPUT_DIR/outputs/` from the old endpoint are no longer served or cleaned up; delete that folder by hand.

## Your data (local only)

Your own files never go into the repository. Everything in `data/` is gitignored except `data/samples/`, which holds made-up copies of the files the service needs, for a fictional Jane Doe:

| File | What it is |
|---|---|
| `BASE.tex`, `resume.cls` | The one-page base resume and its class. `\name{...}` names the saved PDFs |
| `PROFILE.md` | Your profile: facts per job and skills beyond the resume (see [How resumes are tailored](#how-resumes-are-tailored)) |
| `COVER_LETTER.md`, `COVER_LETTER.pdf` | The base cover letter (see [How cover letters are written](#how-cover-letters-are-written)) |
| `BASE.pdf` | `BASE.tex` rendered, for reference |

To start, copy them and replace each with your own:

```sh
cp -n data/samples/* data/
```

The service, the skills and the smoke test read `data/`. The tests read `data/samples/` instead (they set `JOB_HUNT_DATA_DIR`, which overrides the folder), so they pass on a fresh clone and never see your files. Anything else you keep in `data/`, such as notes for application forms, stays local too.

## Configuration

Copy `.env.example` to `.env` (git-ignored), fill it in and run `chmod 600 .env`. The service refuses to start if a required value is missing or invalid, and its errors never print the values.

| Variable | Required | Notes |
|---|---|---|
| `API_KEY` | yes | Sent by clients as `X-API-Key`. Generate it with `openssl rand -hex 32` |
| `OUTPUT_DIR` | no | Where resumes and the application store live. Default `~/Library/Application Support/job-hunt-hq`. Don't use `~/Documents`, `~/Desktop` or `~/Downloads`: macOS blocks background services from those folders |
| `CLAUDE_CODE_OAUTH_TOKEN` | no | Claude subscription token for [resume tailoring](#how-resumes-are-tailored), from `claude setup-token`. Paste it as one line: the command's display can wrap it. Without a Claude credential, resumes that need scoring fail with 500 |
| `ANTHROPIC_API_KEY` | no | Claude Console API key, the other tailoring credential, billed per run. When both are set, the API key is used |
| `TAILORING_MODEL` | no | Default `claude-opus-5-5`. Claude Code falls back to `claude-sonnet-5-5` when the model is overloaded or unavailable |
| `TAILORING_TIMEOUT_SECONDS` | no | Default `420`, from `60` to `480`, for all the Claude runs of one resume together. A run still going when it is used up is stopped, and the request fails |
| `TAILORING_MAX_BUDGET_USD` | no | Default `3`, the estimated spend cap for all the Claude runs of one resume together. When it is reached the request fails. The estimate is checked between turns, so a run can go slightly over |
| `CLAUDE_BIN` | no | Default `claude`. The installed service gets the path the install script found |
| `HERDR_BIN` | no | Default `herdr`, the Herdr CLI the viewer's **Fill form** button and link box call. The installed service gets the path the install script found |
| `FILL_WORKSPACE` | no | Default `Claude-Jobs-Automation`, the Herdr workspace **Fill form** and the link box open their tabs in |
| `API_DOCS_ENABLED` | no | Default `false`. `true` serves the API reference at `/docs`, `/redoc` and `/openapi.json`, and the [resume viewer](#resume-viewer), on a development server. The installed service ignores it: its public port never serves docs, and its local port always does |

## Development

Rendering needs `tectonic` on your PATH; the first render downloads TeX packages into its cache.

```sh
brew install python@3.12 tectonic
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp -n data/samples/* data/   # then replace them with your own; see "Your data"
.venv/bin/uvicorn app.main:create_app --factory --port 8080

ID=$(curl -s -X POST localhost:8080/application -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"company":"Acme","role":"Software Engineer","job_link":"https://www.acme.com/careers/1","posting_source_type":"employer_site","verification_method":"employer_site","official_apply_url":""}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["application_id"])')
echo "$ID"
# 3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13   (201; 200 with the same id when sent again)

curl -X POST localhost:8080/resume -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' -d "{\"application_id\":\"$ID\"}"
# {"ok":true,"application_id":"3f2b…","status":"running","started_at":"2026-10-28T17:02:11.204518Z"}   (202)

curl "localhost:8080/resume/$ID/status" -H "X-API-Key: $API_KEY"
# {"ok":true,"application_id":"3f2b…","status":"done","started_at":"…","finished_at":"…",
#  "saved_path":"<name>.pdf",
#  "match":{"status":"no_job_description","threshold":70,"base_score":null,"tailored_score":null,"added_terms":[]},"error":null}
# (this posting has no text, so nothing was scored and the job finished in seconds; with posting text, poll until done.
#  saved_path is only the file name: the PDF is at OUTPUT_DIR/Acme/<id>/<name>.pdf on the Mac)

curl -X POST localhost:8080/cover-letter -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' -d "{\"application_id\":\"$ID\"}"
# {"ok":false,"message":"Application has no usable posting text: add full_job_description (at least 50 words) with PATCH /application/{application_id} first"}
# (422: this posting has no text. With one, it returns 202, and once done
#  GET /cover-letter/$ID/status has "saved_path":"<name> - Cover Letter.pdf" and "text":"Dear Acme Hiring Team,\n\n…")

curl -X PATCH "localhost:8080/application/$ID" -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' -d '{"status":"applied"}'
# {"ok":true,"application_id":"3f2b…","status":"applied"}

curl -X DELETE "localhost:8080/application/$ID" -H "X-API-Key: $API_KEY"
# {"ok":true,"application_id":"3f2b…"}   (404 {"ok":false,"message":"Application not found"} if sent again)
```

### API reference and request tester

An interactive API reference (Swagger UI) lists every endpoint by tag. Its **Try it out** button sends a request to the service and shows the status, headers and body. On a development server, turn it on and point `OUTPUT_DIR` at a throwaway folder, because requests are real:

```sh
API_DOCS_ENABLED=true OUTPUT_DIR=/tmp/job-hunt-hq-dev .venv/bin/uvicorn app.main:create_app --factory --port 8080
open http://localhost:8080/docs   # also /redoc and /openapi.json
```

Click **Authorize** and enter the API key once. The page keeps it in memory only, so reloading forgets it. The page loads exact, integrity-checked versions of Swagger UI and ReDoc from the jsDelivr CDN (pinned in `app/main.py`).

With docs on, the [resume viewer](#resume-viewer) and its read endpoints are served too, and they need no API key. Keep a docs-enabled dev server on loopback (uvicorn's default; don't pass `--host 0.0.0.0`).

On the installed service the reference is on a separate listener reached only from the Mac mini itself (see [Local listener](#local-listener)): `http://127.0.0.1:8081/docs`.

The public address never serves these pages. Requests sent from there change your real application store and write real resume files.

### Resume viewer

`/viewer` is a page for reviewing what the service generated for each application, generating or regenerating its resume and cover letter, changing its status and deleting it. It is served wherever the API reference is: on the installed service only on the local listener, at `http://127.0.0.1:8081/viewer` on the Mac mini; the public address answers 404. Every request the page makes is a relative path, so it only ever calls the listener it was opened from.

The page opens straight to the list, with no API key: its endpoints need none, so anything that can reach the local listener (programs running on the Mac mini) can read every application, posting and resume, change a status, delete an application or start a Claude run. The left column lists every application, most recently generated first. Each entry is one card showing the company, the role, the status, the match badge, the base → generated score (the generated score green at or above the threshold, red below) and the day it was recorded. While a resume or cover letter is being generated for it, the card shows **Resume…** or **Letter…**. Cards have no controls: clicking one selects it.

Above the filters, the link box takes a job link and **Apply from link** starts the workflow described under [Apply from a link](#apply-from-a-link). The list keeps refreshing for 15 minutes after that, so the application appears once the session records it. Each list entry has a tag for how the posting was added: **ByLink** for this workflow and **Manual** for everything else, including applications recorded before the tag existed and postings other API clients recorded.

Above the list, a search box matches company or role (ignoring case), **All statuses** narrows to one status, and **Recorded** takes a from and a to day. The dates are the days the applications were recorded in the database (in your browser's time zone, both days included), not the posting dates. Either date can be left empty. While any filter is set, the header shows how many applications match out of the total and **Clear** resets them all. Filters reset when the page reloads.

The selected application's action bar, pinned above its details, holds everything you can do to it:

- **Status** is a dropdown of the six statuses: choosing one saves it at once;
- **Generate resume** / **Regenerate resume** and **Generate cover letter** / **Regenerate cover letter** start the same background run as `POST /resume` and `POST /cover-letter`, with the same one-run-at-a-time rule, so a click while a run is going (from here or from the API) starts nothing new. Regenerating asks first; the new file replaces the old one only when the run succeeds. A cover letter needs posting text, and the bar shows the service's message when there is none. While a run is going the button says **Generating…** and the page re-reads the list every 5 seconds; when it finishes, the bar says so and the new PDF, scores, additions and gaps are shown in place (keeping the resume or cover letter view you are on), or it shows why the run failed;
- **Fill form** opens a new tab in the Herdr workspace `Claude-Jobs-Automation` (created if missing), labelled `<Company>-<Role>-<application id>`, and runs `claude --chrome "/job-application-form-filler <id>"` in the repo there. It is an ordinary interactive Claude Code session on the Mac mini: you approve its permissions and answer its questions in that tab, and it submits the application on its own unless a guardrail stops it and it asks you there (add `review` to the command to keep review-first). Clicking again while that tab is open says so and starts nothing. The button only helps when you are at the Mac mini, since the session drives the mini's Chrome. The session runs the `job-application-form-filler` skill in `.claude/skills/`, which reads your answers from your gitignored profile document;
- **Delete** asks you to confirm, naming the company and role, then removes the application and its report (its PDFs stay in the output folder).

Below the action bar, the selected application shows:

- the application's details and links, including its status, with the posting text collapsed;
- the base and generated scores against the threshold of 70, each with its keyword and requirement coverage;
- **What was added**: the posting keywords the judge approved and the tailored resume uses, and the requirements that improved from missing or partial;
- **Gaps still found**: the posting keywords and requirements the generated resume still doesn't cover, and the keywords the judge rejected with the reason;
- each requirement's base and generated assessment, with the quoted evidence;
- the base resume and the generated resume side by side, rendered by the browser's own PDF viewer (stacked, base first, on a narrow screen);
- a **Resume / Cover letter** switch above them: **Cover letter** shows the base letter (`data/COVER_LETTER.pdf`) beside the letter `POST /cover-letter` saved for the application, the same way. The letters load only when you switch to them, and the generated pane says so when no letter was written for the application. Choosing another application goes back to the resumes.

The page loads nothing from other origins and runs only its own script. Its data comes from six `GET` endpoints, documented under the `viewer` tag in `/docs`: `/applications`, `/application/{id}`, `/application/{id}/resume.pdf`, `/application/{id}/cover-letter.pdf`, `/resume/base.pdf` and `/cover-letter/base.pdf`. `/applications` also gives each application's latest resume and cover letter job state (`running`, `done` or `failed`, never the result), and `?job_link=<link>` narrows it to the one application with that dedupe key. It writes through seven more under the same tag, also without a key: `PATCH /viewer/application/{id}` with `{"status": "applied"}` changes only the status, `PUT /viewer/application/{id}/hidden` with `{"hidden": true}` (or `false`) hides the application from the viewer's list and shows it again, changing nothing else (`/applications` still returns it, with `hidden`), `DELETE /viewer/application/{id}` deletes the application but keeps its files, `POST /viewer/application/{id}/fill` opens the Fill form tab (503 `Herdr unavailable` when Herdr is not running), `POST /viewer/apply-from-link` with `{"link": "<url>"}` opens the link box's tab (same 503, and 422 for anything but an `http` or `https` link of at most 2048 characters with no spaces or user information), and `POST /viewer/application/{id}/resume` and `POST /viewer/application/{id}/cover-letter` start the same jobs as the keyed `POST /resume` and `POST /cover-letter` and answer the same 202. All seven answer 403 to a request the browser marks as coming from another site, so other websites can't trigger them. The keyed `PATCH` and `DELETE /application/{id}`, `POST /resume` and `POST /cover-letter` are unchanged and still need the key. A saved letter is looked for under the application's current company and then beside its resume, so one written before a company rename is still found. The scores come from a report `POST /resume` stores with each successful generation. The report keeps where the PDF was saved, but `/application/{id}` shows only its file name. Resumes generated before reports existed show "no report" next to their saved PDF; generating the resume again creates one.

Tests (no network needed):

```sh
.venv/bin/python -m pytest
sh scripts/test_smoke_test.sh       # smoke script, stubbed curl
sh scripts/test_install_service.sh  # install/uninstall/status scripts, stubbed sudo/launchctl
```

### Apply from a link

The link box in the viewer takes a job link and goes further than **Fill form**, which needs a recorded application with its resume. It opens a Herdr tab in the same workspace, labelled `ByLink-<host>-<hash>`, and runs `claude --chrome "/apply-from-link <link>"` in the repo. You can also run `/apply-from-link <url>` yourself in Claude Code on the Mac mini. If a tab for the same posting is already open, nothing new starts.

The session is interactive, like Fill form's, and works through these steps:

1. **Checks whether the posting is stored.** A stored `verified` application skips ahead to its missing documents. Any other status stops the run.
2. **Finds the official posting.** A LinkedIn or aggregator link is resolved through the employer's job board (Ashby, Greenhouse and Lever have public APIs) or careers page, since LinkedIn hides Apply links from the logged-out Chrome window. If nothing matches on both company and role, it asks you for the link.
3. **Applies the hard filters.** It drops recruiter and staffing posts, contract-only or unpaid roles, explicit refusals of sponsorship, postings with no full description, and pay ranges that top out below your floor. The floor comes from the Hard filters section of your profile document. Silence on pay or sponsorship passes. A dropped posting is not recorded, and the reason appears only in the tab.
4. **Records the application** with `added_via` `link`, and renames the tab to `<Company>-<Role>-<application id>`, so Fill form finds the session and the form filler can close it.
5. **Generates the resume**, and a cover letter only if the form has a cover letter field.
6. **Hands off to `job-application-form-filler`**. The form filler submits on its own unless a guardrail stops it.

**LinkedIn Easy Apply.** When a LinkedIn posting has no official posting, the question at step 2 also offers **It's LinkedIn Easy Apply**. Chrome is logged out of LinkedIn, so your answer is the only signal. Easy Apply stands in for the "official careers page only" filter, and every other filter still applies. The row is recorded as `linkedin_easy_apply` under the LinkedIn link, and the viewer shows an **Easy Apply** tag with no Fill form button. The run stops after the resume, with no cover letter and no form filler, and names the file. You apply on LinkedIn, then answer the Submitted question: on Yes it marks the application applied and closes its Chrome and Herdr tabs. On No nothing changes, and running the link again comes back to that question.

Tailored Attach may not appear on custom careers pages such as `cursor.com`. If enabling it for the site doesn't help, the session names the files to attach by hand.

## Running on the Mac mini

The service runs as a launchd daemon. It starts at boot without anyone logging in, restarts within about 10 seconds if it crashes, runs as your user (not root), and listens only on loopback: the four public endpoints (`GET /health`, `POST /application`, `POST /resume`, `POST /cover-letter`) on `127.0.0.1:8080`, and the full API plus its reference pages and the resume viewer on `127.0.0.1:8081`. Tailscale Funnel publishes port 8080 over HTTPS at your machine's `ts.net` hostname, reachable from the internet as well as your tailnet; every other path there answers 404, whatever API key it carries, because the launcher lets only those four method and path pairs through. Port 8081 is not published anywhere: you use it on the Mac mini itself. Neither is reachable directly on your LAN. Access control on the public address is the API key on the three `POST` endpoints. Job status, the application list, application edits and deletes, email status updates, generated resumes and cover letters, the viewer (whose status change, delete, Fill form and resume and cover letter generation need no key) and the API docs are all served only on port 8081.

### 1. Prerequisites

```sh
brew install python@3.12 tectonic tailscale

# Never sleep, and boot again after a power cut.
sudo pmset -a sleep 0 disksleep 0
sudo pmset -a autorestart 1
```

**FileVault:** if disk encryption is on, the Mac stops at the unlock screen after a reboot, and the service (and Tailscale) can't start until someone unlocks it at the machine. For planned restarts, use `sudo fdesetup authrestart`, which unlocks once on the way back up. After an unplanned power loss someone must unlock it in person. Turning FileVault off avoids this but leaves the disk unencrypted. Choose based on how physically secure the Mac is.

### 2. Tailscale

```sh
sudo brew services start tailscale   # tailscaled as a boot-time daemon (not the App Store app, which needs a login)
sudo tailscale up                    # sign in to your tailnet
```

In the Tailscale admin console, enable **MagicDNS** and **HTTPS certificates** (DNS page). Then publish the service with Funnel:

```sh
sudo tailscale funnel --bg --https=443 http://127.0.0.1:8080
tailscale funnel status   # "Funnel on": https://<machine>.<tailnet>.ts.net -> http://127.0.0.1:8080
```

If Funnel isn't allowed yet, the command prints an admin-console link to enable it for this machine. Use `--bg` so it keeps running after the terminal closes; the setting persists across reboots.

**Security:** with Funnel on, anyone on the internet can reach the service. The API key (keep it a 64-character random value) is the only protection, and there is no rate limiting yet. Give outside tools only the URL and `API_KEY`.

#### Local listener

The API reference, the resume viewer and every endpoint other than the four public ones are on port 8081, which you open on the Mac mini itself:
- API reference: `http://127.0.0.1:8081/docs`
- resume viewer: `http://127.0.0.1:8081/viewer`

Don't publish this port with `tailscale serve` or `tailscale funnel`: the viewer and its endpoints need no API key, so loopback is their only guard. The install and status scripts warn, and print the command that removes it, if any Tailscale mapping proxies port 8081. If an earlier install had you publish it on the tailnet, remove that mapping once:

```sh
tailscale serve --https=8444 off
tailscale serve status   # only :443 with Funnel -> 127.0.0.1:8080
```

The public address (`https://<machine>.<tailnet>.ts.net/docs`, `/viewer` or any path but the four) answers 404. The app decides by the local port a connection arrived on, which no request header can change. Write requests from the docs page still need the API key, and they are real: they change your application store and write resume files.

The local listener is always installed; pick another port with `DOCS_PORT=<port>`. `DOCS_PORT=off` is no longer accepted, since without it nothing could read job status or edit applications.

To go back to tailnet-only access:

```sh
sudo tailscale funnel --https=443 off
sudo tailscale serve --bg --https=443 http://127.0.0.1:8080
```

Resume tailoring also needs the [Claude Code CLI](https://code.claude.com/docs/en/setup), installed for your user (it usually lands in `~/.local/bin`; the install script finds it there).

### 3. Configure

```sh
cp .env.example .env
cp -n data/samples/* data/   # then replace them with your resume, profile and cover letter ("Your data")
# API_KEY: openssl rand -hex 32
# A Claude credential for resume tailoring, one of:
#   CLAUDE_CODE_OAUTH_TOKEN: run `claude setup-token` and paste the token as one line
#   ANTHROPIC_API_KEY:       a Claude Console API key, billed per run
chmod 600 .env
```

### 4. Install, check, uninstall

```sh
scripts/install_service.sh     # asks for your sudo password for the launchd steps
scripts/service_status.sh      # launchd state and pid, health check, docs listener, tailoring readiness, log size, sleep setting
scripts/uninstall_service.sh   # stops and removes the daemon; keeps output files and logs
```

The install script checks prerequisites and `.env` permissions, creates `.venv`, validates the configuration, does one test render to fill the TeX cache (so later renders work offline), installs `/Library/LaunchDaemons/local.job-hunt-hq.plist` with the path of your Claude Code CLI, waits for `/health`, checks that `/docs` and `/viewer` are 404 on port 8080 and 200 on port 8081, that `/healthz` and a status path are 404 on port 8080, and prints the local docs and viewer URLs, warning if a Tailscale mapping still proxies port 8081. Finally it checks resume tailoring: it warns when the Claude Code CLI or a Claude credential is missing, and makes one minimal live call (`python -m app.tailoring --check --live`) to confirm the credential works, warning if it is rejected. None of these warnings stops the install. It is safe to run again.

The daemon runs straight from this checkout. **After `git pull`, run `scripts/install_service.sh` again** (or `sudo launchctl kickstart -k system/local.job-hunt-hq` if only Python code changed).

The status script's `tailoring:` line reads, for example, `ready (subscription token, claude-opus-5-5, Claude Code 2.1.303)`, `not configured` or `FAILING (…)`. It checks the CLI and the credential kind without any model call. To confirm the credential itself works, run `.venv/bin/python -m app.tailoring --check --live` from the repository, which sends one minimal prompt.

Logs are in `~/Library/Logs/job-hunt-hq/`:
- `service.log`: requests (one JSON line per `/resume`, `/cover-letter` or `/application` request, with its `method`), one `resume_job` or `cover_letter_job` line per finished background job (its `outcome`, duration and match and Claude-run counts), and the access log without query strings. Rotated at 10 MB, 5 kept.
- `launchd.log`: anything printed before logging starts, such as import errors and crash tracebacks.

### 5. Verify

On the Mac (the smoke test reads the saved PDF from disk, so it must run there). The service returns only the file name, so the test looks for the PDF under `OUTPUT_DIR`, which defaults to the service's default. If your `.env` sets another `OUTPUT_DIR`, pass the same value:

```sh
API_KEY=... [OUTPUT_DIR=...] scripts/smoke_test.sh http://127.0.0.1:8080
```

First it checks that the given address answers 404 for `/docs`, `/openapi.json` and `/viewer`, and for `GET /healthz`, `GET /applications`, both status endpoints and a keyed `PATCH` and `DELETE /application`, all with the all-zero ID so nothing real can change, and for `POST /application/email-status` and `POST /viewer/apply-from-link` with an empty body. It also checks that the local listener (`DOCS_URL`, default `http://127.0.0.1:8081`; required) serves `/docs`, `/viewer` and a schema with the twenty-three operations, and sends its `POST /application/email-status` an `Applied` email for a company no application has, which must answer 404 `no_match` (an `Applied` email never writes anyway). Then it records a synthetic application and starts its resume on the given address, polls `GET /resume/{id}/status` on the local listener until the job is done (failing if it fails or takes over a minute), checks that `saved_path` is the bare file name and that the file in the application's folder under `OUTPUT_DIR` is a PDF, and removes the application (through the local listener) and its folder again if it created them. The application has no posting text (a leftover one from an older smoke test is cleared first, through the local listener), so the service saves the base resume without a Claude run, and the test fails unless `match.status` is `no_job_description`. It then asks for a cover letter, which must be refused with 422 for the same reason, with no file written. From another device, check that `https://<machine>.<tailnet>.ts.net/health` answers.

Then reboot the Mac without logging in and check that `https://<machine>.<tailnet>.ts.net/health` answers again.

### Retiring the old cloud deployment

Earlier versions ran on Google Cloud Run with Cloudflare R2 storage. Nothing in this repo uses them anymore. Once the Mac mini is verified, delete the Cloud Run service, the R2 bucket and its API token, and the Secret Manager secrets by hand. Links issued by the old deployment stop working when the bucket is deleted.
