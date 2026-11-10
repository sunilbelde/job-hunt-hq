"""The Slack workflow: one thread per application in the owner's channel.

The service posts with the Hermes Slack app's bot token. It never receives Slack events: Hermes, connected to the
same app through Socket Mode, reads the thread and calls this service's keyed endpoints. Because the posts come from
Hermes's own bot, they never start a Hermes turn, but Hermes sees them as thread context.

Nothing here logs message text, question text, answers or the token: only which kind of post went to which
application, and whether Slack accepted it.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from app.applications import ApplicationStore, ApplicationStoreError

logger = logging.getLogger("app.requests")

SLACK_TIMEOUT_SECONDS = 10
MESSAGE_LIMIT = 3500
VIEWER_URL = "http://127.0.0.1:8081/viewer#{id}"
OPTION_LETTERS = "abcd"
KIND_NAMES = {"resume": "Resume", "cover_letter": "Cover letter"}


class SlackError(Exception):
    """Slack refused a call or could not be reached. The message is Slack's error code or the failure's type,
    never the token or the text."""


class SlackClient:
    def __init__(self, token: str, api_base: str = "https://slack.com/api", timeout: float = SLACK_TIMEOUT_SECONDS):
        self._token = token
        self._base = api_base.rstrip("/")
        self._timeout = timeout

    def _call(self, method: str, *, json_body: dict | None = None, form: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json; charset=utf-8"
        else:
            data = urllib.parse.urlencode(form or {}).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(f"{self._base}/{method}", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as exc:
            raise SlackError(f"{method}: HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise SlackError(f"{method}: {type(exc).__name__}") from None
        if not isinstance(reply, dict) or not reply.get("ok"):
            error = reply.get("error") if isinstance(reply, dict) else None
            raise SlackError(f"{method}: {error if isinstance(error, str) else 'not ok'}")
        return reply

    def post_message(self, channel: str, text: str, thread_ts: str | None = None) -> str:
        """Post text (mrkdwn) and return the new message's ts."""
        body: dict[str, Any] = {"channel": channel, "text": text, "unfurl_links": False, "unfurl_media": False}
        if thread_ts is not None:
            body["thread_ts"] = thread_ts
        ts = self._call("chat.postMessage", json_body=body).get("ts")
        if not isinstance(ts, str):
            raise SlackError("chat.postMessage: no ts")
        return ts

    def thread_replies(self, channel: str, thread_ts: str) -> list[dict]:
        """Every message in the thread, root first (paged)."""
        messages: list[dict] = []
        cursor = None
        for _ in range(20):  # 20 pages of 200 is far beyond any application thread
            form = {"channel": channel, "ts": thread_ts, "limit": "200"}
            if cursor:
                form["cursor"] = cursor
            reply = self._call("conversations.replies", form=form)
            messages.extend(m for m in reply.get("messages", []) if isinstance(m, dict))
            cursor = (reply.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return messages


# ---------------------------------------------------------------- formatting

def escape(text: str) -> str:
    """Slack mrkdwn escaping for text that came from a posting or a form: no stray links or mentions."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _document_state(job: dict | str | None) -> str:
    if not isinstance(job, dict):
        return "not generated"
    return {"done": "✓", "failed": "failed", "running": "generating"}.get(job.get("status"), "not generated")


def _scores(report: dict | None) -> str | None:
    if not report:
        return None
    base, tailored = report.get("base_score"), report.get("tailored_score")
    if base is None and tailored is None:
        return None
    if tailored is None or tailored == base:
        return str(base)
    return f"{base} → {tailored}"


def format_report(application: dict, jobs: dict[str, Any], report: dict | None) -> str:
    """The ready report that starts an application's thread. Empty fields are left out; the App ID line is
    always there, in a fixed form Hermes reads back."""
    company, role, app_id = escape(application["company"]), escape(application["role"]), application["id"]
    lines = [f"*Ready for review:* {role} at {company}", f"*App ID:* `{app_id}`"]
    score = _scores(report)
    if score:
        lines.append(f"*Match:* {score}")
    if application.get("why_it_fits"):
        lines.append(f"*Why it fits:* {escape(application['why_it_fits'])}")
    details = [f"*{label}:* {escape(str(application[field]))}"
               for field, label in (("location", "Location"), ("work_type", "Work type"), ("salary", "Salary"),
                                    ("sponsorship", "Sponsorship"))
               if application.get(field)]
    if details:
        lines.append("  ·  ".join(details))
    if application.get("job_link"):
        lines.append(f"*Posting:* {escape(application['job_link'])}")
    lines.append(f"*Viewer:* {VIEWER_URL.format(id=app_id)}")
    lines.append(f"Documents: resume {_document_state(jobs.get('resume'))} · "
                 f"cover letter {_document_state(jobs.get('cover_letter'))}")
    lines.append('Reply in this thread with "@Hermes fill form" to start the application.')
    return "\n".join(lines)


def format_job_reply(kind: str, job: dict | str | None, report: dict | None) -> str | None:
    """A thread reply for a generation job that ended after the report was posted."""
    if not isinstance(job, dict) or job.get("status") not in ("done", "failed"):
        return None
    name = KIND_NAMES[kind]
    if job["status"] == "failed":
        return f"{name} generation failed: {escape(job.get('error') or 'unknown error')}"
    if kind == "resume":
        score = _scores(report)
        return "Resume regenerated ✓" + (f"  ·  *Match:* {score}" if score else "")
    return "Cover letter generated ✓"


def format_batch(questions: list[dict]) -> str:
    """A question batch as a numbered list with lettered options, ending with how to answer."""
    lines = ["*The form filler has a question:*" if len(questions) == 1 else "*The form filler has questions:*"]
    approval = any(q.get("kind") == "approval" for q in questions)
    for number, question in enumerate(questions, 1):
        multi = " _(pick any)_" if question.get("multi_select") else ""
        lines.append(f"*{number}. {escape(question['question'])}*{multi}")
        for letter, option in zip(OPTION_LETTERS, question["options"]):
            description = f" — {escape(option['description'])}" if option.get("description") else ""
            lines.append(f"    {letter}) {escape(option['label'])}{description}")
    if approval:
        lines.append("_This needs your approval: reply yourself, starting with \"yes\" to approve._")
    else:
        lines.append("_Reply in this thread (e.g. \"1a, 2: 5 years\"), or with your own answer._")
    return "\n".join(lines)


def split_text(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Messages of at most limit characters, split on line boundaries (a single over-long line is cut)."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current.strip():
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


# ---------------------------------------------------------------- the notifier

@dataclass(frozen=True)
class ReportResult:
    """posted: a report went up now (thread_ts set); existing: one was already there (thread_ts set);
    not_ready: the resume is not done or a job is running; in_progress: another report is being posted."""
    state: str
    thread_ts: str | None = None


class SlackNotifier:
    """Posts ready reports and thread replies. A no-op when Slack is not configured. Never raises from after_job:
    a generation job's outcome must never depend on Slack."""

    def __init__(self, applications: ApplicationStore, channel: str | None, client: SlackClient | None,
                 log: Callable[[dict], None] | None = None):
        self.applications = applications
        self.channel = channel
        self.client = client
        self._log = log or (lambda fields: logger.info(json.dumps(fields)))

    @property
    def enabled(self) -> bool:
        return self.client is not None and self.channel is not None

    def log(self, application_id: str, kind: str, error: str | None = None) -> None:
        fields = {"event": "slack_post", "application_id": application_id, "kind": kind, "ok": error is None}
        if error is not None:
            fields["error"] = error
        self._log(fields)

    def _jobs(self, application_id: str) -> dict[str, Any]:
        return {kind: self.applications.get_job(application_id, kind) for kind in ("resume", "cover_letter")}

    def post_report(self, application_id: str) -> ReportResult:
        """Claim and post the ready report. Raises SlackError (claim released) when Slack refuses it."""
        claim = self.applications.claim_slack_report(application_id, self.channel)
        if claim.state != "claimed":
            return ReportResult(claim.state, claim.thread_ts)
        try:
            application = self.applications.get(application_id)
            if application is None:
                self.applications.release_slack_claim(application_id)
                return ReportResult("not_ready")
            text = format_report(application, self._jobs(application_id), self.applications.get_report(application_id))
            ts = self.client.post_message(self.channel, text)
        except BaseException as exc:
            self.applications.release_slack_claim(application_id)
            if isinstance(exc, SlackError):
                self.log(application_id, "report", str(exc))
            raise
        self.applications.set_slack_thread_ts(application_id, ts)
        self.log(application_id, "report")
        return ReportResult("posted", ts)

    def post_in_thread(self, application_id: str, text: str, kind: str = "update") -> list[str]:
        """Post text in the application's thread, split as needed. Raises LookupError without a thread and
        SlackError when Slack refuses."""
        thread = self.applications.get_slack_thread(application_id)
        if thread is None or thread["thread_ts"] is None:
            raise LookupError("no thread")
        posted = []
        try:
            for chunk in split_text(text):
                posted.append(self.client.post_message(thread["channel"], chunk, thread_ts=thread["thread_ts"]))
        except SlackError as exc:
            self.log(application_id, kind, str(exc))
            raise
        self.log(application_id, kind)
        return posted

    def after_job(self, application_id: str, kind: str, finished_at: str | None = None) -> None:
        """Called after every generation job ends: post the report once the documents are ready, or reply in the
        thread for a job that ended after the report."""
        if not self.enabled:
            return
        try:
            thread = self.applications.get_slack_thread(application_id)
            if thread is None:
                self.post_report(application_id)
                return
            if thread["thread_ts"] is None:
                return  # another job's report is being posted right now; it covers this job too
            job = self.applications.get_job(application_id, kind)
            # A job that ended before the report was claimed is already in the report.
            if not isinstance(job, dict) or (job.get("finished_at") or "") <= thread["claimed_at"]:
                return
            text = format_job_reply(kind, job, self.applications.get_report(application_id))
            if text:
                self.post_in_thread(application_id, text, kind="reply")
        except SlackError:
            pass  # already logged
        except (ApplicationStoreError, LookupError) as exc:
            self.log(application_id, "report", type(exc).__name__)
        except Exception as exc:  # never let Slack break a job
            self.log(application_id, "report", type(exc).__name__)


def build_notifier(settings, applications: ApplicationStore) -> SlackNotifier:
    client = None
    if settings.slack_enabled:
        client = SlackClient(settings.slack_bot_token.get_secret_value(), settings.slack_api_base)
    return SlackNotifier(applications, settings.slack_channel_id, client)
