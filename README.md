# job-hunt-hq

A small FastAPI service that runs on a Mac mini used as a personal server. `POST /jobs` takes a job posting, renders a resume PDF, stores it on the Mac's disk, and returns a signed download link that expires. Nothing depends on a cloud service: storage, links, secrets and the process all live on the Mac, and it is published over HTTPS through [Tailscale](https://tailscale.com) Funnel, so both your own devices and outside tools (such as Muse) can call it.

The generation step is a stub: `generate_output` in `app/generation.py` validates the posting but ignores its contents and renders the baseline resume (`data/BASE.tex` + `data/resume.cls`, compiled with [tectonic](https://tectonic-typesetting.github.io/)), so the PDF is equivalent to `data/BASE.pdf`. **Not implemented yet (backlog):** tailoring the resume to the posting; that change will replace the stub with generated TeX rendered through the same path.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /healthz`, `GET /health` | none | `200 {"status": "ok"}`, no storage access |
| `POST /jobs` | `X-API-Key` | `201 {"job_id", "url", "expires_at", "key"}`; 401 bad key, 422 bad body, 500 render failure, 502 storage failure |
| `GET /files/{key}?expires=…&sig=…` | signed link | The stored file. 403 for a missing, wrong or expired signature, 404 if the file is gone. This is the `url` returned by `POST /jobs` |

Code layout: `app/main.py` (HTTP, download route, hourly cleanup), `app/models.py` (`JobRow`), `app/generation.py` (stub generator), `app/rendering.py` (TeX to PDF), `app/storage.py` (local file storage, link signing, retention), `app/settings.py` (config), `app/log_filters.py` (keeps link signatures out of access logs), `data/` (resume template assets), `deploy/` (launchd and logging templates), `scripts/` (install, uninstall, status, smoke test).

### Request body (`JobRow`)

All values are plain strings and are not parsed or validated beyond type. Extra fields are ignored. Missing or empty required fields, or non-string values, return 422 (the error lists field names, never values).

| Field | Required |
|---|---|
| `company`, `role`, `full_job_description` | yes (non-empty) |
| `location`, `work_type`, `salary`, `date_posted`, `sponsorship`, `why_it_fits`, `job_link` | no |

### Storage and links

Files are written to `OUTPUT_DIR/outputs/YYYY-MM-DD/<uuid>.pdf`. The directory is readable only by your user. Download links are signed with `LINK_SIGNING_SECRET` (HMAC-SHA256) and expire after `SIGNED_URL_TTL_SECONDS`. They keep working across restarts. The service deletes files older than `OUTPUT_RETENTION_DAYS`, at startup and then every hour.

## Configuration

Copy `.env.example` to `.env` (git-ignored), fill it in and run `chmod 600 .env`. The service refuses to start if a required value is missing or invalid, and its errors never print the values.

| Variable | Required | Notes |
|---|---|---|
| `API_KEY` | yes | Sent by clients as `X-API-Key`. Generate it with `openssl rand -hex 32` |
| `LINK_SIGNING_SECRET` | yes | At least 32 characters; `openssl rand -hex 32`. Changing it invalidates every outstanding link, so rotate it if it leaks |
| `PUBLIC_BASE_URL` | yes | Base of the download links, e.g. `https://mac-mini.your-tailnet.ts.net` |
| `OUTPUT_DIR` | no | Default `~/Library/Application Support/job-hunt-hq`. Don't use `~/Documents`, `~/Desktop` or `~/Downloads`: macOS blocks background services from those folders |
| `OUTPUT_RETENTION_DAYS` | no | Default 30. Must be at least as long as the link lifetime |
| `SIGNED_URL_TTL_SECONDS` | no | Default and max 604800 (7 days) |
| `ANTHROPIC_API_KEY` | no | Not used yet; reserved for resume tailoring |

## Development

Rendering needs `tectonic` on your PATH; the first render downloads TeX packages into its cache.

```sh
brew install python@3.12 tectonic
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:create_app --factory --port 8080

curl -X POST localhost:8080/jobs -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"company":"Acme","role":"Software Engineer","full_job_description":"Build things."}'
```

Tests (no network needed):

```sh
.venv/bin/python -m pytest
sh scripts/test_smoke_test.sh       # smoke script, stubbed curl
sh scripts/test_install_service.sh  # install/uninstall/status scripts, stubbed sudo/launchctl
```

## Running on the Mac mini

The service runs as a launchd daemon. It starts at boot without anyone logging in, restarts within about 10 seconds if it crashes, runs as your user (not root), and listens only on `127.0.0.1:8080`. Tailscale Funnel publishes it over HTTPS at your machine's `ts.net` hostname, reachable from the internet as well as your tailnet. It is not reachable directly on your LAN. Access control is the API key for `POST /jobs` and the signed links for downloads.

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

**Security:** with Funnel on, anyone on the internet can reach the service. The API key (keep it a 64-character random value) and the link-signing secret are the only protection, and there is no rate limiting yet. Give outside tools only the URL and `API_KEY`.

To go back to tailnet-only access:

```sh
sudo tailscale funnel --https=443 off
sudo tailscale serve --bg --https=443 http://127.0.0.1:8080
```

### 3. Configure

```sh
cp .env.example .env
# API_KEY and LINK_SIGNING_SECRET: openssl rand -hex 32
# PUBLIC_BASE_URL: the https://<machine>.<tailnet>.ts.net URL from `tailscale funnel status`
chmod 600 .env
```

### 4. Install, check, uninstall

```sh
scripts/install_service.sh     # asks for your sudo password for the launchd steps
scripts/service_status.sh      # launchd state and pid, health check, log size, sleep setting
scripts/uninstall_service.sh   # stops and removes the daemon; keeps output files and logs
```

The install script checks prerequisites and `.env` permissions, creates `.venv`, validates the configuration, does one test render to fill the TeX cache (so later renders work offline), installs `/Library/LaunchDaemons/local.job-hunt-hq.plist` and waits for `/health`. It is safe to run again.

The daemon runs straight from this checkout. **After `git pull`, run `scripts/install_service.sh` again** (or `sudo launchctl kickstart -k system/local.job-hunt-hq` if only Python code changed).

Logs are in `~/Library/Logs/job-hunt-hq/`:
- `service.log`: requests (one JSON line per `POST /jobs`), access log without query strings, and cleanup. Rotated at 10 MB, 5 kept.
- `launchd.log`: anything printed before logging starts, such as import errors and crash tracebacks.

### 5. Verify

From another device (any network, since Funnel is public):

```sh
API_KEY=... scripts/smoke_test.sh https://<machine>.<tailnet>.ts.net
```

Then reboot the Mac without logging in and check that `https://<machine>.<tailnet>.ts.net/health` answers again.

### Retiring the old cloud deployment

Earlier versions ran on Google Cloud Run with Cloudflare R2 storage. Nothing in this repo uses them anymore. Once the Mac mini is verified, delete the Cloud Run service, the R2 bucket and its API token, and the Secret Manager secrets by hand. Links issued by the old deployment stop working when the bucket is deleted.
