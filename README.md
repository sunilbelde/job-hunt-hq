# job-hunt-hq

A small FastAPI service that runs on a Mac mini used as a personal server. `POST /application` records a job posting, and `POST /resume` renders a resume PDF for a recorded application and saves it on the Mac's disk at `OUTPUT_DIR/<company>/<application id>/SUNIL BELDE.pdf`. Nothing depends on a cloud service: storage, secrets and the process all live on the Mac, and it is published over HTTPS through [Tailscale](https://tailscale.com) Funnel, so both your own devices and outside tools (such as Muse) can call it.

The generation step is a stub: `generate_output` in `app/generation.py` receives the stored application but ignores its contents and renders the baseline resume (`data/BASE.tex` + `data/resume.cls`, compiled with [tectonic](https://tectonic-typesetting.github.io/)), so the PDF is equivalent to `data/BASE.pdf`. **Not implemented yet (backlog):** tailoring the resume to the posting; that change will replace the stub with generated TeX rendered through the same path.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /healthz`, `GET /health` | none | `200 {"status": "ok"}`, no storage access |
| `POST /resume` | `X-API-Key` | Body `{"application_id": "<uuid>"}`. Renders the resume from the stored application and saves it. `201 {"ok": true, "application_id", "saved_path", "cover_letter_path"}`, where `saved_path` is the resume's absolute path and `cover_letter_path` is where the cover letter goes, beside it (`SUNIL BELDE - Cover Letter.pdf`). Cover letters are not generated yet, so that path is a placeholder with no file. Errors are `{"ok": false, "message"}`: 401 bad key, 404 unknown application, 422 bad body, 500 render failure, 502 file write failure, 503 store failure |
| `POST /application` | `X-API-Key` | Records a verified posting. `201 {"ok": true, "application_id"}` for a new one, `200` with the existing ID if its `job_link` is already stored. Errors are `{"ok": false, "message"}`: 401 bad key, 422 bad body, 503 store failure |
| `PATCH /application/{application_id}` | `X-API-Key` | Changes the fields sent, e.g. `{"status": "applied"}`. `200 {"ok": true, "application_id", "status"}`. 401 bad key, 404 unknown ID, 422 bad body, 503 store failure |
| `DELETE /application/{application_id}` | `X-API-Key` | Permanently removes the row. `200 {"ok": true, "application_id"}`. 401 bad key, 404 unknown or already-deleted ID, 503 store failure |

Code layout: `app/main.py` (HTTP), `app/serve.py` (launcher for the installed service: public and docs listeners), `app/models.py` (`ResumeRequest`, `StoredApplication`, `ApplicationRow`, `ApplicationUpdate`, and the response shapes shown in the API docs), `app/applications.py` (application store and link dedupe), `app/generation.py` (stub generator), `app/rendering.py` (TeX to PDF), `app/storage.py` (resume file layout and atomic writes), `app/settings.py` (config), `app/log_filters.py` (keeps query strings out of access logs), `data/` (resume template assets), `deploy/` (launchd and logging templates, Tailscale docs-mapping check), `scripts/` (install, uninstall, status, smoke test).

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
| `ANTHROPIC_API_KEY` | no | Not used yet; reserved for resume tailoring |
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
#  "cover_letter_path":"/Users/you/Library/Application Support/job-hunt-hq/Acme/3f2b…/SUNIL BELDE - Cover Letter.pdf"}
# (no cover letter is generated yet; nothing exists at cover_letter_path)

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

### 3. Configure

```sh
cp .env.example .env
# API_KEY: openssl rand -hex 32
chmod 600 .env
```

### 4. Install, check, uninstall

```sh
scripts/install_service.sh     # asks for your sudo password for the launchd steps
scripts/service_status.sh      # launchd state and pid, health check, docs listener, log size, sleep setting
scripts/uninstall_service.sh   # stops and removes the daemon; keeps output files and logs
tailscale serve --https=8444 off   # after uninstalling, if you published the docs
```

The install script checks prerequisites and `.env` permissions, creates `.venv`, validates the configuration, does one test render to fill the TeX cache (so later renders work offline), installs `/Library/LaunchDaemons/local.job-hunt-hq.plist`, waits for `/health`, checks that `/docs` is 404 on port 8080 and 200 on port 8081, and prints the docs URLs. It is safe to run again.

The daemon runs straight from this checkout. **After `git pull`, run `scripts/install_service.sh` again** (or `sudo launchctl kickstart -k system/local.job-hunt-hq` if only Python code changed).

Logs are in `~/Library/Logs/job-hunt-hq/`:
- `service.log`: requests (one JSON line per `POST /resume` or `/application` request, the latter with its `method`) and the access log without query strings. Rotated at 10 MB, 5 kept.
- `launchd.log`: anything printed before logging starts, such as import errors and crash tracebacks.

### 5. Verify

On the Mac (the smoke test reads the saved PDF from disk, so it must run there):

```sh
API_KEY=... scripts/smoke_test.sh http://127.0.0.1:8080
```

First it checks that the given address answers 404 for `/docs` and `/openapi.json`, and that the docs listener (`DOCS_URL`, default `http://127.0.0.1:8081`; `DOCS_URL=off` skips it) serves `/docs` and a schema with the six operations. Then it records a synthetic application, generates its resume, checks the file is a PDF, and removes the application and its folder again if it created them. From another device, check that `https://<machine>.<tailnet>.ts.net/health` answers.

Then reboot the Mac without logging in and check that `https://<machine>.<tailnet>.ts.net/health` answers again.

### Retiring the old cloud deployment

Earlier versions ran on Google Cloud Run with Cloudflare R2 storage. Nothing in this repo uses them anymore. Once the Mac mini is verified, delete the Cloud Run service, the R2 bucket and its API token, and the Secret Manager secrets by hand. Links issued by the old deployment stop working when the bucket is deleted.
