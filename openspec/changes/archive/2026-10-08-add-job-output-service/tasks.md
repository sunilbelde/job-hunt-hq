# Tasks

## 1. Project scaffolding

- [x] 1.1 Create `app/` package, `tests/`, `requirements.txt` (fastapi, uvicorn, boto3, pydantic-settings) and `requirements-dev.txt` (pytest, httpx); verify `pip install -r requirements-dev.txt` succeeds on Python 3.12
- [x] 1.2 Add `.env.example` with placeholder values for every variable and a `.gitignore` excluding `.env`; verify no real secrets appear and `.env` is ignored by git check-ignore

## 2. Configuration

- [x] 2.1 Implement `app/settings.py` (required fields, optional `ANTHROPIC_API_KEY`, TTL default 604800 with `0 < ttl <= 604800`, `SecretStr` for secrets) with unit tests for missing variable, default TTL and TTL 604801 rejected; verify `pytest tests/test_settings.py` passes

## 3. Storage module

- [x] 3.1 Implement `app/storage.py`: `Storage` protocol, `R2Storage` (boto3 client with R2 endpoint, region `auto`), dated UUID key builder, upload with Content-Type, presigned GET URL, and `StorageError` wrapping; verify unit tests using botocore Stubber / a fake client cover key format `outputs/YYYY-MM-DD/<uuid4>.<ext>`, Content-Type passthrough, TTL passed to signing, and error wrapping (no network)

## 4. Generation seam

- [x] 4.1 Implement `app/generation.py` with `GeneratedFile` and the stub `generate_output` (payload + UTC timestamp + job id as JSON); verify a unit test checks bytes parse to JSON with those fields and content type `application/json`, extension `json`

## 5. HTTP layer

- [x] 5.1 Implement `app/main.py`: app factory with settings loaded at startup, storage dependency, `GET /healthz`, `POST /jobs` with constant-time API-key check before body handling, object-body validation, 201 response `{job_id, url, expires_at, key}`, `StorageError` → 502 generic message; verify with `TestClient` tests (storage overridden by a fake) for: missing key 401, wrong key 401, invalid JSON 4xx, array/string body 4xx, success shape, 502 on R2 failure with no internals in the body, and that the fake recorded zero uploads in all rejection cases
- [x] 5.2 Add structured per-request logging (one JSON line with job_id, status, duration_ms; never payload or keys; botocore loggers at WARNING) and log storage-failure details server-side; verify with `caplog` tests that exactly one line is emitted per request and that the API key and payload values do not appear in logs
- [x] 5.3 Verify `/healthz` returns 200 `{"status":"ok"}` without a key and makes no storage call (test asserts fake storage untouched)

## 6. Packaging and deployment

- [x] 6.1 Write `Dockerfile` (python:3.12-slim, non-root user, `uvicorn` bound to `0.0.0.0:$PORT` defaulting to 8080); verify `docker build` succeeds and `docker run -e PORT=9000 ...` serves `/healthz` on port 9000 as non-root (`id -u` != 0)
- [x] 6.2 Add `.dockerignore` excluding `.env`, `tests/`, `openspec/`, `.git`; verify the built image contains no `.env`
- [x] 6.3 Add README "Deploying" section covering R2 bucket and bucket-scoped API token creation, Secret Manager secrets mounted as env vars, the `gcloud run deploy` command (timeout 900s, 1Gi, min 0, max 3, allow-unauthenticated), granting the service account Secret Accessor, and the 30-day `outputs/` lifecycle rule; verify each command/flag is syntactically checked against `gcloud run deploy --help` and the doc has local-run instructions

## 7. Smoke test and end-to-end checks

- [x] 7.1 Write `scripts/smoke_test.sh <base_url>` (reads `API_KEY` from env, POSTs sample JSON, extracts `url`, fetches it, exits non-zero unless HTTP 200, prints the downloaded content); verify `sh -n` passes and a stubbed-curl test (matching the existing `scripts/test_read_sheet.sh` style) covers success and failure paths
- [x] 7.2 Integration check locally against a real R2 bucket: run uvicorn with a real `.env`, run `scripts/smoke_test.sh http://localhost:8080`, and open the returned URL in a browser to confirm the stub file downloads; also confirm a wrong key returns 401 and leaves no new object in the bucket
- [x] 7.3 Deploy to Cloud Run per the README and rerun `scripts/smoke_test.sh <service-url>`; verify 201 then 200 on the signed link
- [x] 7.4 Run the full unit suite with networking disabled (e.g., `pytest` with sockets blocked or offline) and verify all tests pass

## Workflow follow-up

- Archive the change after review and after the Cloud Run acceptance check passes.
