# Proposal

## Why

The resume-generation workflow needs a network-reachable service that turns a JSON request into a file and hands back a shareable link. Real generation (Claude Agent SDK, skills, scripts) is a later change; before building it we need the surrounding plumbing — auth, storage on Cloudflare R2, signed links, container deployment on Cloud Run — proven end to end so the later change only has to replace one function.

## What Changes

- New HTTP service (Python 3.12, FastAPI, uvicorn) with `POST /jobs` and `GET /healthz`.
- `POST /jobs`: API-key auth, JSON-object body validation, calls a stubbed `generate_output(payload) -> GeneratedFile`, uploads the result to R2 at `outputs/{YYYY-MM-DD}/{uuid4}.{ext}`, returns 201 with a pre-signed GET URL, expiry and key.
- Storage module (boto3 against R2's S3-compatible endpoint) providing upload and signed-URL generation behind a swappable/mockable seam.
- Startup-validated configuration from env vars via pydantic-settings, plus `.env.example`.
- Error handling: R2 failures → 502 with a generic message; one structured log line per request; no secrets or full payloads in logs.
- Dockerfile (slim base, non-root, honors `$PORT`).
- README deployment section (R2 bucket + scoped token, Secret Manager, `gcloud run deploy`, 30-day lifecycle rule).
- Unit tests (storage mocked, no network) and a manual `scripts/smoke_test.sh`.

Out of scope: Claude Agent SDK/skills/real output format, async/queue processing, custom-domain public links, rate limiting beyond max instances.

## Capabilities

### New Capabilities
- `job-api`: HTTP surface — `POST /jobs` (auth, body validation, response contract, error mapping, per-request logging) and unauthenticated `GET /healthz`.
- `output-storage`: Persisting generated files to R2 under a dated key with correct Content-Type and issuing time-limited pre-signed download URLs.
- `service-config`: Environment-based configuration, validated at startup, including signed-URL TTL bounds and secret-handling rules.

### Modified Capabilities
<!-- None: no specs exist yet. -->

## Impact

- New code: an `app/` Python package (HTTP layer, `generate_output` stub, storage module, settings), `tests/`, `scripts/smoke_test.sh`, `Dockerfile`, `.env.example`, `requirements` file.
- Existing repo content (`scripts/read_sheet.sh` and its tests, README) is untouched except for a new deployment section in `README.md`.
- External systems: Cloudflare R2 (bucket, scoped API token, lifecycle rule), Google Cloud Run, Google Secret Manager.
- New dependencies: fastapi, uvicorn, boto3, pydantic-settings (+ pytest, httpx for tests).
