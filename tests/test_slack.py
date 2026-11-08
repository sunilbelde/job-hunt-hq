"""The Slack workflow: ready reports, thread replies, fill from Slack, the question relay and verified approvals."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient

from app.applications import ApplicationStore
from app.form_filler import FillStarted, HerdrUnavailable, fill_command
from app.main import create_app
from app.slack import SlackClient, SlackError, SlackNotifier, format_batch, format_report, split_text
from app.slack_routes import approval_verified
from tests.conftest import API_KEY, LONG_POSTING, VALID_APPLICATION

KEY = {"X-API-Key": API_KEY}
OWNER = "U0OWNER"
CHANNEL = "C0JOBS"


class FakeSlack:
    """Records posts; serves thread replies from what was posted plus what tests add as the owner."""

    def __init__(self):
        self.posts: list[dict] = []
        self.extra: list[dict] = []
        self.fail = False
        self.read_fail = False
        self._ts = 1762570000.0

    def post_message(self, channel, text, thread_ts=None):
        if self.fail:
            raise SlackError("chat.postMessage: channel_not_found")
        self._ts += 1
        ts = f"{self._ts:.6f}"
        self.posts.append({"channel": channel, "text": text, "thread_ts": thread_ts, "ts": ts})
        return ts

    def owner_reply(self, text, user=OWNER, bot=False):
        self._ts += 1
        ts = f"{self._ts:.6f}"
        message = {"ts": ts, "text": text, "user": user}
        if bot:
            message["bot_id"] = "B0HERMES"
        self.extra.append(message)
        return ts

    def thread_replies(self, channel, thread_ts):
        if self.read_fail:
            raise SlackError("conversations.replies: ratelimited")
        own = [{"ts": p["ts"], "text": p["text"], "bot_id": "B0HERMES"} for p in self.posts]
        return own + self.extra

    def top_level(self):
        return [p for p in self.posts if p["thread_ts"] is None]


class FakeLauncher:
    def __init__(self, fail=False, already_open=False):
        self.calls = []
        self.fail = fail
        self.already_open = already_open

    def start(self, company, role, application_id, mode=None):
        if self.fail:
            raise HerdrUnavailable("herdr tab create exited 1")
        self.calls.append((company, role, application_id, mode))
        return FillStarted("wK:t3", f"{company}-{role}-{application_id}", "wK", self.already_open)


@pytest.fixture
def slack():
    return FakeSlack()


@pytest.fixture
def launcher():
    return FakeLauncher()


@pytest.fixture
def store(settings):
    return ApplicationStore(settings.output_dir / "applications.sqlite3")


@pytest.fixture
def slack_settings(settings):
    return settings.model_copy(update={"api_docs_enabled": True, "slack_bot_token": "xoxb-test",
                                       "slack_channel_id": CHANNEL, "slack_owner_user_id": OWNER})


def make_client(settings, storage, store, slack, launcher, channel=CHANNEL):
    notifier = SlackNotifier(store, channel, slack if channel else None, log=lambda fields: None)
    return TestClient(create_app(settings, storage, store, form_filler=launcher, notifier=notifier))


@pytest.fixture
def api(slack_settings, storage, store, slack, launcher):
    return make_client(slack_settings, storage, store, slack, launcher)


def record(api, **changes):
    r = api.post("/application", headers=KEY, json={**VALID_APPLICATION, **changes})
    assert r.status_code in (200, 201), r.text
    return r.json()["application_id"]


def ready(api, letter=True):
    """An application with its documents generated, so its report is posted. Jobs run at once in tests, so the
    cover letter goes first: the report then waits for the resume and shows both."""
    app_id = record(api, full_job_description=LONG_POSTING)
    if letter:
        assert api.post("/cover-letter", headers=KEY, json={"application_id": app_id}).status_code == 202
    assert api.post("/resume", headers=KEY, json={"application_id": app_id}).status_code == 202
    return app_id


# --- formatting ---

def test_report_has_app_id_line_and_leaves_out_empty_fields():
    application = {**VALID_APPLICATION, "id": "0f6c0000-0000-4000-8000-000000000000", "salary": None,
                   "sponsorship": ""}
    text = format_report(application, {"resume": {"status": "done"}, "cover_letter": None},
                         {"base_score": 64, "tailored_score": 82})
    assert "*App ID:* `0f6c0000-0000-4000-8000-000000000000`" in text.splitlines()
    assert "*Match:* 64 → 82" in text
    assert "Salary" not in text and "Sponsorship" not in text
    assert "http://127.0.0.1:8081/viewer#0f6c0000-0000-4000-8000-000000000000" in text
    assert "resume ✓ · cover letter not generated" in text


def test_report_escapes_posting_text():
    application = {**VALID_APPLICATION, "id": "x", "why_it_fits": "<!channel> & <https://evil|click>"}
    text = format_report(application, {}, None)
    assert "<!channel>" not in text and "&lt;!channel&gt; &amp;" in text


def test_batch_lists_lettered_options_and_flags_approval():
    text = format_batch([{"question": "Submit Ramp?", "header": "Submit", "kind": "approval", "multi_select": False,
                          "options": [{"label": "Yes, agree and submit"}, {"label": "No, I'll do it myself"}]}])
    assert "*1. Submit Ramp?*" in text and "a) Yes, agree and submit" in text and "b) No, I'll do it myself" in text
    assert "approval" in text


def test_split_text_on_lines():
    text = "\n".join(["x" * 1000] * 5)
    parts = split_text(text, 3500)
    assert len(parts) == 2 and all(len(p) <= 3500 for p in parts) and "\n".join(parts) == text


def test_split_text_cuts_an_overlong_line():
    assert [len(p) for p in split_text("y" * 8000, 3500)] == [3500, 3500, 1000]


# --- ready report ---

def test_report_posted_once_when_both_documents_done(api, slack, store):
    app_id = ready(api)
    top = slack.top_level()
    assert len(top) == 1 and top[0]["channel"] == CHANNEL
    assert f"*App ID:* `{app_id}`" in top[0]["text"] and "resume ✓ · cover letter ✓" in top[0]["text"]
    assert store.get_slack_thread(app_id)["thread_ts"] == top[0]["ts"]


def test_cover_letter_after_report_is_a_reply(api, slack):
    app_id = ready(api, letter=False)
    api.post("/cover-letter", headers=KEY, json={"application_id": app_id})
    assert len(slack.top_level()) == 1 and "cover letter not generated" in slack.top_level()[0]["text"]
    assert slack.posts[-1]["text"] == "Cover letter generated ✓"
    assert slack.posts[-1]["thread_ts"] == slack.top_level()[0]["ts"]


def test_resume_only_application_gets_report(api, slack):
    ready(api, letter=False)
    assert len(slack.top_level()) == 1


def test_no_report_while_cover_letter_running(api, slack, store):
    app_id = record(api, full_job_description=LONG_POSTING)
    store.start_job(app_id, "cover_letter", "2026-11-08T00:00:00Z")
    api.post("/resume", headers=KEY, json={"application_id": app_id})
    assert slack.top_level() == []


def test_no_report_when_resume_failed(api, slack, monkeypatch):
    def boom(application, settings):
        raise RuntimeError("tectonic crashed")
    monkeypatch.setattr("app.main.generate_output", boom)
    app_id = record(api)
    api.post("/resume", headers=KEY, json={"application_id": app_id})
    assert slack.posts == []


def test_slack_failure_keeps_job_done_and_releases_claim(api, slack, store):
    slack.fail = True
    app_id = record(api)
    api.post("/resume", headers=KEY, json={"application_id": app_id})
    assert store.get_job(app_id, "resume")["status"] == "done"
    assert store.get_slack_thread(app_id) is None
    slack.fail = False
    r = api.post(f"/application/{app_id}/slack-report", headers=KEY)
    assert r.status_code == 200 and r.json()["already_posted"] is False and len(slack.top_level()) == 1


def test_concurrent_claims_post_one_report(store):
    app_id, _ = store.record(dict(VALID_APPLICATION))
    store.start_job(app_id, "resume", "s")
    store.finish_job(app_id, "resume", "s", "done")
    results = []
    barrier = threading.Barrier(8)

    def claim():
        barrier.wait()
        results.append(store.claim_slack_report(app_id, CHANNEL).state)
    threads = [threading.Thread(target=claim) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("claimed") == 1 and set(results) <= {"claimed", "in_progress"}


def test_regenerated_resume_is_a_thread_reply(api, slack):
    app_id = ready(api)
    api.post("/resume", headers=KEY, json={"application_id": app_id})
    assert len(slack.top_level()) == 1
    reply = slack.posts[-1]
    assert reply["thread_ts"] == slack.top_level()[0]["ts"] and reply["text"].startswith("Resume regenerated ✓")


def test_not_configured_posts_nothing_and_endpoints_503(settings, storage, store, slack, launcher):
    api = make_client(settings.model_copy(update={"api_docs_enabled": True}), storage, store, slack, launcher,
                      channel=None)
    app_id = ready(api)
    assert slack.posts == []
    r = api.post(f"/application/{app_id}/fill", headers=KEY)
    assert r.status_code == 503 and r.json()["reason"] == "slack_not_configured"


def test_manual_report_states(api, store):
    app_id = record(api)
    r = api.post(f"/application/{app_id}/slack-report", headers=KEY)
    assert r.status_code == 409 and r.json()["reason"] == "resume_not_ready"
    api.post("/resume", headers=KEY, json={"application_id": app_id})
    r = api.post(f"/application/{app_id}/slack-report", headers=KEY)
    assert r.status_code == 200 and r.json()["already_posted"] is True
    assert api.post("/application/00000000-0000-4000-8000-000000000000/slack-report", headers=KEY).status_code == 404
    assert api.post(f"/application/{app_id}/slack-report").status_code == 401


def test_deleting_an_application_drops_its_thread(api, store):
    app_id = ready(api)
    store.add_question_batch(app_id, [{"question": "q", "header": "h", "options": []}])
    assert api.delete(f"/application/{app_id}", headers=KEY).status_code == 200
    assert store.get_slack_thread(app_id) is None and store.pending_question_batch(app_id) is None


# --- fill from Slack ---

def test_fill_command_slack_mode_is_one_argument():
    assert fill_command("claude", "abc") == "claude --chrome '/job-application-form-filler abc'"
    assert fill_command("claude", "abc", "slack") == "claude --chrome '/job-application-form-filler abc slack'"
    with pytest.raises(ValueError):
        fill_command("claude", "abc", "submit")


def test_fill_from_slack(api, slack, launcher):
    app_id = ready(api)
    r = api.post(f"/application/{app_id}/fill", headers=KEY, json={"mode": "slack"})
    assert r.status_code == 200 and r.json()["already_open"] is False
    assert launcher.calls == [(VALID_APPLICATION["company"], VALID_APPLICATION["role"], app_id, "slack")]
    assert slack.posts[-1]["text"].startswith("Started filling the form")


def test_fill_empty_body_ok(api, launcher):
    app_id = ready(api)
    assert api.post(f"/application/{app_id}/fill", headers=KEY).status_code == 200


def test_fill_needs_a_thread(api, launcher):
    app_id = record(api)
    r = api.post(f"/application/{app_id}/fill", headers=KEY)
    assert r.status_code == 409 and r.json()["reason"] == "no_thread" and launcher.calls == []


def test_fill_herdr_unavailable(slack_settings, storage, store, slack):
    api = make_client(slack_settings, storage, store, slack, FakeLauncher(fail=True))
    app_id = ready(api)
    assert api.post(f"/application/{app_id}/fill", headers=KEY).status_code == 503


def test_fill_needs_key_and_known_id(api):
    assert api.post("/application/00000000-0000-4000-8000-000000000000/fill").status_code == 401
    assert api.post("/application/00000000-0000-4000-8000-000000000000/fill", headers=KEY).status_code == 404
    assert api.post("/application/not-a-uuid/fill", headers=KEY).status_code == 404


def test_slack_routes_not_on_public_app(slack_settings, storage, store, slack, launcher):
    api = make_client(slack_settings.model_copy(update={"api_docs_enabled": False}), storage, store, slack, launcher)
    app_id = ready(api)  # the public app still posts reports for jobs it runs
    assert len(slack.top_level()) == 1
    assert api.post(f"/application/{app_id}/fill", headers=KEY).status_code in (404, 405)


# --- questions and answers ---

QUESTION = {"question": "Ramp form: years of Python?", "header": "Python yrs",
            "options": [{"label": "5+", "description": "from your resume"}, {"label": "3-5"}]}
APPROVAL = {"question": "Tick the consent box on the Ramp form and submit?", "header": "Submit", "kind": "approval",
            "options": [{"label": "Yes, agree and submit"}, {"label": "No, I'll do it myself"}]}


def ask(api, app_id, *questions):
    r = api.post(f"/application/{app_id}/questions", headers=KEY, json={"questions": list(questions)})
    assert r.status_code == 201, r.text
    return r.json()["question_id"]


def test_question_round_trip(api, slack):
    app_id = ready(api)
    qid = ask(api, app_id, QUESTION, {**QUESTION, "question": "Ramp form: start date?", "header": "Start"})
    assert "*1. Ramp form: years of Python?*" in slack.posts[-1]["text"]
    pending = api.get(f"/application/{app_id}/questions", headers=KEY).json()["pending"]
    assert pending["question_id"] == qid and pending["status"] == "pending"
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["5+"], ["In two weeks"]]})
    assert r.status_code == 200
    state = api.get(f"/application/{app_id}/questions/{qid}", headers=KEY).json()
    assert state["status"] == "answered" and state["answers"] == [["5+"], ["In two weeks"]]
    assert api.get(f"/application/{app_id}/questions", headers=KEY).json()["pending"] is None


def test_newer_batch_supersedes(api):
    app_id = ready(api)
    first = ask(api, app_id, QUESTION)
    second = ask(api, app_id, QUESTION)
    assert api.get(f"/application/{app_id}/questions/{first}", headers=KEY).json()["status"] == "cancelled"
    assert api.get(f"/application/{app_id}/questions", headers=KEY).json()["pending"]["question_id"] == second


def test_answered_twice_conflicts(api):
    app_id = ready(api)
    qid = ask(api, app_id, QUESTION)
    api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY, json={"answers": [["5+"]]})
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY, json={"answers": [["3-5"]]})
    assert r.status_code == 409 and r.json()["reason"] == "not_pending"
    assert api.get(f"/application/{app_id}/questions/{qid}", headers=KEY).json()["answers"] == [["5+"]]


def test_answer_count_must_match(api):
    app_id = ready(api)
    qid = ask(api, app_id, QUESTION)
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY, json={"answers": [["5+"], ["x"]]})
    assert r.status_code == 422 and r.json()["reason"] == "answer_count"


@pytest.mark.parametrize("batch", [
    {"questions": [QUESTION] * 5},
    {"questions": [{**QUESTION, "options": [{"label": "only"}]}]},
    {"questions": [{**QUESTION, "header": "much too long header"}]},
    {"questions": []},
])
def test_invalid_batch_posts_nothing(api, slack, batch):
    app_id = ready(api)
    before = len(slack.posts)
    assert api.post(f"/application/{app_id}/questions", headers=KEY, json=batch).status_code == 422
    assert len(slack.posts) == before


def test_cancel_batch(api):
    app_id = ready(api)
    qid = ask(api, app_id, QUESTION)
    assert api.delete(f"/application/{app_id}/questions/{qid}", headers=KEY).json()["status"] == "cancelled"
    assert api.delete(f"/application/{app_id}/questions/{qid}", headers=KEY).status_code == 409


def test_batch_of_another_application_not_found(api):
    other = "https://jobs.lever.co/acme/other"
    first, second = ready(api), record(api, job_link=other, official_apply_url=other)
    qid = ask(api, first, QUESTION)
    assert api.get(f"/application/{second}/questions/{qid}", headers=KEY).status_code == 404


def test_questions_and_answers_never_logged(api, caplog):
    app_id = ready(api)
    with caplog.at_level("INFO", logger="app.requests"):
        qid = ask(api, app_id, {**QUESTION, "question": "SECRET-QUESTION?"})
        api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY, json={"answers": [["SECRET-ANSWER"]]})
    assert "SECRET" not in caplog.text


# --- verified approval ---

def test_owner_approval_accepted(api, slack):
    app_id = ready(api)
    qid = ask(api, app_id, APPROVAL)
    ts = slack.owner_reply("yes, submit it")
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["Yes, agree and submit"]], "slack_message_ts": ts})
    assert r.status_code == 200


def test_owner_decline_accepted(api, slack):
    app_id = ready(api)
    qid = ask(api, app_id, APPROVAL)
    ts = slack.owner_reply("nope, I'll do it")
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["No, I'll do it myself"]], "slack_message_ts": ts})
    assert r.status_code == 200


@pytest.mark.parametrize("case", ["no_reply", "unknown_ts", "bot", "other_user", "older", "not_yes"])
def test_approval_not_verified(api, slack, case):
    app_id = ready(api)
    older = slack.owner_reply("yes")  # before the question
    qid = ask(api, app_id, APPROVAL)
    ts = {"no_reply": None, "unknown_ts": "1.000000", "older": older,
          "bot": slack.owner_reply("yes, approve", bot=True) if case == "bot" else None,
          "other_user": slack.owner_reply("yes", user="U0SOMEONE") if case == "other_user" else None,
          "not_yes": slack.owner_reply("hmm let me think") if case == "not_yes" else None}[case]
    body = {"answers": [["Yes, agree and submit"]]}
    if ts is not None:
        body["slack_message_ts"] = ts
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY, json=body)
    assert r.status_code == 422 and r.json()["reason"] == "approval_not_verified"
    assert api.get(f"/application/{app_id}/questions/{qid}", headers=KEY).json()["status"] == "pending"


def test_approval_without_ts_uses_latest_owner_reply(api, slack):
    app_id = ready(api)
    qid = ask(api, app_id, APPROVAL)
    slack.owner_reply("hmm wait")
    slack.owner_reply("yes, approve", bot=True)  # a bot saying yes never counts
    slack.owner_reply("yes go ahead")
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["Yes, agree and submit"]]})
    assert r.status_code == 200


def test_approval_without_ts_rejected_when_latest_owner_reply_hesitates(api, slack):
    app_id = ready(api)
    qid = ask(api, app_id, APPROVAL)
    slack.owner_reply("yes")
    slack.owner_reply("actually wait, hold on")
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["Yes, agree and submit"]]})
    assert r.status_code == 422


def test_approval_needs_owner_configured(slack_settings, storage, store, slack, launcher):
    api = make_client(slack_settings.model_copy(update={"slack_owner_user_id": None}), storage, store, slack, launcher)
    app_id = ready(api)
    qid = ask(api, app_id, APPROVAL)
    ts = slack.owner_reply("yes")
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["Yes, agree and submit"]], "slack_message_ts": ts})
    assert r.status_code == 503


def test_approval_slack_unreadable(api, slack):
    app_id = ready(api)
    qid = ask(api, app_id, APPROVAL)
    ts = slack.owner_reply("yes")
    slack.read_fail = True
    r = api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY,
                 json={"answers": [["Yes, agree and submit"]], "slack_message_ts": ts})
    assert r.status_code == 502


def test_approval_verified_label_match():
    messages = [{"ts": "5.0", "user": OWNER, "text": "go with Submit, but leave the boxes to me"}]
    assert approval_verified(messages, "5.0", OWNER, "4.0", ["Submit, but leave the boxes to me"])
    assert not approval_verified(messages, "5.0", OWNER, None, ["Yes"])


# --- updates ---

def test_slack_update_split(api, slack):
    app_id = ready(api)
    text = "\n".join(["line " + "z" * 995] * 5)
    r = api.post(f"/application/{app_id}/slack-update", headers=KEY, json={"text": text})
    assert r.status_code == 200 and r.json()["messages"] == 2
    assert all(p["thread_ts"] == slack.top_level()[0]["ts"] for p in slack.posts[-2:])


def test_slack_update_needs_thread(api):
    app_id = record(api)
    r = api.post(f"/application/{app_id}/slack-update", headers=KEY, json={"text": "hi"})
    assert r.status_code == 409 and r.json()["reason"] == "no_thread"


# --- the real client against a fake Slack server ---

@pytest.fixture
def fake_slack_server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.path, self.headers.get("Authorization"), self.headers.get("Content-Type"), body))
            if self.path.endswith("chat.postMessage"):
                payload = json.loads(body)
                reply = ({"ok": False, "error": "not_in_channel"} if payload["channel"] == "C0BAD"
                         else {"ok": True, "ts": "1762570001.000100"})
            else:
                form = parse_qs(body.decode())
                reply = {"ok": True, "messages": [{"ts": form["ts"][0], "text": "root"}],
                         "response_metadata": {"next_cursor": ""}}
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/api", calls
    server.shutdown()


def test_client_posts_and_reads(fake_slack_server):
    base, calls = fake_slack_server
    client = SlackClient("xoxb-secret", base)
    assert client.post_message("C0JOBS", "hello", thread_ts="1.0") == "1762570001.000100"
    assert client.thread_replies("C0JOBS", "1.0")[0]["text"] == "root"
    path, auth, ctype, body = calls[0]
    assert path == "/api/chat.postMessage" and auth == "Bearer xoxb-secret" and ctype.startswith("application/json")
    assert json.loads(body)["thread_ts"] == "1.0"


def test_client_error_hides_token_and_text(fake_slack_server):
    base, _ = fake_slack_server
    with pytest.raises(SlackError) as caught:
        SlackClient("xoxb-secret", base).post_message("C0BAD", "private text")
    assert str(caught.value) == "chat.postMessage: not_in_channel"


def test_client_unreachable():
    with pytest.raises(SlackError) as caught:
        SlackClient("xoxb-secret", "http://127.0.0.1:1/api", timeout=2).post_message("C", "t")
    assert "xoxb" not in str(caught.value)


# --- scripts/ask_slack.py, routed into the test app ---

@pytest.fixture
def ask_slack(api, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "ask_slack", Path(__file__).resolve().parent.parent / "scripts" / "ask_slack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def call(method, path, body=None):
        r = api.request(method, path, headers=KEY, json=body)
        return r.status_code, r.json()
    monkeypatch.setattr(module, "call", call)
    monkeypatch.setattr(module, "POLL_SECONDS", 0)
    return module


def test_ask_slack_post_wait_answer(api, ask_slack, tmp_path, capsys):
    app_id = ready(api)
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"questions": [QUESTION]}))
    assert ask_slack.main(["post", app_id, str(batch)]) == 0
    qid = capsys.readouterr().out.strip()
    assert ask_slack.main(["wait", app_id, qid, "--timeout", "0"]) == 3
    assert capsys.readouterr().out.strip() == "pending"
    api.post(f"/application/{app_id}/questions/{qid}/answers", headers=KEY, json={"answers": [["5+"]]})
    assert ask_slack.main(["wait", app_id, qid]) == 0
    assert json.loads(capsys.readouterr().out) == {"answers": [["5+"]]}


def test_ask_slack_cancel_and_superseded(api, ask_slack, tmp_path, capsys):
    app_id = ready(api)
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"questions": [QUESTION]}))
    ask_slack.main(["post", app_id, str(batch)])
    first = capsys.readouterr().out.strip()
    ask_slack.main(["post", app_id, str(batch)])
    second = capsys.readouterr().out.strip()
    assert ask_slack.main(["wait", app_id, first]) == 4
    assert ask_slack.main(["cancel", app_id, second]) == 0
    assert ask_slack.main(["wait", app_id, second]) == 4


def test_ask_slack_post_error(api, ask_slack, tmp_path, capsys):
    app_id = record(api)  # no thread yet
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"questions": [QUESTION]}))
    assert ask_slack.main(["post", app_id, str(batch)]) == 1
    assert "no_thread" in capsys.readouterr().err
