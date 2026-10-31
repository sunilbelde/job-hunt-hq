import json
import logging
import pathlib
import re
import secrets
import sys
import threading
import time
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Path, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ValidationError
from pydantic.json_schema import models_json_schema

from app.applications import NO_JOB, ApplicationStore, ApplicationStoreError, utc_now
from app.cover_letter import posting_usable as letter_posting_usable
from app.cover_letter import run as write_cover_letter
from app.generation import generate_output
from app.models import (
    ApplicationDetail,
    ApplicationList,
    ApplicationRecorded,
    ApplicationRow,
    ApplicationUpdate,
    ApplicationUpdated,
    CoverLetterJobStatus,
    CoverLetterRequest,
    ErrorResponse,
    GenerationAccepted,
    HealthStatus,
    ResumeJobStatus,
    ResumeRequest,
    StoredApplication,
)
from app.rendering import RenderError
from app.settings import Settings, get_settings
from app.storage import (
    COVER_LETTER_FILE_NAME,
    LocalStorage,
    Storage,
    StorageError,
    cover_letter_path,
    rename_legacy_folders,
    resume_path,
)
from app.tailoring import TailoringError
from app.viewer import BaseResumeCache, content_security_policy, page, read_base_cover_letter

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
BODY_MODELS = (ApplicationRow, ApplicationUpdate, ResumeRequest, CoverLetterRequest)

DESCRIPTION = """Records verified job applications and generates resume and cover letter PDFs for them.

Every endpoint except the health checks and the viewer reads needs the `X-API-Key` header. Every error is a JSON object
`{"ok": false, "message": "..."}`; the message names fields and rules but never echoes submitted values.

Requests sent from this page are real: they change the application store and write resume and cover letter files."""

TAGS = [
    {"name": "health", "description": "Liveness checks. No API key needed."},
    {"name": "applications", "description": "Record, update and delete verified job applications."},
    {"name": "resumes", "description": "Generate a resume PDF for a recorded application in the background, and "
                                       "poll the job's status."},
    {"name": "cover letters", "description": "Write a cover letter for a recorded application, only when it asks "
                                             "for one, in the background, and poll the job's status."},
    {"name": "viewer", "description": "Read applications, their generation reports, resume and cover letter PDFs, "
                                      "for the resume viewer at `/viewer`. Served only where these docs are."},
]

ERROR_DESCRIPTIONS = {
    401: "Missing or wrong `X-API-Key`. Checked before the body or ID is looked at.",
    404: "No application has this ID. An ID that is not a UUID gets this too.",
    "404_resume": "No application has this ID (`Application not found`), or it has no saved resume (`Resume not found`).",
    "404_letter": "No application has this ID (`Application not found`), or it has no saved cover letter "
                  "(`Cover letter not found`).",
    "404_base_letter": "`data/COVER_LETTER.pdf` is missing or unreadable (`Base cover letter not found`).",
    "500_base": "The base resume could not be rendered.",
    422: "The body is not JSON, not a JSON object, or fails validation. `message` names the fields and rules.",
    "404_job": "No application has this ID (`Application not found`), or it never had a job of this kind "
               "(`No job for this application`).",
    "422_letter": "The body is not JSON, not a JSON object, or fails validation, or the application has no usable "
                  "posting text (missing, under 50 words, or over 60,000 characters). `message` says which.",
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


def errors(*statuses: int | str) -> dict[int | str, dict[str, Any]]:
    """Error responses by status; a key such as "404_resume" documents its status with that variant's text."""
    return {int(str(status).split("_")[0]): {"model": ErrorResponse, "description": ERROR_DESCRIPTIONS[status]}
            for status in statuses}


PDF_HEADERS = {"Cache-Control": "no-store", "Content-Disposition": "inline"}


def pdf_response(content: bytes) -> Response:
    return Response(content, media_type="application/pdf", headers=PDF_HEADERS)


def pdf_ok(description: str) -> dict[int | str, dict[str, Any]]:
    return {200: {"description": description,
                  "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}}


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


# Request-state values copied into the request's log line when set: the ID, and whether a POST found a
# record or a job that already existed. Generation details go on the job's own line (run_job).
LOGGED_STATE = ("application_id", "duplicate")

JOB_EVENTS = {"resume": "resume_job", "cover_letter": "cover_letter_job"}
# The generic errors a failed job records. Details are logged, never stored: the status endpoints are public.
JOB_ERRORS = {"resume": "Resume generation failed", "cover_letter": "Cover letter generation failed"}
STORAGE_UNAVAILABLE = "Storage service unavailable"


def generation_fields(match=None, run=None) -> dict[str, Any]:
    """A job line's generation details: the match result, the Claude runs' size and estimated cost, and how many
    keywords the judge approved and rejected. Never text from the posting or the resume, keywords included."""
    fields = {}
    if match is not None:
        fields.update(match_status=match.status, base_score=match.base_score, tailored_score=match.tailored_score)
    if run is not None:
        fields.update(claude_turns=run.turns,
                      claude_cost_usd=round(run.cost_usd, 4) if run.cost_usd is not None else None,
                      terms_approved=run.terms_approved, terms_rejected=run.terms_rejected)
    return {name: value for name, value in fields.items() if value is not None}


class JobFailed(Exception):
    """A run's failure, already logged in detail. Its message is the generic error the job records."""


def start_thread(job: Callable[[], None]) -> None:
    """Run a generation job on its own daemon thread. It is not tied to the request, so a client that disconnects
    cannot cancel it; a job a restart cuts short is failed when the store next opens."""
    threading.Thread(target=job, daemon=True).start()


def run_job(applications: ApplicationStore, kind: str, application_id: str, started_at: str,
            work: Callable[[dict], tuple[pathlib.Path, dict]]) -> None:
    """Run work, record how it ended on the job, and log one job line. work fills in the line's generation
    details and returns the saved path and the result, or raises JobFailed. Nothing escapes: a thread that died
    silently would leave its job running until the next restart."""
    started = time.perf_counter()
    fields: dict[str, Any] = {}
    try:
        saved_path, result = work(fields)
        outcome = {"status": "done", "saved_path": str(saved_path), "result": result}
    except JobFailed as exc:
        outcome = {"status": "failed", "error": str(exc)}
    except Exception as exc:
        logger.error(json.dumps({"event": f"{kind}_job_error", "application_id": application_id,
                                 "error": type(exc).__name__}))
        outcome = {"status": "failed", "error": JOB_ERRORS[kind]}
    try:
        applications.finish_job(application_id, kind, started_at, **outcome)
    except ApplicationStoreError as exc:
        logger.error(json.dumps({"event": "job_store_error", "application_id": application_id, "error": str(exc)}))
    logger.info(json.dumps({"event": JOB_EVENTS[kind], "application_id": application_id, "outcome": outcome["status"],
                            "duration_ms": round((time.perf_counter() - started) * 1000, 1), **fields}))


def request_event(path: str) -> str | None:
    if path == "/resume" or path.startswith("/resume/"):
        return "resume_request"
    if path == "/cover-letter" or path.startswith("/cover-letter/"):
        return "cover_letter_request"
    if path in ("/application", "/applications") or path.startswith("/application/"):
        return "application_request"
    return None


def application_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "message": message})


def application_not_found() -> JSONResponse:
    return application_error(404, "Application not found")


def file_name(path: str | None) -> str | None:
    """The saved file's name without its folders: responses never show where on the host it was saved."""
    return None if path is None else pathlib.PurePath(path).name


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
    start_job: Callable[[Callable[[], None]], None] | None = None,
) -> FastAPI:
    """Build the app. Settings are validated here, so bad config fails at startup. start_job runs a generation
    job in the background, on its own thread unless given."""
    settings = settings or get_settings()
    start_job = start_job or start_thread
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
            fields: dict[str, Any] = {"event": event, "method": request.method, "status": status}
            fields["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            for name in LOGGED_STATE:
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


    async def requested_application(request: Request, model: type[BaseModel]) -> tuple[StoredApplication | None,
                                                                                       JSONResponse | None]:
        """The stored application a POST body names, or the error response to send instead."""
        try:
            payload = await request.json()
        except ValueError:
            return None, application_error(422, "Request body must be valid JSON")
        if not isinstance(payload, dict):
            return None, application_error(422, "Request body must be a JSON object")
        try:
            requested = model.model_validate(payload).application_id
        except ValidationError as exc:
            return None, application_error(422, validation_message(exc))
        target = parse_application_id(requested)
        if target is None:  # cannot name a row; the raw string stays out of the log line
            return None, application_not_found()
        request.state.application_id = target
        try:
            row = await run_in_threadpool(applications.get, target)
        except ApplicationStoreError as exc:
            return None, store_unavailable(exc)
        if row is None:
            return None, application_not_found()
        return StoredApplication.model_validate(row), None

    def save_report(application_id: str, path, match) -> None:
        """Store the generation report for the viewer. The resume is already saved, so a failure only logs:
        the old report is removed if possible, so the viewer never shows scores for a different PDF."""
        try:
            applications.save_report(application_id, utc_now(), str(path), match.report())
        except ApplicationStoreError as exc:
            logger.error(json.dumps({"event": "report_store_error", "application_id": application_id, "error": str(exc)}))
            try:
                applications.delete_report(application_id)
            except ApplicationStoreError:
                pass

    def save_file(save, application: StoredApplication, content: bytes) -> pathlib.Path:
        try:
            return save(application.company, application.id, content)
        except StorageError as exc:
            logger.error(json.dumps({"event": "storage_error", "application_id": application.id, "error": str(exc)}))
            raise JobFailed(STORAGE_UNAVAILABLE) from exc

    def resume_work(application: StoredApplication):
        def work(fields: dict) -> tuple[pathlib.Path, dict]:
            target = application.id
            try:
                generated = generate_output(application, settings)
            except RenderError as exc:
                logger.error(json.dumps({"event": "render_error", "application_id": target, "error": str(exc)}))
                raise JobFailed(JOB_ERRORS["resume"]) from exc
            except TailoringError as exc:
                fields.update(generation_fields(run=exc.run))
                logger.error(json.dumps({"event": "tailoring_error", "application_id": target, **exc.log_fields()}))
                raise JobFailed(JOB_ERRORS["resume"]) from exc
            fields.update(generation_fields(generated.match, generated.run))
            path = save_file(storage.save_resume, application, generated.content)
            save_report(target, path, generated.match)
            return path, {"match": generated.match.to_dict()}
        return work

    def cover_letter_work(application: StoredApplication):
        def work(fields: dict) -> tuple[pathlib.Path, dict]:
            try:
                written = write_cover_letter(application, settings)
            except TailoringError as exc:
                fields.update(generation_fields(run=exc.run))
                logger.error(json.dumps({"event": "cover_letter_error", "application_id": application.id,
                                         **exc.log_fields()}))
                raise JobFailed(JOB_ERRORS["cover_letter"]) from exc
            fields.update(generation_fields(run=written.run))
            path = save_file(storage.save_cover_letter, application, written.pdf)
            return path, {"text": written.text}
        return work

    async def start_generation(request: Request, kind: str, application: StoredApplication, work) -> JSONResponse:
        """Claim the application's job of this kind and start work in the background, or report the job already
        running. Either way the client gets 202 and polls the status endpoint."""
        started_at = utc_now()
        try:
            claimed, running_since = await run_in_threadpool(applications.start_job, application.id, kind, started_at)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if running_since is None:  # deleted since it was read
            return application_not_found()
        if claimed:
            start_job(lambda: run_job(applications, kind, application.id, started_at, work))
        else:
            request.state.duplicate = True
        return JSONResponse(
            status_code=202,
            content={"ok": True, "application_id": application.id, "status": "running", "started_at": running_since},
        )

    accepted = {"model": GenerationAccepted, "description": "Started, or already running; poll the status endpoint."}

    @app.post(
        "/resume",
        tags=["resumes"],
        summary="Generate a resume PDF",
        description=(
            "Starts generating the resume for a recorded application and returns 202 at once. The run continues "
            "in the background, whether or not the client stays connected: poll "
            "`GET /resume/{application_id}/status` until `status` is `done` or `failed`. When done, the resume is "
            "saved on the service host, replacing any earlier one, and the job's `saved_path` is its file name. "
            "The application itself is not changed.\n\n"
            "A request while a resume job for the application is still running starts no second run: it returns "
            "202 with that job's `started_at`, so retrying after a dropped connection is safe.\n\n"
            "How the resume is chosen, reported in the job's `match.status`:\n"
            "- `no_job_description`: the application has no posting text, or under 50 words of it, so the base "
            "resume is saved unscored.\n"
            "- `base_meets_threshold`: Claude scores the base resume against the posting at 70 or more, so the "
            "base resume is saved.\n"
            "- `tailored`: the base resume scores below 70, so a tailored resume is saved. It uses the same "
            "one-page template, reworded and reordered from the base resume's own facts and checked by script. "
            "It may also use posting keywords the base resume lacks, when a separate Claude judge that never sees "
            "the posting finds them in the resume or the owner's profile list; `match.added_terms` lists them.\n\n"
            "Scoring and tailoring take about 1 to 5 minutes and are capped at about 10. Without usable posting "
            "text the job finishes in seconds."
        ),
        status_code=202,
        responses={202: accepted, **errors(401, 404, 422, 503)},
        openapi_extra=json_body(ResumeRequest, "The application to generate a resume for."),
    )
    async def create_resume(request: Request, x_api_key: str | None = Security(api_key_header)):
        if not api_key_valid(x_api_key):
            return application_error(401, "Invalid or missing API key")
        application, error = await requested_application(request, ResumeRequest)
        if error is not None:
            return error
        return await start_generation(request, "resume", application, resume_work(application))

    def job_status(kind: str, result: str):
        """The handler for a status endpoint: the job's state and result, nothing from the posting."""
        async def read_status(
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
                job = await run_in_threadpool(applications.get_job, target, kind)
            except ApplicationStoreError as exc:
                return store_unavailable(exc)
            if job is None:
                return application_not_found()
            if job == NO_JOB:
                return application_error(404, "No job for this application")
            return {"ok": True, "application_id": target, "status": job["status"], "started_at": job["started_at"],
                    "finished_at": job["finished_at"], "saved_path": file_name(job["saved_path"]),
                    result: job.get(result), "error": job["error"]}
        return read_status

    status_description = (
        "The state of the application's latest {kind} job, started by `POST {post}`: `running`, `done` or `failed`. "
        "When `done`, `saved_path` (the file name only, never a path on the host) and `{result}` are set; when "
        "`failed`, `error` says why in a fixed message, and an earlier {kind} for the application is unchanged. "
        "A job that was running when the service restarted is `failed` with `Interrupted by a service restart`; "
        "request it again.\n\n"
        "Returns only the job's state and result: no posting text and no generation report. Reading it never "
        "starts or changes a job."
    )

    app.get(
        "/resume/{application_id}/status",
        tags=["resumes"],
        summary="Resume job status",
        description=status_description.format(kind="resume", post="/resume", result="match"),
        responses={200: {"model": ResumeJobStatus, "description": "The resume job."}, **errors(401, "404_job", 503)},
    )(job_status("resume", "match"))

    @app.post(
        "/cover-letter",
        tags=["cover letters"],
        summary="Write a cover letter PDF",
        description=(
            "Starts writing a one-page cover letter for a recorded application, tailored to its stored posting, and "
            "returns 202 at once. The run continues in the background, whether or not the client stays connected: "
            "poll `GET /cover-letter/{application_id}/status` until `status` is `done` or `failed`. When done, the "
            "letter is saved on the service host beside the application's resume, replacing any earlier one, the "
            "job's `saved_path` is its file name (`SUNIL BELDE - Cover Letter.pdf`), and the job's `text` is the same "
            "letter as plain text, for application forms that take pasted text. Call it only for applications that "
            "ask for a cover letter: `POST /resume` never writes one. The application itself is not changed, and no "
            "resume is needed.\n\n"
            "A request while a cover letter job for the application is still running starts no second run: it "
            "returns 202 with that job's `started_at`, so retrying after a dropped connection is safe.\n\n"
            "The letter is always tailored, never generic: an application without usable posting text "
            "(`full_job_description` missing, under 50 words or over 60,000 characters) gets a 422 and no job, so "
            "add the posting with `PATCH /application/{application_id}` first. Claude writes the paragraphs from the "
            "owner's base resume and profile only, and scripts check them: every number comes from a cited "
            "source, no posting keyword the owner lacks, no phrasing copied from the posting, the company and "
            "role named, 250 to 400 words on one page.\n\n"
            "Writing takes about 1 to 3 minutes and is capped at about 10."
        ),
        status_code=202,
        responses={202: accepted, **errors(401, 404, "422_letter", 503)},
        openapi_extra=json_body(CoverLetterRequest, "The application to write a cover letter for."),
    )
    async def create_cover_letter(request: Request, x_api_key: str | None = Security(api_key_header)):
        if not api_key_valid(x_api_key):
            return application_error(401, "Invalid or missing API key")
        application, error = await requested_application(request, CoverLetterRequest)
        if error is not None:
            return error
        if not letter_posting_usable(application.full_job_description):
            return application_error(422, "Application has no usable posting text: add full_job_description "
                                          "(at least 50 words) with PATCH /application/{application_id} first")
        return await start_generation(request, "cover_letter", application, cover_letter_work(application))

    app.get(
        "/cover-letter/{application_id}/status",
        tags=["cover letters"],
        summary="Cover letter job status",
        description=status_description.format(kind="cover letter", post="/cover-letter", result="text"),
        responses={200: {"model": CoverLetterJobStatus, "description": "The cover letter job."},
                   **errors(401, "404_job", 503)},
    )(job_status("cover_letter", "text"))

    if docs:
        register_viewer(app, settings, applications, store_unavailable, application_id_path)
    else:
        # PATCH and DELETE share this path, so without a GET route it would answer 405 and reveal that the
        # viewer's read exists somewhere. Answer exactly as for an unknown path instead.
        @app.get("/application/{application_id}", include_in_schema=False)
        def no_application_read(application_id: str):
            raise HTTPException(status_code=404)

    return app


def register_viewer(app: FastAPI, settings: Settings, applications: ApplicationStore, store_unavailable,
                    application_id_path) -> None:
    """The resume viewer's read endpoints. Only for an app with docs enabled: on the public listener none of
    these paths exist, so saved resumes and posting text never leave the tailnet. They take no API key, so
    this docs-only registration is their only guard."""
    base_resume = BaseResumeCache()
    output_root = settings.output_dir.resolve()

    # The page holds no data and needs no key: it reads the endpoints below as soon as it loads.
    @app.get("/viewer", include_in_schema=False)
    def viewer_page() -> HTMLResponse:
        nonce = secrets.token_urlsafe(18)
        return HTMLResponse(page(nonce), headers={
            "Content-Security-Policy": content_security_policy(nonce),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        })

    @app.get(
        "/applications",
        tags=["viewer"],
        summary="List applications",
        description=(
            "Every recorded application with its ID, company, role, status and recording times, most recently "
            "generated first and then most recently recorded. `report` summarises the latest generation (when, "
            "how the resume was chosen, the scores), or is null when none is stored. No posting text."
        ),
        responses={200: {"model": ApplicationList, "description": "The applications."}, **errors(503)},
    )
    async def list_applications():
        try:
            listed = await run_in_threadpool(applications.list_with_reports)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        return {"ok": True, "applications": listed}

    async def find(request: Request, application_id: str) -> tuple[str | None, dict | None, JSONResponse | None]:
        """The ID, stored row and report of an application, or the error response to send instead."""
        target = parse_application_id(application_id)
        if target is None:
            return None, None, application_not_found()
        request.state.application_id = target
        try:
            row = await run_in_threadpool(applications.get, target)
            report = await run_in_threadpool(applications.get_report, target) if row else None
        except ApplicationStoreError as exc:
            return None, None, store_unavailable(exc)
        if row is None:
            return None, None, application_not_found()
        return target, {"application": row, "report": report}, None

    @app.get(
        "/application/{application_id}",
        tags=["viewer"],
        summary="Read an application and its report",
        description=(
            "Every stored field of the application, the posting text included, and its latest generation report: "
            "how the resume was chosen, the base and tailored score breakdowns (each posting keyword and whether "
            "the resume covers it, each requirement with its assessment and quoted evidence), the keywords added "
            "and the keywords the judge rejected. `report` is null when none is stored: never generated, or "
            "generated before reports were kept."
        ),
        responses={200: {"model": ApplicationDetail, "description": "The application and its report."},
                   **errors(404, 503)},
    )
    async def read_application(request: Request, application_id: str = application_id_path):
        _, found, error = await find(request, application_id)
        if error is not None:
            return error
        report = found["report"]
        if report is not None:
            # The stored path finds the PDFs after a company rename; the response names only the file.
            report = {**report, "saved_path": file_name(report["saved_path"])}
        return {"ok": True, "application": found["application"], "report": report}

    def read_output(path: pathlib.Path) -> bytes | None:
        """The saved file's bytes, or None when there is no regular file there inside OUTPUT_DIR."""
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(output_root) or not resolved.is_file():
                return None
            return resolved.read_bytes()
        except OSError:
            return None

    @app.get(
        "/application/{application_id}/resume.pdf",
        tags=["viewer"],
        summary="Read an application's saved resume",
        description=(
            "The resume PDF saved for the application by its latest generation, read from the path recorded in "
            "its report, so a company renamed since still finds it. Without a report, the resume path for the "
            "current company is used. Sent inline with `Cache-Control: no-store`."
        ),
        responses={**pdf_ok("The saved resume."), **errors("404_resume", 503)},
        response_class=Response,
    )
    async def read_saved_resume(request: Request, application_id: str = application_id_path):
        target, found, error = await find(request, application_id)
        if error is not None:
            return error
        report = found["report"]
        path = pathlib.Path(report["saved_path"]) if report else resume_path(output_root, found["application"]["company"], target)
        content = await run_in_threadpool(read_output, path)
        if content is None:
            return application_error(404, "Resume not found")
        return pdf_response(content)

    def read_cover_letter(application: dict, application_id: str, report: dict | None) -> bytes | None:
        """The saved cover letter: first where POST /cover-letter would save it now, then beside the resume the
        report points to, which finds a letter written before the company was renamed."""
        candidates = [cover_letter_path(output_root, application["company"], application_id)]
        if report:
            candidates.append(pathlib.Path(report["saved_path"]).parent / COVER_LETTER_FILE_NAME)
        for path in candidates:
            content = read_output(path)
            if content is not None:
                return content
        return None

    @app.get(
        "/application/{application_id}/cover-letter.pdf",
        tags=["viewer"],
        summary="Read an application's saved cover letter",
        description=(
            "The cover letter PDF saved for the application by `POST /cover-letter`. Looked for in the "
            "application's folder for its current company, then beside the resume its report points to, so a "
            "letter written before the company was renamed is still found. Sent inline with "
            "`Cache-Control: no-store`."
        ),
        responses={**pdf_ok("The saved cover letter."), **errors("404_letter", 503)},
        response_class=Response,
    )
    async def read_saved_cover_letter(request: Request, application_id: str = application_id_path):
        target, found, error = await find(request, application_id)
        if error is not None:
            return error
        content = await run_in_threadpool(read_cover_letter, found["application"], target, found["report"])
        if content is None:
            return application_error(404, "Cover letter not found")
        return pdf_response(content)

    @app.get(
        "/resume/base.pdf",
        tags=["viewer"],
        summary="Read the base resume",
        description=(
            "The base resume, rendered from the bundled template: the same PDF `POST /resume` saves when it keeps "
            "the base resume. Rendered again whenever a template file changes. Sent inline with "
            "`Cache-Control: no-store`."
        ),
        responses={**pdf_ok("The base resume."), **errors("500_base")},
        response_class=Response,
    )
    async def read_base_resume():
        try:
            content = await run_in_threadpool(base_resume.get)
        except RenderError as exc:
            logger.error(json.dumps({"event": "render_error", "error": str(exc)}))
            return application_error(500, "Resume generation failed")
        return pdf_response(content)

    @app.get(
        "/cover-letter/base.pdf",
        tags=["viewer"],
        summary="Read the base cover letter",
        description=(
            "The generic base cover letter committed as `data/COVER_LETTER.pdf`, served unchanged and read again "
            "on every request, so a letter the owner re-renders shows straight away. The service never generates "
            "or edits it, and tailored letters do not use it. Sent inline with `Cache-Control: no-store`."
        ),
        responses={**pdf_ok("The base cover letter."), **errors("404_base_letter")},
        response_class=Response,
    )
    async def read_base_letter():
        content = await run_in_threadpool(read_base_cover_letter)
        if content is None:
            return application_error(404, "Base cover letter not found")
        return pdf_response(content)
