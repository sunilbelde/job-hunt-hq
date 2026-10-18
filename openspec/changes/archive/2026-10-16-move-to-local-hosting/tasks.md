# Tasks

## 1. Host prerequisites and dev environment

- [x] 1.1 Install Homebrew `python@3.12` and `tectonic` on the Mac mini. Verify that `python3.12 --version` reports 3.12.x and `tectonic --version` runs.
- [x] 1.2 Recreate `.venv` with `python3.12 -m venv .venv` and run `.venv/bin/pip install -r requirements-dev.txt`. Verify that the existing suite, `.venv/bin/python -m pytest`, passes before any code changes. This is the baseline, including the tectonic-backed rendering tests.

## 2. Configuration

- [x] 2.1 In `app/settings.py`:
  - Remove the `r2_*` fields.
  - Add `link_signing_secret` (`SecretStr`, at least 32 characters).
  - Add `public_base_url` (absolute http/https URL, no query or fragment, trailing slash stripped).
  - Add `output_dir` (`Path`, default `~/Library/Application Support/job-hunt-hq`).
  - Add `output_retention_days` (int greater than 0, default 30).
  - Add a model validator enforcing `retention_days * 86400 >= signed_url_ttl_seconds`.

  Verify that the rewritten `tests/test_settings.py` covers the defaults, a missing `LINK_SIGNING_SECRET` being named, a short secret, a relative base URL, trailing-slash stripping, retention shorter than the TTL naming both variables, `R2_*` not being required, and secrets never appearing in errors.
- [x] 2.2 Rewrite `.env.example`:
  - Remove the `R2_*` lines.
  - Add the new variables with placeholders and comments: `openssl rand -hex 32` for both secrets, and a `PUBLIC_BASE_URL` example using a `ts.net` hostname.
  - Keep `ANTHROPIC_API_KEY` as optional.

  Verify that every `Settings` field appears in it and it contains no real values.

## 3. Local storage and link signing

- [x] 3.1 In `app/storage.py`:
  - Remove `R2Storage` and the boto3 and botocore imports.
  - Add `LocalStorage(root)`: create the root with mode `0700` and check it is writable (raising `StorageError` naming `OUTPUT_DIR`), and keep `build_key()`.
  - Make `upload()` write to a `.tmp-<uuid>` file, fsync it, then `os.replace` it into place. Wrap `OSError` in `StorageError`.

  Verify that the rewritten `tests/test_storage.py`, using `tmp_path`, covers the key format and the file at `<root>/<key>`, unique keys, the absence of `.tmp-*` files after upload, a `StorageError` when the root is read-only, and directory mode `0700`.
- [x] 3.2 Add `LinkSigner(secret, base_url)` that signs `"{key}\n{expires}"` with HMAC-SHA256. It builds `{base}/files/{key}?expires=…&sig=…` and verifies with `hmac.compare_digest`. Make `LocalStorage.presigned_url(key, ttl)` delegate to it. Verify with unit tests: a link round-trips, an expired link fails, and a tampered key, expiry or signature fails. A link signed by one instance must verify on a new instance with the same secret, which simulates a restart.
- [x] 3.3 Add `LocalStorage.resolve(key)`, which checks the key against the regex `^outputs/\d{4}-\d{2}-\d{2}/[0-9a-f-]{36}\.[a-z0-9]{1,8}$` and confirms the resolved path stays under the root. Add `cleanup(max_age)`, which deletes old files by mtime, removes `.tmp-*` files older than one hour and empty date directories, and logs and skips per-file errors. Verify with tests:
  - keys containing `..`, absolute paths and keys in the wrong format are rejected
  - a file 31 days old is deleted and one 29 days old is kept, using `os.utime`
  - a stale `.tmp` file is removed
  - an empty date directory is removed
  - a file that can't be deleted doesn't make the cleanup raise
- [x] 3.4 Remove `boto3` from `requirements.txt` and reinstall into a fresh venv. Verify that `.venv/bin/pip show boto3` reports it's not installed and `grep -rn "boto\|R2" app tests` finds nothing.

## 4. HTTP layer

- [x] 4.1 Update `create_app()`:
  - Build `LocalStorage(settings.output_dir)` with a `LinkSigner`.
  - Drop the botocore and boto3 logger settings.
  - Leave the `POST /jobs` flow and response shape unchanged.

  Update `tests/conftest.py` so `FakeStorage` and the `settings` fixture use the new fields. Verify that every existing test in `tests/test_api.py` passes. The 502 test now simulates a disk error, and the success test checks that `url` starts with `PUBLIC_BASE_URL`.
- [x] 4.2 Add `GET /files/{key:path}`. It is not protected by the API key. Check in this order: key format (403), then signature and expiry (403), then a missing file (404). Return a `FileResponse` with the Content-Type mapped from the extension (`pdf` → `application/pdf`). Verify with `TestClient` tests using a real `LocalStorage` on `tmp_path`:
  - POST then GET of the returned URL gives 200, the same bytes, and `application/pdf`
  - no signature gives 403
  - an expired link gives 403 (tested by freezing the time used for expiry)
  - a tampered signature gives 403
  - a `..` key gives 403 without touching the filesystem
  - a deleted file gives 404
  - a download emits no `job_request` log line and no signature in the logs
- [x] 4.3 Add a lifespan task that runs `storage.cleanup()` in the threadpool at startup and then every hour, and cancels cleanly on shutdown. Update the health route comment that mentions Cloud Run. Verify with a test that a file aged past retention is gone after `TestClient` starts the app, and that `/health` and `/healthz` still return 200 with no storage call.

## 5. Running as a launchd service

- [x] 5.1 Add `deploy/local.job-hunt-hq.plist.template`, a LaunchDaemon with `UserName`, `WorkingDirectory`, uvicorn bound to `127.0.0.1:8080` with `--log-config`, `RunAtLoad`, `KeepAlive`, `ThrottleInterval` 10, the `HOME`, `PATH` and `TECTONIC_CACHE_DIR` environment variables, and stdout and stderr going to `launchd.log`. Also add `deploy/logging.json.template` with a `RotatingFileHandler` (10 MB × 5) for the `uvicorn*` and `app.requests` loggers. Verify that `plutil -lint` passes on a template filled with the real repo path (which contains a space), and that `python -c "import json; json.load(open(...))"` passes on the filled logging config.
- [x] 5.2 Write `scripts/install_service.sh` as described in design decision 7. It:
  - checks for `python3.12`, `tectonic` and `.env`, and that `.env` has mode 600 or stricter, giving the fix on failure
  - creates or refreshes the venv
  - validates the config by running `create_app()` and prints the error only
  - warms the tectonic cache with one render
  - fills in the templates with XML-escaped paths
  - installs the plist with `sudo` as `root:wheel 644`, then runs `launchctl bootout` (ignoring errors) and `launchctl bootstrap system`
  - truncates `launchd.log`
  - polls `/health` for up to 30 seconds
  - warns if `tailscale serve status` shows no proxy to port 8080

  Add `scripts/test_install_service.sh` (stubbed `sudo`, `launchctl`, `curl`, `tectonic`, `tailscale`, following `scripts/test_smoke_test.sh`). Verify it shows that a world-readable `.env` exits non-zero with nothing installed, that a missing `tectonic` exits non-zero, and that a happy path calls bootout and then bootstrap with the filled plist.
- [x] 5.3 Write `scripts/uninstall_service.sh` (bootout, remove the plist, keep the data and logs) and `scripts/service_status.sh` (`launchctl print` state and pid, a health check, the size of `launchd.log`, and the `pmset` sleep value). Extend the stubbed test script. Verify that uninstall calls bootout and removes the plist without touching `OUTPUT_DIR`, and that status reports "not loaded" when `launchctl print` fails.
- [x] 5.4 Run `scripts/install_service.sh` on the Mac mini. Verify all of the following:
  - `curl -s 127.0.0.1:8080/health` returns `{"status":"ok"}`
  - `ps -o user= -p <pid>` shows the owner's account, not root
  - `lsof -iTCP:8080 -sTCP:LISTEN` shows only `127.0.0.1`
  - running `sudo kill <pid>` brings back a new pid serving `/health` within 30 seconds
  - `service.log` contains a `job_request` line after running `scripts/smoke_test.sh http://127.0.0.1:8080`
  - running the install script a second time succeeds

## 6. Remove cloud deployment and update docs

- [x] 6.1 Delete `Dockerfile` and `.dockerignore`. Verify that `git ls-files | grep -i docker` is empty.
- [x] 6.2 Rewrite `README.md`:
  - Retitle it for this service.
  - Remove the missing `read_sheet.sh` and Google Sheets section, and the Cloud Run, R2 and Secret Manager deployment sections.
  - Update the endpoint table (add `/files/{key}`) and the configuration list.
  - Add a "Running on the Mac mini" section covering the Homebrew prerequisites, the `pmset` sleep and autorestart settings, the FileVault trade-off with `fdesetup authrestart`, Tailscale (the formula, `brew services`, MagicDNS and HTTPS, `tailscale serve --bg --https=443 http://127.0.0.1:8080`), creating `.env` with `chmod 600`, install, status and uninstall, where the logs are, re-running install after `git pull`, changing `LINK_SIGNING_SECRET` after a leak, and not pointing `OUTPUT_DIR` at a folder macOS protects (`~/Documents`, `~/Desktop`, `~/Downloads`).
  - Add a note that the old cloud resources can be deleted by hand.

  Verify that `grep -niE "cloud run|gcloud|r2|secret manager|docker|read_sheet" README.md` finds nothing, and that every command in the new section matches a script or flag that exists.

## 7. End-to-end checks on the Mac mini

- [ ] 7.1 Set up Tailscale as the README describes and set `PUBLIC_BASE_URL` to the `ts.net` HTTPS URL. Re-run the install script. From another tailnet device, verify that `API_KEY=... scripts/smoke_test.sh https://<machine>.<tailnet>.ts.net` prints OK, and that the same URL can't be reached from a device off the tailnet or from the LAN IP on port 8080.
- [ ] 7.2 Reboot the Mac mini without logging in. Verify from a tailnet device that `/health` returns 200 within two minutes, and that a link issued before the reboot still downloads the PDF.
- [ ] 7.3 Turn off networking on the Mac (other than loopback) and `POST /jobs` to `127.0.0.1:8080`. Verify that it returns 201 and the link downloads a PDF, which confirms offline rendering and that no cloud dependency is needed. Run the full `.venv/bin/python -m pytest` suite and `sh scripts/test_*.sh` once more, and check that they all pass.

## Workflow follow-up

- Once the Mac mini has been verified, the owner deletes the Cloud Run service, the R2 bucket and token, and the Secret Manager secrets. This is manual and outside the repo.
- Archive the change with `/opsx:archive` after review.
