# Design

## Context

The service is a single FastAPI app (`app/main.py`, built by `create_app()`). Storage goes through a small `Storage` protocol with `upload()` and `presigned_url()`, and `R2Storage` is the only implementation. Rendering shells out to `tectonic`. Today the container image provides tectonic and a pre-warmed package cache, and Cloud Run keeps the process alive. On the Mac mini none of that exists yet. The system `python3` is 3.9, but the code uses `X | None` syntax, which needs Python 3.10 or later. Tectonic and Tailscale aren't installed. The repo lives at a path that contains a space (`.../claude Projects/job-hunt-hq`), so every script and plist must quote paths.

The motivation is in proposal.md, and the requirements are in the delta specs.

## Goals / Non-Goals

**Goals:**
- Keep the storage seam: replace `R2Storage` with a local implementation behind the same protocol so `main.py` changes are limited to wiring and the new download route.
- One install command on a prepared Mac, safe to run again.
- The service survives reboots, crashes and an unattended power cut, with no one logged in.

**Non-Goals:**
- Resume tailoring and any LLM integration. The Anthropic key is only carried through as optional config.
- Multiple worker processes, a render concurrency limit, or a queue. One owner, low volume.
- Backups of `OUTPUT_DIR`. Outputs can be regenerated and are deleted after 30 days anyway.
- Removing existing cloud resources (the Cloud Run service, the R2 bucket, Secret Manager secrets). That's for the owner to do by hand, and the README will say so.
- Serving to the public internet. Tailscale Funnel and port forwarding are explicitly not used.

## Decisions

### 1. Local filesystem storage with atomic writes
`LocalStorage(root)` writes to `root/outputs/YYYY-MM-DD/<uuid>.<ext>`. It reuses `build_key()` unchanged. Each write goes to a `.tmp-<uuid>` file in the same directory, is fsynced, then renamed into place with `os.replace`, which makes it atomic on the same volume. Directories are created with mode `0700`, and `OSError` is wrapped in `StorageError`, so the existing 502 path in `main.py` keeps working.
*Alternative:* SQLite or a self-hosted S3 such as MinIO. Rejected: extra moving parts for single-file blobs, and MinIO would keep boto3 around for no benefit.

### 2. Download links signed by the service with HMAC
Link format: `{PUBLIC_BASE_URL}/files/{key}?expires=<unix>&sig=<hex>`. `sig` is the HMAC-SHA256, keyed with `LINK_SIGNING_SECRET`, of `"{key}\n{expires}"`. Verification uses `hmac.compare_digest`. This lives in a small `LinkSigner` in `app/storage.py`. `LocalStorage.presigned_url()` delegates to it, so the protocol method name stays and `main.py`'s call doesn't change. Links are stateless, so they survive restarts.
*Alternatives:* (a) A random token per file stored in a database. Rejected: it's state that needs persisting and expiring, for no extra benefit. (b) Reusing `API_KEY` as the HMAC key. Rejected: changing the API key would silently invalidate every link, and the two secrets protect different things.

### 3. `GET /files/{key:path}` route
The route is not protected by the API key, and the order of checks is fixed:
1. Match the key against `^outputs/\d{4}-\d{2}-\d{2}/[0-9a-f-]{36}\.[a-z0-9]{1,8}$`. On failure, return 403. This happens before any filesystem access and blocks path traversal.
2. Check `expires` and `sig`. On failure, return 403.
3. Resolve the path and confirm it is under the output root.
4. If the file is missing, return 404.
5. Otherwise return a `FileResponse`.

Content-Type comes from the extension through a small map (`pdf` → `application/pdf`, falling back to `mimetypes`). The generator always pairs a content type with an extension, so storing a sidecar file isn't needed. The logging middleware already filters on `path == "/jobs"`, so downloads don't produce `job_request` lines, and the query string (which holds the signature) is never logged.

### 4. Retention runs inside the app
A FastAPI lifespan task runs `storage.cleanup(max_age)` in the threadpool at startup and then every hour. It deletes files whose mtime is older than the retention period, removes `.tmp-*` files older than one hour (left over from interrupted writes), and removes empty date directories. Each failure is logged and skipped.
*Alternative:* a separate launchd job that runs a cleanup script. Rejected: a second job to install and keep in sync, when the app already has the configuration.

### 5. Settings
The `r2_*` fields are removed. New fields:
- `link_signing_secret: SecretStr`, at least 32 characters.
- `public_base_url`, validated as an absolute http(s) URL with any trailing slash stripped.
- `output_dir: Path`, defaulting to `~/Library/Application Support/job-hunt-hq`.
- `output_retention_days: int`, default 30, greater than 0.

A `model_validator` enforces `retention_days * 86400 >= ttl`. Settings validation has no side effects. Creating the directory and checking that it's writable happens in `LocalStorage.__init__`, which `create_app()` calls, so a bad `OUTPUT_DIR` still stops startup, with a `StorageError` naming `OUTPUT_DIR`. `.env` is resolved relative to the process working directory, and launchd sets that to the repo root.

### 6. launchd LaunchDaemon with `UserName`, not a LaunchAgent
`/Library/LaunchDaemons/local.job-hunt-hq.plist` has these keys:
- `UserName` = the owner's account
- `WorkingDirectory` = the repo
- `ProgramArguments` = `.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080`
- `RunAtLoad` and `KeepAlive` = true
- `ThrottleInterval` = 10
- `EnvironmentVariables`: `HOME`, `PATH` (including `/opt/homebrew/bin` for tectonic) and `TECTONIC_CACHE_DIR` = `~/Library/Caches/job-hunt-hq/tectonic`
- `StandardOutPath` and `StandardErrorPath` under `~/Library/Logs/job-hunt-hq/`

A daemon starts at boot. A LaunchAgent would wait for a GUI login, which breaks "always running" on a headless server. `HOME` and `PATH` must be set explicitly, because daemons don't inherit a login shell environment. The plist is a template in `deploy/` with `__REPO__`, `__USER__` and `__HOME__` placeholders. The install script fills them in and escapes them for XML.
*Alternative:* Homebrew `brew services`. Rejected: it's meant for brew formulae, not a project checkout.

### 7. Install and uninstall scripts
`scripts/install_service.sh` runs as the owner and uses `sudo` only for system paths. Steps:
1. Check prerequisites: `python3.12`, `tectonic`, and `.env` present with mode `600` (or stricter).
2. Create or refresh `.venv` with `python3.12` and run `pip install -r requirements.txt`.
3. Validate the config by importing `create_app` and building it once, and print only the error.
4. Warm the tectonic cache by running one render with the same `TECTONIC_CACHE_DIR`.
5. Fill in the plist template, install it as `root:wheel 644`, then `launchctl bootout` (ignoring errors) and `launchctl bootstrap system`.
6. Fill in `deploy/logging.json` and truncate `launchd.log`.
7. Poll `http://127.0.0.1:8080/health` for up to 30 seconds.

`uninstall_service.sh` runs bootout, removes the plist, and leaves the output data and logs alone. `service_status.sh` combines `launchctl print system/local.job-hunt-hq` (state and pid) with a curl to `/health`.

### 8. The app rotates its own logs
uvicorn starts with `--log-config deploy/logging.json`. The install script fills in that file from a template with the absolute log path. It sends the `uvicorn`, `uvicorn.access`, `uvicorn.error` and `app.requests` loggers to a `RotatingFileHandler` at `~/Library/Logs/job-hunt-hq/service.log` (10 MB, 5 backups). uvicorn applies the log config before importing the app, so the fallback handler in `main.py` (added only when the logger has no handlers) stays unused. launchd's `StandardOutPath` and `StandardErrorPath` point at `launchd.log` in the same directory. That file only catches output from before logging is configured, such as import errors and crash tracebacks, so it stays small, and the install script truncates it on each install.
*Alternative:* let launchd capture all output and rotate it with newsyslog. Rejected: newsyslog moves the file aside, and uvicorn doesn't reopen its stdout on a signal, so lines after rotation would go to a file that has been moved or compressed and deleted.

### 9. Tailscale for remote access
Install the Homebrew `tailscale` formula and run `tailscaled` as a root daemon with `sudo brew services start tailscale`, so it is up at boot without a login. The Mac App Store app only runs after a GUI login, so it isn't used. Then run `tailscale up`, enable MagicDNS and HTTPS certificates in the tailnet admin console, and run `tailscale serve --bg --https=443 http://127.0.0.1:8080`. The serve configuration persists across reboots. `PUBLIC_BASE_URL` is then `https://<machine>.<tailnet>.ts.net`. Tailscale terminates TLS, so the app never handles certificates. These steps are manual and documented in the README. The install script only warns if `tailscale serve status` shows nothing proxied to port 8080.

### 10. Mac power settings
The README prerequisites include:
- `sudo pmset -a sleep 0 disksleep 0` (the Mac never sleeps)
- `sudo pmset -a autorestart 1` (boots again after a power loss)
- optionally `womp 1`

`service_status.sh` reports the current `sleep` value as a hint.

### 11. Removals
- Delete `Dockerfile` and `.dockerignore`.
- Remove `boto3` from `requirements.txt`.
- Delete `R2Storage` and the botocore logger settings in `main.py`.
- Rewrite the README "Deploying" section and replace it with "Running on the Mac mini".
- Remove the README section about the missing `read_sheet.sh`.

## Risks / Trade-offs

- [FileVault holds the boot at the unlock screen, so the daemon can't start until someone unlocks the disk] → Document it. Use `sudo fdesetup authrestart` for planned restarts. After an unplanned power loss, someone must unlock it in person, because Tailscale isn't running yet at the unlock screen. Or the owner turns FileVault off, accepting that the disk is unencrypted. The README presents this trade-off and leaves the choice to the owner.
- [The service runs directly from the repo checkout, so editing code or switching branches changes what runs after the next restart] → Document this: run `install_service.sh` (or `launchctl kickstart -k`) after pulling. It's acceptable for a personal server and avoids keeping a deploy copy in sync.
- [Tailscale's coordination server is a third-party service] → It only brokers keys and identity. Traffic stays peer-to-peer and encrypted, and the service keeps working on `127.0.0.1` without it. This is the user's chosen access method.
- [Disk fills up] → The 30-day retention limits growth (each PDF is about 100 KB). A failed write returns 502 instead of crashing.
- [Leaking `LINK_SIGNING_SECRET` lets someone forge links] → Tailscale still limits reach to the tailnet. Changing the secret invalidates every outstanding link, which the README documents as the response to a leak.
- [macOS privacy protection (TCC) blocks a daemon from reading `~/Documents`, `~/Desktop` or `~/Downloads`] → The repo and the default paths (`~/dev-workspace`, `~/Library/Application Support`, `~/Library/Logs`, `~/Library/Caches`) are outside the protected folders. The README warns against pointing `OUTPUT_DIR` at a protected folder.
- [A crash loop fills `launchd.log`, which isn't rotated] → `ThrottleInterval` limits restarts to one every 10 seconds, `service_status.sh` shows the size of `launchd.log`, and the install script truncates it.

## Migration Plan

1. Prepare the Mac: install Homebrew `python@3.12`, `tectonic` and `tailscale`; apply the `pmset` settings; join the tailnet and set up `tailscale serve`.
2. Create `.env` from `.env.example`, using `openssl rand -hex 32` for `API_KEY` and `LINK_SIGNING_SECRET`, then `chmod 600 .env`.
3. Run `scripts/install_service.sh`, then from another tailnet device run `API_KEY=... scripts/smoke_test.sh https://<machine>.<tailnet>.ts.net`.
4. Reboot the Mac and confirm `/health` responds without logging in.
5. Once that's confirmed, the owner can delete the Cloud Run service, the R2 bucket and token, and the Secret Manager secrets.

Links issued by the cloud deployment keep working until that R2 bucket is deleted. There's no data to carry over.

**Rollback:** run `scripts/uninstall_service.sh`, then `git revert` this change. The cloud deployment can be redeployed from the reverted tree.

## Open Questions

- Port `8080` on loopback is assumed to be free. If it isn't, it's one value in the plist template and the serve command, and doesn't affect the specs.
