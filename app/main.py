import json
import logging
import re
import secrets
import sys
import time
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.applications import ApplicationStore, ApplicationStoreError
from app.generation import generate_output
from app.models import ApplicationRow, ApplicationUpdate, ResumeRequest, StoredApplication
from app.rendering import RenderError
from app.settings import Settings, get_settings
from app.storage import LocalStorage, Storage, StorageError, rename_legacy_folders

logger = logging.getLogger("app.requests")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():  # without --log-config, uvicorn leaves app loggers without a handler
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)

# Hyphenated UUIDs only: uuid.UUID() would also take braces, "urn:uuid:" and bare hex,
# giving one ID several spellings in logs and folder names.
APPLICATION_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def request_event(path: str) -> str | None:
    if path == "/resume":
        return "resume_request"
    if path == "/application" or path.startswith("/application/"):
        return "application_request"
    return None


def application_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "message": message})


def application_not_found() -> JSONResponse:
    return application_error(404, "Application not found")


def parse_application_id(raw: str) -> str | None:
    """A stored ID is a UUID, kept in lower case; anything else cannot name a row."""
    return raw.lower() if APPLICATION_ID.fullmatch(raw) else None


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
    storage = storage or LocalStorage(settings.output_dir)
    applications = applications or ApplicationStore(settings.output_dir / "applications.sqlite3")
    try:
        # Resume folders made before IDs were UUIDs follow their application to its new ID.
        rename_legacy_folders(settings.output_dir, applications.legacy_ids())
    except ApplicationStoreError as exc:
        logger.error(json.dumps({"event": "application_store_error", "error": str(exc)}))

    app = FastAPI(title="Job output service")
    expected_key = settings.api_key.get_secret_value().encode()

    def api_key_valid(x_api_key: str | None) -> bool:
        return x_api_key is not None and secrets.compare_digest(x_api_key.encode(), expected_key)

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        event = request_event(request.url.path)
        if event is None:
            return await call_next(request)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            fields: dict[str, Any] = {"event": event}
            if event == "application_request":
                fields["method"] = request.method
            fields["status"] = status
            fields["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            for name in ("application_id", "duplicate"):
                value = getattr(request.state, name, None)
                if value is not None:
                    fields[name] = value
            logger.info(json.dumps(fields))

    @app.get("/healthz")
    @app.get("/health")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def store_unavailable(exc: ApplicationStoreError) -> JSONResponse:
        logger.error(json.dumps({"event": "application_store_error", "error": str(exc)}))
        return application_error(503, "Application store unavailable")

    # Errors use {"ok": false, "message"}, so the key is checked inline rather than through a
    # FastAPI dependency, whose 401 would come back as {"detail"}.
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

    # The path ID is taken as a string: a typed UUID would let FastAPI answer with its own 422 shape.
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


    @app.post("/resume")
    async def create_resume(request: Request, x_api_key: str | None = Header(default=None)):
        if not api_key_valid(x_api_key):
            return application_error(401, "Invalid or missing API key")
        try:
            payload = await request.json()
        except ValueError:
            return application_error(422, "Request body must be valid JSON")
        if not isinstance(payload, dict):
            return application_error(422, "Request body must be a JSON object")
        try:
            requested = ResumeRequest.model_validate(payload).application_id
        except ValidationError as exc:
            return application_error(422, validation_message(exc))
        target = parse_application_id(requested)
        if target is None:  # cannot name a row; the raw string stays out of the log line
            return application_not_found()
        request.state.application_id = target

        try:
            row = await run_in_threadpool(applications.get, target)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if row is None:
            return application_not_found()
        application = StoredApplication.model_validate(row)

        try:
            # Rendering blocks for seconds; keep it off the event loop so /health stays responsive.
            generated = await run_in_threadpool(generate_output, application)
        except RenderError as exc:
            logger.error(json.dumps({"event": "render_error", "application_id": target, "error": str(exc)}))
            return application_error(500, "Resume generation failed")
        try:
            path = await run_in_threadpool(storage.save_resume, application.company, target, generated.content)
        except StorageError as exc:
            logger.error(json.dumps({"event": "storage_error", "application_id": target, "error": str(exc)}))
            return application_error(502, "Storage service unavailable")
        return JSONResponse(
            status_code=201,
            content={"ok": True, "application_id": target, "saved_path": str(path)},
        )

    return app
