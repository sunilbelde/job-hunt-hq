import asyncio
import json
import logging
import re
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

from app.applications import ApplicationStore, ApplicationStoreError
from app.generation import generate_output
from app.models import ApplicationRow, ApplicationUpdate, JobRow
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
APPLICATION_ID = re.compile(r"[1-9][0-9]{0,18}")
MAX_APPLICATION_ID = 2**63 - 1  # SQLite's integer range


def request_event(path: str) -> str | None:
    if path == "/jobs":
        return "job_request"
    if path == "/application" or path.startswith("/application/"):
        return "application_request"
    return None


def application_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "message": message})


def application_not_found() -> JSONResponse:
    return application_error(404, "Application not found")


def parse_application_id(raw: str) -> int | None:
    """A stored ID is a positive base-10 integer; anything else cannot name a row."""
    if not APPLICATION_ID.fullmatch(raw):
        return None
    value = int(raw)
    return value if value <= MAX_APPLICATION_ID else None


def validation_message(exc: ValidationError) -> str:
    """Field names and messages only: never echo submitted values."""
    parts = []
    for error in exc.errors(include_input=False):
        msg = error["msg"].removeprefix("Value error, ")
        field = ".".join(str(part) for part in error["loc"])
        parts.append(f"{field}: {msg}" if field else msg)
    return "Invalid request: " + "; ".join(parts)


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
    applications: ApplicationStore | None = None,
) -> FastAPI:
    """Build the app. Settings are validated here, so bad config fails at startup."""
    settings = settings or get_settings()
    storage = storage or LocalStorage(
        settings.output_dir,
        LinkSigner(settings.link_signing_secret.get_secret_value(), settings.public_base_url),
    )
    applications = applications or ApplicationStore(settings.output_dir / "applications.sqlite3")
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

    def api_key_valid(x_api_key: str | None) -> bool:
        return x_api_key is not None and secrets.compare_digest(x_api_key.encode(), expected_key)

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if not api_key_valid(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        event = request_event(request.url.path)
        if event is None:
            return await call_next(request)
        if event == "job_request":
            request.state.job_id = str(uuid.uuid4())
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            fields: dict[str, Any] = {"event": event}
            if event == "job_request":
                fields["job_id"] = request.state.job_id
            else:
                fields["method"] = request.method
            fields["status"] = status
            fields["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            for name in ("key", "application_id", "duplicate"):
                value = getattr(request.state, name, None)
                if value is not None:
                    fields[name] = value
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

    def store_unavailable(exc: ApplicationStoreError) -> JSONResponse:
        logger.error(json.dumps({"event": "application_store_error", "error": str(exc)}))
        return application_error(503, "Application store unavailable")

    # Errors here use {"ok": false, "message"} instead of /jobs' {"detail"}, so the key is
    # checked inline rather than through require_api_key.
    @app.post("/application")
    async def record_application(request: Request, x_api_key: str | None = Header(default=None)):
        if not api_key_valid(x_api_key):
            return application_error(401, "Invalid or missing API key")
        try:
            payload = await request.json()
        except ValueError:
            return application_error(422, "Request body must be valid JSON")
        if not isinstance(payload, dict):
            return application_error(422, "Request body must be a JSON object")

        try:
            application = ApplicationRow.model_validate(payload)
        except ValidationError as exc:
            return application_error(422, validation_message(exc))

        try:
            application_id, created = await run_in_threadpool(applications.record, application.model_dump())
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        request.state.application_id = application_id
        request.state.duplicate = not created
        return JSONResponse(
            status_code=201 if created else 200,
            content={"ok": True, "application_id": application_id},
        )

    async def read_update(request: Request) -> tuple[dict | None, str | None]:
        """The fields to write, or a 422 message naming what is wrong with the body."""
        try:
            payload = await request.json()
        except ValueError:
            return None, "Request body must be valid JSON"
        if not isinstance(payload, dict):
            return None, "Request body must be a JSON object"
        try:
            return ApplicationUpdate.model_validate(payload).model_dump(exclude_unset=True), None
        except ValidationError as exc:
            return None, validation_message(exc)

    # The path ID is taken as a string: a typed int would let FastAPI answer with its own 422 shape.
    @app.patch("/application/{application_id}")
    async def update_application(
        application_id: str, request: Request, x_api_key: str | None = Header(default=None)
    ):
        if not api_key_valid(x_api_key):
            return application_error(401, "Invalid or missing API key")
        target = parse_application_id(application_id)
        if target is None:
            return application_not_found()
        request.state.application_id = target

        changes, message = await read_update(request)
        try:
            # An unknown ID is reported as such even when the body is also wrong.
            if message is not None:
                if not await run_in_threadpool(applications.exists, target):
                    return application_not_found()
                return application_error(422, message)
            status = await run_in_threadpool(applications.update, target, changes)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if status is None:
            return application_not_found()
        return {"ok": True, "application_id": target, "status": status}

    @app.delete("/application/{application_id}")
    async def delete_application(
        application_id: str, request: Request, x_api_key: str | None = Header(default=None)
    ):
        if not api_key_valid(x_api_key):
            return application_error(401, "Invalid or missing API key")
        target = parse_application_id(application_id)
        if target is None:
            return application_not_found()
        request.state.application_id = target
        try:
            deleted = await run_in_threadpool(applications.delete, target)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if not deleted:
            return application_not_found()
        return {"ok": True, "application_id": target}

    return app
