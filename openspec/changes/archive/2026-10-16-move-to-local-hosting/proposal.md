# Proposal

## Why

The service was built for Google Cloud Run, with Cloudflare R2 for storage and Secret Manager for secrets. It is moving to a dedicated Mac mini that serves as an isolated, always-on personal server, and it should run there with no cloud accounts or services. Generated PDFs, download links, secrets and the process lifecycle all need to live on that machine, and only the owner's devices should reach it, over Tailscale.

## What Changes

- **BREAKING** Generated files go to a directory on the local filesystem instead of Cloudflare R2. `R2Storage` and the `boto3` dependency are removed.
- **BREAKING** The service itself creates download links: signed with HMAC, expiring, and served from a new unauthenticated `GET /files/{key}` endpoint that checks the signature. They replace R2 pre-signed URLs. Links are built from a configured public base URL, normally the Mac's Tailscale HTTPS name.
- **BREAKING** Configuration: the `R2_*` variables are removed. `OUTPUT_DIR`, `PUBLIC_BASE_URL`, `LINK_SIGNING_SECRET` and `OUTPUT_RETENTION_DAYS` are added. `API_KEY`, `SIGNED_URL_TTL_SECONDS` and the optional `ANTHROPIC_API_KEY` stay. Secrets live only in a git-ignored `.env` that only its owner can read (mode 600).
- The service deletes stored files older than the retention period itself, at startup and then hourly. This replaces the R2 lifecycle rule.
- The service runs natively under launchd as a LaunchDaemon. It starts at boot without anyone logging in, restarts if it crashes, binds to `127.0.0.1`, and writes logs to a file under `~/Library/Logs`. Scripts install and uninstall it, and check its status.
- Tailscale (`tailscale serve`) exposes the service only to the owner's tailnet, over HTTPS.
- Tectonic and Python 3.12 are installed with Homebrew. A bootstrap step fills tectonic's package cache once so later renders work offline.
- **BREAKING** Cloud deployment is removed: the `Dockerfile`, `.dockerignore`, and the Cloud Run, R2 and Secret Manager sections of the README. The README section for the missing `scripts/read_sheet.sh` (Google Sheets) is also removed, because that script isn't in the repo.
- Stays the same: the `POST /jobs` request, response shape and auth; the `/healthz` and `/health` endpoints; rendering; and the stub generator. The Anthropic API key stays optional, for the later resume-tailoring change. That change is the only one that will call out to a network service.

## Capabilities

### New Capabilities
- `local-service-hosting`: running the service on the Mac mini. Covers the launchd lifecycle (start at boot, restart on crash), binding to localhost only, log files, install, uninstall and status scripts, and private access over Tailscale.

### Modified Capabilities
- `output-storage`: storage moves from R2 objects to files under `OUTPUT_DIR`. Links are signed by the service instead of pre-signed by R2. Files are deleted after a retention period. Files are private: the only way to fetch one is a valid signed link.
- `job-api`: the `url` in the response becomes a signed link served by this service. Adds the `GET /files/{key}` download endpoint. The storage-failure scenario changes from R2 to local disk. Cloud Run is no longer mentioned in the health endpoint requirement.
- `service-config`: the variable set changes (R2 removed; output directory, public base URL, signing secret and retention added). Startup also checks that the output directory is writable and that retention covers the link TTL.
- `resume-pdf-rendering`: offline rendering and the bundled template files now refer to the host install (Homebrew tectonic with a warmed cache, `data/` in the repo) instead of a container image.

## Impact

- **Code**: `app/storage.py` (R2 replaced by local storage and link signing), `app/main.py` (download route, cleanup task, building app objects from the new settings), `app/settings.py`, and the matching tests. `tests/conftest.py` and `tests/test_storage.py` get substantial rewrites.
- **Dependencies**: `boto3` removed. No new Python dependencies: signing uses the standard library's `hmac`. Host prerequisites: Homebrew `python@3.12`, `tectonic` and `tailscale`. The system Python is 3.9 and can't run the code.
- **New files**: a launchd plist template under `deploy/`, plus `scripts/install_service.sh`, `scripts/uninstall_service.sh` and `scripts/service_status.sh`.
- **Removed files**: `Dockerfile` and `.dockerignore`.
- **API**: the request and response shape of `POST /jobs` is unchanged. Download URLs now point at this service instead of R2, so links issued before the migration stop working.
- **Ops**: no cloud accounts, credentials or bills. Backups and disk space for `OUTPUT_DIR` are now handled on the Mac.
