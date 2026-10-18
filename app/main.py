import json
import logging
import re
import secrets
import sys
import time
from typing import Any

from fastapi import FastAPI, Path, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ValidationError
from pydantic.json_schema import models_json_schema

from app.applications import ApplicationStore, ApplicationStoreError
from app.generation import generate_output
from app.models import (
    ApplicationRecorded,
    ApplicationRow,
    ApplicationUpdate,
    ApplicationUpdated,
    ErrorResponse,
    HealthStatus,
    ResumeCreated,
    ResumeRequest,
    StoredApplication,
)
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


# auto_error=False: a missing key comes through as None, so the handlers answer with their own
# {"ok": false} 401 rather than FastAPI's 403 {"detail"}. The scheme gives /docs its Authorize button.
api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKey",
    description="The service's API key. Entered once with Authorize; the page keeps it in memory only.",
    auto_error=False,
)

# Bodies are read by hand (see record_application), so FastAPI cannot document them itself.
BODY_MODELS = (ApplicationRow, ApplicationUpdate, ResumeRequest)

DESCRIPTION = """Records verified job applications and generates resume PDFs for them.

Every endpoint except the health checks needs the `X-API-Key` header. Every error is a JSON object
`{"ok": false, "message": "..."}`; the message names fields and rules but never echoes submitted values.

Requests sent from this page are real: they change the application store and write resume files."""

TAGS = [
    {"name": "health", "description": "Liveness checks. No API key needed."},
    {"name": "applications", "description": "Record, update and delete verified job applications."},
    {"name": "resumes", "description": "Generate a resume PDF for a recorded application."},
]

ERROR_DESCRIPTIONS = {
    401: "Missing or wrong `X-API-Key`. Checked before the body or ID is looked at.",
    404: "No application has this ID. An ID that is not a UUID gets this too.",
    422: "The body is not JSON, not a JSON object, or fails validation. `message` names the fields and rules.",
    500: "Resume generation failed.",
    502: "Storage service unavailable.",
    503: "Application store unavailable.",
}


# Exact versions with subresource integrity: the API key is typed into this page, so the code it
# runs must not change under it. To move versions, resolve the new one on jsDelivr and recompute each
# hash: curl -s <url> | openssl dgst -sha384 -binary | openssl base64 -A
CDN = "https://cdn.jsdelivr.net/npm"
SWAGGER_JS = (f"{CDN}/swagger-ui-dist@5.33.3/swagger-ui-bundle.js",
              "sha384-h00llMzD1afyNow1pDmnZKlHsUZgp9KE9HXLFXF2CvbwsBY0+WBO4f75SfGwvM4K")
SWAGGER_CSS = (f"{CDN}/swagger-ui-dist@5.33.3/swagger-ui.css",
               "sha384-Ov4/wv3j2bmct8cDc5X4ngJZohVPzEmc6uDPH8WeljUxO5vtoykvMEfbu9Vh6RaW")
REDOC_JS = (f"{CDN}/redoc@2.5.4/bundles/redoc.standalone.js",
            "sha384-w447zOpYfw/1Tv/5AK9NfHTlQIqE3RVR6KY62jCyy9zNDgO64cMwGGP1Fj0zJVf5")


def with_integrity(page: HTMLResponse, *assets: tuple[str, str]) -> HTMLResponse:
    """Add integrity and crossorigin to the tags loading each pinned asset."""
    html = page.body.decode()
    for url, digest in assets:
        attribute = "src" if url.endswith(".js") else "href"
        tag = f'{attribute}="{url}"'
        if html.count(tag) != 1:  # FastAPI's page template changed; this function needs updating
            raise RuntimeError(f"cannot find the tag loading {url}")
        html = html.replace(tag, f'{tag} integrity="{digest}" crossorigin="anonymous"')
    return HTMLResponse(html)


def errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorResponse, "description": ERROR_DESCRIPTIONS[status]} for status in statuses}


def json_body(model: type[BaseModel], description: str) -> dict[str, Any]:
    """openapi_extra documenting a JSON body, with the model's example to prefill Try it out."""
    return {
        "requestBody": {
            "required": True,
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{model.__name__}"},
                    "example": model.model_config["json_schema_extra"]["examples"][0],
                }
            },
        }
    }


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

    docs = settings.api_docs_enabled
    app = FastAPI(
        title="Job output service",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        # Off unless API_DOCS_ENABLED: the installed service's public listener never serves them.
        # The pages themselves are registered below, with pinned assets.
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    if docs:
        oauth2_redirect = "/docs/oauth2-redirect"

        @app.get("/docs", include_in_schema=False)
        def swagger_ui() -> HTMLResponse:
            page = get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{app.title} - Swagger UI",
                swagger_js_url=SWAGGER_JS[0],
                swagger_css_url=SWAGGER_CSS[0],
                oauth2_redirect_url=oauth2_redirect,
                # Pinned off so an entered API key never outlives the page.
                swagger_ui_parameters={"persistAuthorization": False},
            )
            return with_integrity(page, SWAGGER_JS, SWAGGER_CSS)

        @app.get(oauth2_redirect, include_in_schema=False)
        def swagger_ui_redirect() -> HTMLResponse:
            return get_swagger_ui_oauth2_redirect_html()

        @app.get("/redoc", include_in_schema=False)
        def redoc() -> HTMLResponse:
            page = get_redoc_html(openapi_url=app.openapi_url, title=f"{app.title} - ReDoc", redoc_js_url=REDOC_JS[0])
            return with_integrity(page, REDOC_JS)

    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = default_openapi()
            _, definitions = models_json_schema(
                [(model, "validation") for model in BODY_MODELS], ref_template="#/components/schemas/{model}"
            )
            schema["components"]["schemas"].update(definitions["$defs"])
            # FastAPI adds its {"detail"} 422 to every route with parameters; this service never sends it.
            for operations in schema["paths"].values():
                for operation in operations.values():
                    if "HTTPValidationError" in json.dumps(operation["responses"].get("422", {})):
                        del operation["responses"]["422"]
            for name in ("HTTPValidationError", "ValidationError"):
                schema["components"]["schemas"].pop(name, None)
        return app.openapi_schema

    app.openapi = openapi
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

    health = {"model": HealthStatus, "description": "The service is up."}

    # Decorators apply bottom-up: /healthz registers first, so the docs list it before its alias.
    @app.get(
        "/health",
        tags=["health"],
        summary="Health check (alias)",
        description='Returns `{"status": "ok"}` while the service is up. Same as `GET /healthz`.',
        responses={200: health},
    )
    @app.get(
        "/healthz",
        tags=["health"],
        summary="Health check",
        description='Returns `{"status": "ok"}` while the service is up. Same as `GET /health`.',
        responses={200: health},
    )
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def store_unavailable(exc: ApplicationStoreError) -> JSONResponse:
        logger.error(json.dumps({"event": "application_store_error", "error": str(exc)}))
        return application_error(503, "Application store unavailable")

    # Errors use {"ok": false, "message"}, so the key is checked inline rather than through a
    # FastAPI dependency, whose 401 would come back as {"detail"}.
    application_id_path = Path(description="The application's UUID, as returned when it was recorded.")

    @app.post(
        "/application",
        tags=["applications"],
        summary="Record a verified application",
        description=(
            "Records a verified job posting and returns its ID. New rows get status `verified`.\n\n"
            "Deduplicated on `job_link` (scheme and host case, default ports, fragments, trailing slashes "
            "and tracking parameters are ignored): sending a recorded posting again changes nothing and "
            "returns 200 with the existing ID.\n\n"
            "Rules beyond the schema:\n"
            "- `recruiting_platform` requires `verification_method` `official_apply_match` and "
            "`official_apply_url` equal to `job_link`.\n"
            "- `employer_site` requires `verification_method` `employer_site` and an empty `official_apply_url`.\n"
            "- Unknown fields are ignored."
        ),
        status_code=201,
        responses={
            201: {"model": ApplicationRecorded, "description": "Recorded as a new application."},
            200: {"model": ApplicationRecorded, "description": "Already recorded; the existing ID is returned."},
            **errors(401, 422, 503),
        },
        openapi_extra=json_body(ApplicationRow, "The verified posting."),
    )
    async def record_application(request: Request, x_api_key: str | None = Security(api_key_header)):
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
    @app.patch(
        "/application/{application_id}",
        tags=["applications"],
        summary="Update an application",
        description=(
            "Writes only the fields present in the body. `status`, `company` and `role` cannot be set to null.\n\n"
            "`job_link`, `posting_source_type`, `verification_method` and `official_apply_url` are fixed once "
            "recorded: including any of them gets 422.\n\n"
            "An unknown ID gets 404 even when the body is also invalid."
        ),
        responses={
            200: {"model": ApplicationUpdated, "description": "Updated; returns the application's current status."},
            **errors(401, 404, 422, 503),
        },
        openapi_extra=json_body(ApplicationUpdate, "The fields to change; at least one."),
    )
    async def update_application(
        request: Request,
        application_id: str = application_id_path,
        x_api_key: str | None = Security(api_key_header),
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

    @app.delete(
        "/application/{application_id}",
        tags=["applications"],
        summary="Delete an application",
        description=(
            "Permanently removes the application and all its fields; this cannot be undone. "
            "Resume files already generated for it are kept."
        ),
        responses={
            200: {"model": ApplicationRecorded, "description": "Deleted."},
            **errors(401, 404, 503),
        },
    )
    async def delete_application(
        request: Request,
        application_id: str = application_id_path,
        x_api_key: str | None = Security(api_key_header),
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


    @app.post(
        "/resume",
        tags=["resumes"],
        summary="Generate a resume PDF",
        description=(
            "Renders the resume for a recorded application and saves it on the service host at `saved_path`, "
            "replacing any earlier render. The application itself is not changed. Rendering takes a few seconds."
        ),
        status_code=201,
        responses={
            201: {"model": ResumeCreated, "description": "Generated and saved."},
            **errors(401, 404, 422, 500, 502, 503),
        },
        openapi_extra=json_body(ResumeRequest, "The application to generate a resume for."),
    )
    async def create_resume(request: Request, x_api_key: str | None = Security(api_key_header)):
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
