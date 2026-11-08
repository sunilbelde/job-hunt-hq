"""The Slack workflow's keyed endpoints, registered only on the local listener (with the viewer).

Hermes, connected to the owner's Slack, calls these to start a fill from an application's thread and to record the
owner's answers; the Slack-mode form filler calls them to ask questions and post its reports. See app/slack.py.
"""

import json
import logging
from typing import Callable

from fastapi import FastAPI, Path, Query, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.applications import ApplicationStore, ApplicationStoreError
from app.form_filler import FormFillLauncher, HerdrUnavailable
from app.models import (
    AnswersRecorded,
    AnswersRequest,
    ErrorResponse,
    FillFormStarted,
    FillFromSlackRequest,
    PendingQuestions,
    QuestionBatchCreated,
    QuestionBatchRequest,
    QuestionBatchState,
    QuestionsCancelled,
    SlackErrorResponse,
    SlackReportPosted,
    SlackUpdatePosted,
    SlackUpdateRequest,
)
from app.slack import SlackError, SlackNotifier, format_batch

logger = logging.getLogger("app.requests")

BODY_MODELS = (FillFromSlackRequest, QuestionBatchRequest, AnswersRequest, SlackUpdateRequest)

# Words that approve. A declining answer (its label starts with "no") needs only the owner's message to exist.
APPROVING_WORDS = ("yes", "approve", "submit")


def slack_error(status: int, reason: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "reason": reason, "message": message})


def not_configured() -> JSONResponse:
    return slack_error(503, "slack_not_configured", "Slack is not configured (SLACK_BOT_TOKEN, SLACK_CHANNEL_ID)")


def no_thread() -> JSONResponse:
    return slack_error(409, "no_thread", "This application has no Slack thread yet")


def batch_state(batch: dict) -> dict:
    return {"ok": True, "application_id": batch["application_id"], "question_id": batch["question_id"],
            "status": batch["status"], "questions": batch["questions"], "answers": batch["answers"],
            "created_at": batch["created_at"], "answered_at": batch["answered_at"]}


def declines(label: str) -> bool:
    return label.strip().lower().startswith("no")


def approval_verified(messages: list[dict], message_ts: str, owner: str, posted_ts: str | None,
                      chosen: list[str]) -> bool:
    """Whether the thread holds the owner's own reply at message_ts, newer than the question, saying what the
    approval answer says. Bot messages never count, whatever their text."""
    message = next((m for m in messages if m.get("ts") == message_ts), None)
    if message is None or message.get("bot_id") or message.get("subtype") or message.get("user") != owner:
        return False
    if posted_ts is None or float(message_ts) <= float(posted_ts):
        return False
    if all(declines(label) for label in chosen):
        return True
    text = " ".join(str(message.get("text") or "").lower().split())
    return text.startswith(APPROVING_WORDS) or any(label.strip().lower() in text for label in chosen)


def register_slack(app: FastAPI, *, applications: ApplicationStore, notifier: SlackNotifier,
                   form_filler: FormFillLauncher, owner_user_id: str | None, api_key_header, api_key_valid,
                   store_unavailable: Callable, application_id_path, parse_application_id: Callable,
                   validation_message: Callable) -> None:

    def errors(*pairs: tuple[int, str]) -> dict:
        return {status: {"model": SlackErrorResponse if model == "slack" else ErrorResponse, "description": text}
                for status, model, text in pairs}

    common = ((401, "plain", "Missing or wrong `X-API-Key`. Checked first."),)
    unknown = (404, "plain", "No application has this ID (`Application not found`).")
    unconfigured = (503, "slack", "`slack_not_configured`: no Slack token or channel; or the application store "
                                  "is unavailable (`message` says which).")

    def body_doc(model: type[BaseModel], description: str, required: bool = True) -> dict:
        return {"requestBody": {"required": required, "description": description, "content": {"application/json": {
            "schema": {"$ref": f"#/components/schemas/{model.__name__}"},
            "example": model.model_config["json_schema_extra"]["examples"][0]}}}}

    async def guard(request: Request, x_api_key: str | None, application_id: str):
        """Key, Slack configured, ID parsed and existing: (id, row) or (None, error response)."""
        if not api_key_valid(x_api_key):
            return None, JSONResponse(status_code=401, content={"ok": False, "message": "Invalid or missing API key"})
        if not notifier.enabled:
            return None, not_configured()
        target = parse_application_id(application_id)
        if target is None:
            return None, JSONResponse(status_code=404, content={"ok": False, "message": "Application not found"})
        request.state.application_id = target
        try:
            row = await run_in_threadpool(applications.get, target)
        except ApplicationStoreError as exc:
            return None, store_unavailable(exc)
        if row is None:
            return None, JSONResponse(status_code=404, content={"ok": False, "message": "Application not found"})
        return (target, row), None

    async def read_body(request: Request, model: type[BaseModel], empty_ok: bool = False):
        raw = await request.body()
        if empty_ok and not raw.strip():
            return model(), None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None, JSONResponse(status_code=422, content={"ok": False, "message": "Request body must be valid JSON"})
        if not isinstance(payload, dict):
            return None, JSONResponse(status_code=422,
                                      content={"ok": False, "message": "Request body must be a JSON object"})
        try:
            return model.model_validate(payload), None
        except ValidationError as exc:
            return None, JSONResponse(status_code=422, content={"ok": False, "message": validation_message(exc)})

    @app.post(
        "/application/{application_id}/slack-report",
        tags=["slack"],
        summary="Post an application's ready report to Slack",
        description=(
            "Posts the report that starts the application's thread in `SLACK_CHANNEL_ID`, when its resume job is "
            "`done` and no job is running. Normally this happens on its own when generation finishes; use this to "
            "retry after Slack was unreachable. With a thread already there, nothing is posted and `already_posted` "
            "is true."),
        responses={200: {"model": SlackReportPosted, "description": "Posted now, or already posted."},
                   **errors(*common, unknown,
                            (409, "slack", "`resume_not_ready`: the resume is not done, or a job is still running."),
                            (502, "slack", "`slack_error`: Slack refused the post or could not be reached."),
                            unconfigured)},
    )
    async def slack_report(request: Request, application_id: str = application_id_path,
                           x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        target, _ = found
        try:
            result = await run_in_threadpool(notifier.post_report, target)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        except SlackError:
            return slack_error(502, "slack_error", "Slack refused the post or could not be reached")
        if result.state in ("not_ready", "in_progress") or result.thread_ts is None:
            return slack_error(409, "resume_not_ready", "The resume is not done, or a generation job is running")
        return {"ok": True, "application_id": target, "thread_ts": result.thread_ts,
                "already_posted": result.state != "posted"}

    async def say(target: str, text: str, kind: str) -> None:
        """A best-effort line in the thread; failures are logged by the notifier."""
        try:
            await run_in_threadpool(notifier.post_in_thread, target, text, kind)
        except (SlackError, LookupError, ApplicationStoreError):
            pass

    @app.post(
        "/application/{application_id}/fill",
        tags=["slack"],
        summary="Start the form filler from Slack",
        description=(
            "Opens the application's form-filling tab exactly as the viewer's Fill form does, running "
            "`claude --chrome \"/job-application-form-filler <application_id> slack\"`: in Slack mode the form "
            "filler asks its questions and posts its reports in the application's thread. If a tab for this ID is "
            "already open, nothing is started and `already_open` is true. Needs the application's Slack thread. "
            "Local listener only."),
        responses={200: {"model": FillFormStarted, "description": "The tab was opened, or one was already open."},
                   **errors(*common, unknown,
                            (409, "slack", "`no_thread`: the application's report was never posted."),
                            (422, "plain", "The body is not JSON or not a JSON object, or `mode` is not `slack`."),
                            (503, "slack", "`slack_not_configured`, Herdr unavailable, or the store unavailable.")),
                   },
        openapi_extra=body_doc(FillFromSlackRequest, "Optional; the mode is always `slack`.", required=False),
    )
    async def fill_from_slack(request: Request, application_id: str = application_id_path,
                              x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        target, row = found
        _, error = await read_body(request, FillFromSlackRequest, empty_ok=True)
        if error is not None:
            return error
        try:
            thread = await run_in_threadpool(applications.get_slack_thread, target)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if thread is None or thread["thread_ts"] is None:
            return no_thread()
        try:
            started = await run_in_threadpool(form_filler.start, row["company"], row["role"], target, "slack")
        except HerdrUnavailable as exc:
            logger.error(json.dumps({"event": "herdr_error", "application_id": target, "error": str(exc)}))
            return JSONResponse(status_code=503, content={"ok": False, "message": "Herdr unavailable"})
        await say(target, "A form-filling session is already open for this application." if started.already_open
                  else "Started filling the form. Questions will appear here.", "fill")
        return {"ok": True, "application_id": target, "tab_id": started.tab_id, "tab_label": started.tab_label,
                "already_open": started.already_open}

    @app.post(
        "/application/{application_id}/questions",
        tags=["slack"],
        summary="Ask the owner questions in the application's thread",
        description=(
            "For the Slack-mode form filler: the batch it would have passed to AskUserQuestion (1 to 4 questions, "
            "2 to 4 options each). Stored as `pending`, cancelling any older pending batch for the application, "
            "and posted in the thread as a numbered list with lettered options. Poll "
            "`GET /application/{application_id}/questions/{question_id}` for the answers. Question text is never "
            "logged."),
        status_code=201,
        responses={201: {"model": QuestionBatchCreated, "description": "Stored and posted."},
                   **errors(*common, unknown,
                            (409, "slack", "`no_thread`: the application has no Slack thread."),
                            (422, "plain", "The body fails validation; `message` names the fields."),
                            (502, "slack", "`slack_error`: Slack refused the post; the batch was cancelled."),
                            unconfigured)},
        openapi_extra=body_doc(QuestionBatchRequest, "The questions."),
    )
    async def ask_questions(request: Request, application_id: str = application_id_path,
                            x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        target, _ = found
        batch, error = await read_body(request, QuestionBatchRequest)
        if error is not None:
            return error
        questions = [q.model_dump() for q in batch.questions]
        try:
            thread = await run_in_threadpool(applications.get_slack_thread, target)
            if thread is None or thread["thread_ts"] is None:
                return no_thread()
            question_id = await run_in_threadpool(applications.add_question_batch, target, questions)
            if question_id is None:
                return JSONResponse(status_code=404, content={"ok": False, "message": "Application not found"})
            try:
                posted = await run_in_threadpool(notifier.post_in_thread, target, format_batch(questions), "questions")
            except (SlackError, LookupError):
                await run_in_threadpool(applications.cancel_question_batch, target, question_id)
                return slack_error(502, "slack_error", "Slack refused the post or could not be reached")
            await run_in_threadpool(applications.set_question_batch_ts, question_id, posted[-1])
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        return JSONResponse(status_code=201, content={"ok": True, "application_id": target, "question_id": question_id})

    @app.get(
        "/application/{application_id}/questions",
        tags=["slack"],
        summary="The application's pending questions",
        description="For Hermes: the batch waiting for the owner's answers, or `pending: null`.",
        responses={200: {"model": PendingQuestions, "description": "The pending batch, if any."},
                   **errors(*common, unknown, (422, "plain", "`status` is not `pending`."), unconfigured)},
    )
    async def pending_questions(request: Request, application_id: str = application_id_path,
                                status: str = Query("pending", description="Only `pending` is supported."),
                                x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        if status != "pending":
            return JSONResponse(status_code=422, content={"ok": False, "message": "status: only pending is supported"})
        target, _ = found
        try:
            batch = await run_in_threadpool(applications.pending_question_batch, target)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        return {"ok": True, "application_id": target, "pending": batch_state(batch) if batch else None}

    async def find_batch(target: str, question_id: str):
        qid = parse_application_id(question_id)  # question IDs are UUIDs too
        if qid is None:
            return None, JSONResponse(status_code=404, content={"ok": False, "message": "Question batch not found"})
        try:
            batch = await run_in_threadpool(applications.get_question_batch, target, qid)
        except ApplicationStoreError as exc:
            return None, store_unavailable(exc)
        if batch is None:
            return None, JSONResponse(status_code=404, content={"ok": False, "message": "Question batch not found"})
        return batch, None

    question_id_path = Path(description="The batch's UUID, as returned when it was posted.")
    question_404 = (404, "plain", "No such application, or no such batch for it (`Question batch not found`).")

    @app.get(
        "/application/{application_id}/questions/{question_id}",
        tags=["slack"],
        summary="A question batch and its answers",
        description="For the Slack-mode form filler, polling until `status` is `answered` (or `cancelled`).",
        responses={200: {"model": QuestionBatchState, "description": "The batch."},
                   **errors(*common, question_404, unconfigured)},
    )
    async def get_questions(request: Request, application_id: str = application_id_path, question_id: str = question_id_path,
                            x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        batch, error = await find_batch(found[0], question_id)
        return error if error is not None else batch_state(batch)

    @app.delete(
        "/application/{application_id}/questions/{question_id}",
        tags=["slack"],
        summary="Cancel a pending question batch",
        description="For the form filler, when the owner takes over at the Mac. Only a pending batch can be cancelled.",
        responses={200: {"model": QuestionsCancelled, "description": "Cancelled."},
                   **errors(*common, question_404, (409, "slack", "`not_pending`: already answered or cancelled."),
                            unconfigured)},
    )
    async def cancel_questions(request: Request, application_id: str = application_id_path, question_id: str = question_id_path,
                               x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        batch, error = await find_batch(found[0], question_id)
        if error is not None:
            return error
        try:
            outcome = await run_in_threadpool(applications.cancel_question_batch, found[0], batch["question_id"])
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if outcome != "cancelled":
            return slack_error(409, "not_pending", "This batch is no longer pending")
        return {"ok": True, "application_id": found[0], "question_id": batch["question_id"], "status": "cancelled"}

    @app.post(
        "/application/{application_id}/questions/{question_id}/answers",
        tags=["slack"],
        summary="Record the owner's answers",
        description=(
            "For Hermes, after the owner replies in the thread: one entry per question, in order, each the chosen "
            "option labels or the owner's own words.\n\n"
            "A batch with an `approval` question (agree and submit, mark applied) is accepted only when "
            "`slack_message_ts` names the owner's own reply in the thread (`SLACK_OWNER_USER_ID`, not a bot), newer "
            "than the question, whose text starts with yes, approve or submit, or contains the chosen label; a "
            "declining answer (a label starting with No) needs only the owner's reply. The service reads that reply "
            "from Slack itself, so no relay can approve a submission on the owner's behalf. Answers are never logged."),
        responses={200: {"model": AnswersRecorded, "description": "Recorded; the form filler's next poll gets them."},
                   **errors(*common, question_404,
                            (409, "slack", "`not_pending`: already answered or cancelled. Nothing changed."),
                            (422, "slack", "`answer_count` (not one answer per question) or `approval_not_verified` "
                                           "(no matching owner reply); or a body that fails validation."),
                            (502, "slack", "`slack_error`: the thread could not be read to verify an approval."),
                            (503, "slack", "`slack_not_configured`, no `SLACK_OWNER_USER_ID` for an approval, or the "
                                           "store unavailable."))},
        openapi_extra=body_doc(AnswersRequest, "The answers, and the owner's reply they come from."),
    )
    async def answer_questions(request: Request, application_id: str = application_id_path, question_id: str = question_id_path,
                               x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        target = found[0]
        body, error = await read_body(request, AnswersRequest)
        if error is not None:
            return error
        batch, error = await find_batch(target, question_id)
        if error is not None:
            return error
        if batch["status"] != "pending":
            return slack_error(409, "not_pending", "This batch is no longer pending")
        if len(body.answers) != len(batch["questions"]):
            return slack_error(422, "answer_count", "Send exactly one answer per question, in order")
        approvals = [answer for question, answer in zip(batch["questions"], body.answers)
                     if question.get("kind") == "approval"]
        if approvals:
            if owner_user_id is None:
                return slack_error(503, "slack_not_configured", "SLACK_OWNER_USER_ID is not set: approvals are off")
            if not body.slack_message_ts:
                return slack_error(422, "approval_not_verified", "An approval needs the owner's reply (slack_message_ts)")
            try:
                thread = await run_in_threadpool(applications.get_slack_thread, target)
                if thread is None or thread["thread_ts"] is None:
                    return no_thread()
                messages = await run_in_threadpool(notifier.client.thread_replies, thread["channel"],
                                                   thread["thread_ts"])
            except ApplicationStoreError as exc:
                return store_unavailable(exc)
            except SlackError as exc:
                logger.error(json.dumps({"event": "slack_read", "application_id": target, "error": str(exc)}))
                return slack_error(502, "slack_error", "Could not read the thread to verify the approval")
            chosen = [label for answer in approvals for label in answer]
            try:
                verified = approval_verified(messages, body.slack_message_ts, owner_user_id, batch["slack_ts"], chosen)
            except ValueError:
                verified = False
            if not verified:
                logger.info(json.dumps({"event": "approval_not_verified", "application_id": target}))
                return slack_error(422, "approval_not_verified",
                                   "No reply from the owner in this thread approves this answer")
        try:
            outcome = await run_in_threadpool(applications.answer_question_batch, target, batch["question_id"],
                                              body.answers, body.slack_message_ts if approvals else None)
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        if outcome != "answered":
            return slack_error(409, "not_pending", "This batch is no longer pending")
        return {"ok": True, "application_id": target, "question_id": batch["question_id"], "status": "answered"}

    @app.post(
        "/application/{application_id}/slack-update",
        tags=["slack"],
        summary="Post an update in the application's thread",
        description=("For the Slack-mode form filler's reports and progress. Split into messages of at most 3,500 "
                     "characters on line boundaries. Text is never logged."),
        responses={200: {"model": SlackUpdatePosted, "description": "Posted."},
                   **errors(*common, unknown,
                            (409, "slack", "`no_thread`: the application has no Slack thread."),
                            (422, "plain", "The body fails validation; `message` names the fields."),
                            (502, "slack", "`slack_error`: Slack refused a post (earlier parts may be posted)."),
                            unconfigured)},
        openapi_extra=body_doc(SlackUpdateRequest, "The text to post."),
    )
    async def slack_update(request: Request, application_id: str = application_id_path,
                           x_api_key: str | None = Security(api_key_header)):
        found, error = await guard(request, x_api_key, application_id)
        if error is not None:
            return error
        target = found[0]
        body, error = await read_body(request, SlackUpdateRequest)
        if error is not None:
            return error
        try:
            posted = await run_in_threadpool(notifier.post_in_thread, target, body.text, "update")
        except LookupError:
            return no_thread()
        except ApplicationStoreError as exc:
            return store_unavailable(exc)
        except SlackError:
            return slack_error(502, "slack_error", "Slack refused the post or could not be reached")
        return {"ok": True, "application_id": target, "messages": len(posted)}
