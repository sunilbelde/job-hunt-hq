import asyncio
import json
import logging
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from app.generation import generate_output
from app.models import JobRow
from app.rendering import RenderError
from app.settings import Settings, get_settings
from app.storage import LinkSigner, LocalStorage, Storage, StorageError, content_type_for, is_valid_key

logger = logging.getLogger("app.requests")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():  # without --log-config, uvicorn leaves app loggers without a handler
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)

CLEANUP_INTERVAL_SECONDS = 3600


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    """Build the app. Settings are validated here, so bad config fails at startup."""
    settings = settings or get_settings()
    storage = storage or LocalStorage(
        settings.output_dir,
        LinkSigner(settings.link_signing_secret.get_secret_value(), settings.public_base_url),
    )
    retention_seconds = settings.output_retention_days * 86400

    async def run_cleanup() -> None:
        try:
            deleted = await run_in_threadpool(storage.cleanup, retention_seconds)
        except Exception as exc:  # never let cleanup take the service down
            logger.error(json.dumps({"event": "cleanup_error", "error": str(exc)}))
            return
        if deleted:
            logger.info(json.dumps({"event": "cleanup", "deleted": deleted}))

    async def cleanup_loop() -> None:
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            await run_cleanup()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_cleanup()
        task = asyncio.create_task(cleanup_loop())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Job output service", lifespan=lifespan)
    expected_key = settings.api_key.get_secret_value().encode()

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    @app.middleware("http")
    async def log_jobs_request(request: Request, call_next):
        if request.url.path != "/jobs":
            return await call_next(request)
        request.state.job_id = str(uuid.uuid4())
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            fields: dict[str, Any] = {
                "event": "job_request",
                "job_id": request.state.job_id,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            key = getattr(request.state, "key", None)
            if key:
                fields["key"] = key
            logger.info(json.dumps(fields))

    @app.get("/healthz")
    @app.get("/health")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # No API key: the signature in the link is the credential.
    @app.get("/files/{key:path}")
    def download(key: str, expires: str | None = None, sig: str | None = None):
        if not is_valid_key(key) or not storage.verify_link(key, expires, sig):
            raise HTTPException(status_code=403, detail="Invalid or expired link")
        try:
            path = storage.path_for(key)
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid or expired link")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(
            path,
            media_type=content_type_for(key),
            filename=f"resume.{key.rsplit('.', 1)[-1]}",
            content_disposition_type="inline",
        )

    @app.post("/jobs", status_code=201, dependencies=[Depends(require_api_key)])
    async def create_job(request: Request):
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(status_code=422, detail="Request body must be valid JSON")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Request body must be a JSON object")

        try:
            job = JobRow.model_validate(payload)
        except ValidationError as exc:
            # Field names and messages only: never echo submitted values.
            detail = [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
            ]
            raise HTTPException(status_code=422, detail=detail)

        job_id = request.state.job_id
        try:
            # Rendering blocks for seconds; keep it off the event loop so /health stays responsive.
            generated = await run_in_threadpool(generate_output, job, job_id=job_id)
        except RenderError as exc:
            logger.error(json.dumps({"event": "render_error", "job_id": job_id, "error": str(exc)}))
            return JSONResponse(status_code=500, content={"detail": "Resume generation failed"})
        ttl = settings.signed_url_ttl_seconds
        try:
            key = storage.upload(generated.content, generated.content_type, generated.extension)
            request.state.key = key
            url = storage.presigned_url(key, ttl)
        except StorageError as exc:
            logger.error(json.dumps({"event": "storage_error", "job_id": job_id, "error": str(exc)}))
            return JSONResponse(status_code=502, content={"detail": "Storage service unavailable"})

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        return {
            "job_id": job_id,
            "url": url,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "key": key,
        }

    return app
