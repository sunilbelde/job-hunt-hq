# Design

## Context

Greenfield service in a repo that currently holds only `scripts/read_sheet.sh` and a README. Runs on Cloud Run (~20 req/day, scale to zero, max 3 instances) with Cloudflare R2 as storage. The later change will replace the generation stub with a Claude Agent SDK run that can take minutes, which is why the deploy uses a 900s request timeout even though the stub is instant. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Three separate seams: HTTP layer, `generate_output`, storage module.
- Storage swappable/mockable in tests with no network.
- Fail-fast configuration; no secrets in logs or responses.

**Non-Goals:**
- Async/queue processing, retries, idempotency keys.
- Per-client keys, key rotation, rate limiting.
- Public custom-domain links.

## Decisions

**Layout** (new `app/` package at repo root):
- `app/main.py` — FastAPI app factory, routes, auth dependency, exception mapping, request logging.
- `app/settings.py` — pydantic-settings `Settings`; `get_settings()` cached.
- `app/generation.py` — `GeneratedFile` dataclass (`content`, `content_type`, `extension`) and `generate_output(payload, *, job_id=None) -> GeneratedFile`. The route generates `job_id` and passes it as an optional keyword so one id appears in the response, stub file and log line; the real implementation may ignore it. Call shape `generate_output(payload)` still works.
- `app/storage.py` — `Storage` protocol (`put(key, content, content_type)`, `presigned_url(key, ttl) -> url`) and `R2Storage` implementation (boto3 S3 client, `endpoint_url=https://{account}.r2.cloudflarestorage.com`, region `auto`, SigV4). Injected into routes via a FastAPI dependency so tests use `app.dependency_overrides`.
- Key building (`outputs/{date}/{uuid4}.{ext}`) lives in the storage module so callers cannot bypass the scheme; it returns the key from an `upload` operation. Storage failures are wrapped in a `StorageError`, which the HTTP layer maps to 502.

**Auth**: FastAPI dependency comparing `X-API-Key` with `secrets.compare_digest`. Auth is evaluated before the body is parsed, so unauthenticated requests get 401 regardless of body. Alternative (middleware) rejected: dependency is simpler and keeps `/healthz` open.

**Body validation**: the route reads the raw request and parses JSON itself, returning 422 for malformed JSON or a non-object (within the spec's 400/422). Declaring a typed body would let FastAPI reject bad JSON *before* the auth dependency runs, so a wrong-key request with a bad body would get 422 instead of 401; parsing inside the route keeps auth first. Tests assert this ordering.

**Signed URL**: `generate_presigned_url("get_object", ExpiresIn=ttl)`. `expires_at = now_utc + ttl`, ISO 8601. R2 supports SigV4 presigned GETs up to 7 days, matching the 604800 max. Signing is local (no network), so only the upload can fail on connectivity.

**Logging**: stdlib `logging` (the `app.requests` logger gets its own stdout handler, since uvicorn configures only its own loggers) with a single JSON line per `/jobs` request emitted from the route/middleware: `job_id`, `status`, `duration_ms`, plus `key` on success. The payload, headers and settings are never logged. boto3/botocore loggers stay at WARNING to avoid leaking request details. Exception details for 502s are logged with the job id via `logger.exception`-style output that excludes credentials. For 401/422 requests with no job id yet, `job_id` is generated at request start so every line has one.

**Config**: `Settings` fields `API_KEY`, `R2_*` required with `min_length=1`; `ANTHROPIC_API_KEY` optional; `SIGNED_URL_TTL_SECONDS: int = Field(604800, gt=0, le=604800)`. Settings are instantiated at app startup (lifespan), so bad config crashes the container and Cloud Run reports a failed revision. Validation errors list field names; pydantic does not echo secret values when `SecretStr` is used.

**Container**: `python:3.12-slim`, install requirements, create non-root user, `CMD exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT}"` with `PORT` defaulting to 8080. The `--factory` form builds the app (and validates settings) at startup rather than at import, so tests can import the module without env vars. Single worker; concurrency is handled by Cloud Run instances.

**Deployment doc**: README gets a "Deploying" section: R2 bucket and token scoped to that bucket (Object Read & Write), secrets via `gcloud secrets create`, `gcloud run deploy --source/--image --timeout=900 --memory=1Gi --min-instances=0 --max-instances=3 --allow-unauthenticated --set-secrets=...`, and a 30-day R2 lifecycle rule on prefix `outputs/`. The Cloud Run service account needs `secretmanager.secretAccessor`.

**Tests**: pytest + FastAPI `TestClient` with storage overridden by a fake; cases for 401 (missing/wrong), invalid JSON, non-object body, success shape and key pattern, `StorageError` → 502 with generic body. Fakes record calls so "no file written" is asserted. Settings tests cover TTL bounds and missing vars. `scripts/smoke_test.sh <base_url>` uses curl: needs `API_KEY`, POSTs sample JSON, extracts `url` with `python3`/`sed` (no jq dependency), fetches it, and exits non-zero unless 200.

Alternatives considered: `s3fs`/`aioboto3` (extra deps, no benefit at this volume); making `generate_output` async now (premature; the later change can wrap it in a threadpool or make it async behind the same seam).

## Risks / Trade-offs

- [Single shared API key; anyone holding it can create jobs] → acceptable for first pass; store in Secret Manager, rotate by redeploy.
- [Unauthenticated Cloud Run endpoint is internet-exposed; cost abuse] → API key check before any work; max 3 instances caps spend.
- [Signed URLs are bearer links valid up to 7 days] → TTL is configurable; lifecycle rule bounds object retention to 30 days.
- [Synchronous request may be long once real generation lands] → 900s timeout set now; async is a later change.
- [Stub echoes the payload into a downloadable file, which may contain sensitive data] → file only reachable via unguessable key + signature.
- [No real-R2 test in CI] → covered by the manual smoke test and acceptance check.
