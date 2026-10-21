# job-hunt-hq

A small FastAPI service that runs on a Mac mini used as a personal server. `POST /application` records a job posting, and `POST /resume` renders a resume PDF for a recorded application and saves it on the Mac's disk at `OUTPUT_DIR/<company>/<application id>/SUNIL BELDE.pdf`. Nothing depends on a cloud service: storage, secrets and the process all live on the Mac, and it is published over HTTPS through [Tailscale](https://tailscale.com) Funnel, so both your own devices and outside tools (such as Muse) can call it.

Each resume is matched against the application's posting. Claude scores the base resume (`data/BASE.tex` + `data/resume.cls`, compiled with [tectonic](https://tectonic-typesetting.github.io/)). Below 70 it reworks the wording, order and emphasis of the base resume's own facts into the same one-page template, and scripts check every rule. Posting keywords the base resume lacks get in only when a separate Claude judge finds them in your resume or your profile list (`data/PROFILE.md`). See [How resumes are tailored](#how-resumes-are-tailored). **Backlog:** growing the profile list into a full profile document, a second source of facts that tailoring can add on top of the base resume (marked `TODO(profile-doc)` in the code), and cover letters.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /healthz`, `GET /health` | none | `200 {"status": "ok"}`, no storage access |
| `POST /resume` | `X-API-Key` | Body `{"application_id": "<uuid>"}`. Scores the base resume against the stored posting, tailors it below 70, and saves it. Takes about 1–5 minutes when it runs Claude, so use a client timeout of at least 10 minutes. `201 {"ok": true, "application_id", "saved_path", "cover_letter_path", "match"}`, where `saved_path` is the resume's absolute path, `cover_letter_path` is where the cover letter goes, beside it (`SUNIL BELDE - Cover Letter.pdf`), and `match` is `{"status", "threshold", "base_score", "tailored_score", "added_terms"}`. Cover letters are not generated yet, so that path is a placeholder with no file. Errors are `{"ok": false, "message"}`: 401 bad key, 404 unknown application, 422 bad body, 500 render or tailoring failure, 502 file write failure, 503 store failure |
| `POST /application` | `X-API-Key` | Records a verified posting. `201 {"ok": true, "application_id"}` for a new one, `200` with the existing ID if its `job_link` is already stored. Errors are `{"ok": false, "message"}`: 401 bad key, 422 bad body, 503 store failure |
| `PATCH /application/{application_id}` | `X-API-Key` | Changes the fields sent, e.g. `{"status": "applied"}`. `200 {"ok": true, "application_id", "status"}`. 401 bad key, 404 unknown ID, 422 bad body, 503 store failure |
| `DELETE /application/{application_id}` | `X-API-Key` | Permanently removes the row. `200 {"ok": true, "application_id"}`. 401 bad key, 404 unknown or already-deleted ID, 503 store failure |

Code layout: `app/main.py` (HTTP), `app/serve.py` (launcher for the installed service: public and docs listeners), `app/models.py` (`ResumeRequest`, `StoredApplication`, `ApplicationRow`, `ApplicationUpdate`, and the response shapes shown in the API docs), `app/applications.py` (application store and link dedupe), `app/generation.py` (picks the base or tailored resume), `app/tailoring.py` (runs the tailor-resume skill and its judge headlessly, and the final gate), `.claude/skills/tailor-resume/` (the skill and its scripts), `.claude/skills/judge-resume-terms/` (the judge), `app/rendering.py` (TeX to PDF), `app/storage.py` (resume file layout and atomic writes), `app/settings.py` (config), `app/log_filters.py` (keeps query strings out of access logs), `data/` (resume template assets and your profile list), `deploy/` (launchd and logging templates, Tailscale docs-mapping check), `scripts/` (install, uninstall, status, smoke test).

### Request body (`POST /resume`)

`{"application_id": "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"}`: the ID returned by `POST /application`, as a JSON string. Everything else (company, role, job description and so on) is read from the stored application, so record or `PATCH` the posting first. Extra fields are ignored. A missing or non-string ID (`7`, `7.5`, `true`) is a 422; a string that is not a UUID or names no stored application is a 404. Generating a resume never changes the application, its status included, and works for any status.

### Request body (`ApplicationRow`)

Strings only, extra fields ignored, and a 422 message names fields but never values.

| Field | Required |
|---|---|
| `company`, `role`, `job_link` | yes (non-empty) |
| `posting_source_type` | yes: `recruiting_platform` or `employer_site` |
| `verification_method` | yes: `official_apply_match` or `employer_site` |
| `official_apply_url` | yes (may be `""`) |
| `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `company_careers_url`, `official_employer_domain`, `full_job_description` | no |

Only two combinations are verified, and anything else is a 422:

- `recruiting_platform` + `official_apply_match`, with `official_apply_url` equal to `job_link` byte-for-byte
- `employer_site` + `employer_site`, with `official_apply_url` set to `""`

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
- `job_link`, `posting_source_type`, `verification_method` and `official_apply_url` can't be changed. A body that contains any of them is a 422, even if the value matches
- unknown fields are ignored, and a body with nothing to update is a 422

An unknown ID returns 404, checked before the body, and a bad key returns 401 before either.

**IDs** are random UUIDs (version 4), returned in lower case, such as `3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13`. They say nothing about how many applications exist or in what order they were recorded; sort by `created_at` if you need order. Paths and bodies accept the hyphenated form in any letter case. Any other path value, including an old integer ID, is a 404; in the `POST /resume` body a JSON number is a 422.

**Deleting** is permanent and frees the link: posting it again creates a new row with a new ID. To stop tracking a posting but keep its record, set `status` to `withdrawn` instead.

Rows live in `OUTPUT_DIR/applications.sqlite3` (mode 600). To back it up while the service runs:

```sh
sqlite3 ~/Library/Application\ Support/job-hunt-hq/applications.sqlite3 ".backup applications-backup.sqlite3"
```

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
2. **Judge.** If the posting uses keywords the base resume lacks, the judge decides which of them you genuinely have. It runs in a folder of its own and sees your resume, your profile list and those keywords, never the posting, so the job can't sway it. It approves a keyword only with evidence, which a script then checks: a passage of your resume that implies it (for example "automated code validation" for testing), or an entry of your profile list.
3. **Tailoring.** `tailor-resume` runs again and reworks the resume, using approved keywords only where their evidence allows. `match.added_terms` lists the ones it used.

How it decides:

- **The score.** Claude lists the posting's keywords and requirements. A script finds the keywords in the resume (whole words, ignoring case, with listed aliases), and accepts a requirement as met only with a quote that really appears in the resume. The score is half keyword coverage and half requirement coverage, with required items counting double.
- **No fabrication.**
  - The name and contact line, education, job headings and certifications are copied from `BASE.tex` and can't change.
  - Skills may be reordered, regrouped under the existing labels, or dropped. The only new items allowed are keywords the judge approved.
  - Every bullet cites the base bullets of the same job it comes from, and every number in it must appear in them.
  - A posting keyword the base resume lacks can appear only if the judge approved it: in a skills line, or in a bullet that comes from the base bullet holding its resume evidence. A keyword approved from your profile list alone goes in a skills line only. No keyword the base resume has can disappear.
- **Your profile list.** `data/PROFILE.md` lists skills and abilities you have beyond `BASE.tex`, one per line starting with `- `, and the judge treats each one as true. Name the tools you have used: an entry "Browser automation" doesn't tell the judge you have used Playwright. Nothing else reads the file. A keyword the judge rejects is simply left out, and never fails a request.
- **Same template, one page, used fully.** Claude writes plain text; a script splices it into `BASE.tex`, so preamble, spacing and fonts never change. The result must be exactly one page, fill at least 90% of it and keep every line inside the margins. The skill keeps revising toward 96% fill, and toward no bullet whose last line holds only a word or two.
- **The final gate.** Before saving, the service re-checks the output with its own untouched copy of the scripts and template, and saves only the PDF it rendered itself. It scores against the analysis as it stood when the judge ruled, and allows only the keywords of its own copy of the ruling, so the tailoring run can't change either.
- **Failures.** If Claude isn't configured or available, a run hits the time or spend limit, the judge's output is unusable, or the content fails a check, the request fails with 500 `Resume generation failed`. Nothing is saved, any earlier resume is kept, and the log line `tailoring_error` gives the stage (`analysis`, `judge`, `tailoring` or `verify`) and reason codes.
- **Isolation.** Posting text is treated as untrusted data. Each Claude run works in a temporary folder with an empty `HOME` and its own config folder (`OUTPUT_DIR/.claude-runtime/`). It has no web or MCP tools, can only run the skill's script and read-only commands inside that folder (the judge runs no commands at all), and its commands never see the credential. Your own Claude Code settings, hooks and shell profile are never loaded.
- **Cost and limits.** With `CLAUDE_CODE_OAUTH_TOKEN`, runs use your Claude plan. On Pro that plan's limits are shared with your own Claude Code use, and a run that hits them fails. With `ANTHROPIC_API_KEY`, runs are billed per use: roughly 1–2 USD per tailored resume, less when the base resume already matches. `TAILORING_TIMEOUT_SECONDS` and `TAILORING_MAX_BUDGET_USD` cover all the runs for one resume together. Each `resume_request` log line records the runs' turns and estimated cost, and how many keywords the judge approved and rejected (counts only, never the keywords).

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

### Resume files

Each resume is saved at `OUTPUT_DIR/<company folder>/<application id>/SUNIL BELDE.pdf`, using the application's company at the time you generate. The folder keeps the company name as written (spaces, case, accents), with `/`, `\`, `:` and control characters replaced by `-`, leading and trailing spaces and dots removed, and the name cut to 100 characters. An empty result becomes `unknown-company`, and a name starting with `applications.sqlite3` gets a leading `_` so it can't collide with the store.

- Generating again for the same application replaces the file in one step; a failed render or write leaves the previous file intact.
- Folders are readable only by your user and files are mode 600. The service doesn't serve them over HTTP.
- Files are kept until you delete them. Deleting an application, or renaming its company, leaves existing resume folders where they are.

### Upgrading from `POST /jobs`

`POST /jobs`, `GET /files/...` and signed download links are gone (both return 404). Record the posting with `POST /application`, then call `POST /resume` with the returned ID, and read errors from `ok`/`message` rather than `detail`. `LINK_SIGNING_SECRET`, `PUBLIC_BASE_URL`, `SIGNED_URL_TTL_SECONDS` and `OUTPUT_RETENTION_DAYS` are no longer used: remove them from `.env` (they're ignored if left in). Files under `OUTPUT_DIR/outputs/` from the old endpoint are no longer served or cleaned up; delete that folder by hand.

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
| `API_DOCS_ENABLED` | no | Default `false`. `true` serves the API reference at `/docs`, `/redoc` and `/openapi.json` on a development server. The installed service ignores it: its public port never serves docs, and its docs port always does |

## Development

Rendering needs `tectonic` on your PATH; the first render downloads TeX packages into its cache.

```sh
brew install python@3.12 tectonic
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:create_app --factory --port 8080

ID=$(curl -s -X POST localhost:8080/application -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"company":"Acme","role":"Software Engineer","job_link":"https://www.acme.com/careers/1","posting_source_type":"employer_site","verification_method":"employer_site","official_apply_url":""}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["application_id"])')
echo "$ID"
# 3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13   (201; 200 with the same id when sent again)

curl -X POST localhost:8080/resume -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' -d "{\"application_id\":\"$ID\"}"
# {"ok":true,"application_id":"3f2b…","saved_path":"/Users/you/Library/Application Support/job-hunt-hq/Acme/3f2b…/SUNIL BELDE.pdf",
#  "cover_letter_path":"/Users/you/Library/Application Support/job-hunt-hq/Acme/3f2b…/SUNIL BELDE - Cover Letter.pdf",
#  "match":{"status":"no_job_description","threshold":70,"base_score":null,"tailored_score":null,"added_terms":[]}}
# (this posting has no text, so nothing was scored; no cover letter is generated yet)

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

On the installed service the reference is on a separate, tailnet-only listener (see [API docs on the tailnet](#api-docs-on-the-tailnet)):
- on the Mac mini: `http://127.0.0.1:8081/docs`
- from your tailnet devices: `https://<machine>.<tailnet>.ts.net:8444/docs`

The public address never serves these pages. Requests sent from there change your real application store and write real resume files.

Tests (no network needed):

```sh
.venv/bin/python -m pytest
sh scripts/test_smoke_test.sh       # smoke script, stubbed curl
sh scripts/test_install_service.sh  # install/uninstall/status scripts, stubbed sudo/launchctl
```

## Running on the Mac mini

The service runs as a launchd daemon. It starts at boot without anyone logging in, restarts within about 10 seconds if it crashes, runs as your user (not root), and listens only on loopback: the API on `127.0.0.1:8080`, and the same API plus its reference pages on `127.0.0.1:8081`. Tailscale Funnel publishes port 8080 over HTTPS at your machine's `ts.net` hostname, reachable from the internet as well as your tailnet. Port 8081 is published to your tailnet only. Neither is reachable directly on your LAN. Access control is the API key on `POST /resume` and the `/application` endpoints. Generated files are never served over HTTP, and the public address never serves the API docs.

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

#### API docs on the tailnet

Publish the docs listener to your tailnet only, on HTTPS port 8444:

```sh
tailscale serve --bg --https=8444 http://127.0.0.1:8081
tailscale serve status   # :443 with Funnel -> 127.0.0.1:8080; :8444 tailnet only -> 127.0.0.1:8081
```

Then open the API reference:
- on the Mac mini: `http://127.0.0.1:8081/docs`
- from any device on your tailnet: `https://<machine>.<tailnet>.ts.net:8444/docs`

The public address (`https://<machine>.<tailnet>.ts.net/docs`) answers 404. The app decides by the local port a connection arrived on, which no request header can change, and Funnel can only publish ports 443, 8443 and 10000, so 8444 can't be made public by mistake. The install and status scripts warn if Funnel ever publishes the docs listener.

Anyone on your tailnet can open the docs. Requests from the page still need the API key, and they are real: they change your application store and write resume files. If others share your tailnet, add a rule to your tailnet policy file that allows `tcp:8444` on the Mac mini only from your own user.

To install without the docs listener, run `DOCS_PORT=off scripts/install_service.sh`. Pick another port with `DOCS_PORT=<port>` and point `tailscale serve` at it.

To go back to tailnet-only access:

```sh
sudo tailscale funnel --https=443 off
sudo tailscale serve --bg --https=443 http://127.0.0.1:8080
```

Resume tailoring also needs the [Claude Code CLI](https://code.claude.com/docs/en/setup), installed for your user (it usually lands in `~/.local/bin`; the install script finds it there).

### 3. Configure

```sh
cp .env.example .env
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
tailscale serve --https=8444 off   # after uninstalling, if you published the docs
```

The install script checks prerequisites and `.env` permissions, creates `.venv`, validates the configuration, does one test render to fill the TeX cache (so later renders work offline), installs `/Library/LaunchDaemons/local.job-hunt-hq.plist` with the path of your Claude Code CLI, waits for `/health`, checks that `/docs` is 404 on port 8080 and 200 on port 8081, and prints the docs URLs. Finally it checks resume tailoring: it warns when the Claude Code CLI or a Claude credential is missing, and makes one minimal live call (`python -m app.tailoring --check --live`) to confirm the credential works, warning if it is rejected. None of these warnings stops the install. It is safe to run again.

The daemon runs straight from this checkout. **After `git pull`, run `scripts/install_service.sh` again** (or `sudo launchctl kickstart -k system/local.job-hunt-hq` if only Python code changed).

The status script's `tailoring:` line reads, for example, `ready (subscription token, claude-opus-5-5, Claude Code 2.1.303)`, `not configured` or `FAILING (…)`. It checks the CLI and the credential kind without any model call. To confirm the credential itself works, run `.venv/bin/python -m app.tailoring --check --live` from the repository, which sends one minimal prompt.

Logs are in `~/Library/Logs/job-hunt-hq/`:
- `service.log`: requests (one JSON line per `POST /resume` or `/application` request, the latter with its `method`) and the access log without query strings. Rotated at 10 MB, 5 kept.
- `launchd.log`: anything printed before logging starts, such as import errors and crash tracebacks.

### 5. Verify

On the Mac (the smoke test reads the saved PDF from disk, so it must run there):

```sh
API_KEY=... scripts/smoke_test.sh http://127.0.0.1:8080
```

First it checks that the given address answers 404 for `/docs` and `/openapi.json`, and that the docs listener (`DOCS_URL`, default `http://127.0.0.1:8081`; `DOCS_URL=off` skips it) serves `/docs` and a schema with the six operations. Then it records a synthetic application, generates its resume, checks the file is a PDF, and removes the application and its folder again if it created them. The application has no posting text (a leftover one from an older smoke test is cleared first), so the service saves the base resume without a Claude run, and the test fails unless `match.status` is `no_job_description`. From another device, check that `https://<machine>.<tailnet>.ts.net/health` answers.

Then reboot the Mac without logging in and check that `https://<machine>.<tailnet>.ts.net/health` answers again.

### Retiring the old cloud deployment

Earlier versions ran on Google Cloud Run with Cloudflare R2 storage. Nothing in this repo uses them anymore. Once the Mac mini is verified, delete the Cloud Run service, the R2 bucket and its API token, and the Secret Manager secrets by hand. Links issued by the old deployment stop working when the bucket is deleted.
