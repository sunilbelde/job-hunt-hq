#!/usr/bin/env python3
"""Ask the owner questions in an application's Slack thread, for the form filler's Slack mode.

    ask_slack.py post <application id> <batch.json | ->     prints the question ID
    ask_slack.py wait <application id> <question id> [--timeout SECONDS]
    ask_slack.py cancel <application id> <question id>

The batch is what AskUserQuestion would have been given: {"questions": [{question, header, options: [{label,
description}], multi_select, kind}]}, with kind "approval" for the agree-and-submit and mark-applied questions.

wait polls the local service every 5 seconds and exits:
    0  answered: prints {"answers": [[...], ...]} (per question, the chosen labels or the owner's own words)
    3  still pending after the timeout (default 540 s): call wait again with the same IDs
    4  cancelled: a newer batch replaced it, or it was cancelled
    1  error (printed to stderr)

Reads API_KEY from the repo's .env and never prints it. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8081"
REPO = Path(__file__).resolve().parents[1]
POLL_SECONDS = 5


def api_key() -> str:
    try:
        for line in (REPO / ".env").read_text().splitlines():
            if line.startswith("API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    sys.exit("error: no API_KEY in the repo's .env")


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                     headers={"X-API-Key": api_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except ValueError:
            return exc.code, {"message": f"HTTP {exc.code}"}
    except (urllib.error.URLError, OSError) as exc:
        return 0, {"message": f"service unreachable: {type(exc).__name__}"}


def post(application_id: str, source: str) -> int:
    text = sys.stdin.read() if source == "-" else Path(source).read_text()
    try:
        batch = json.loads(text)
    except ValueError:
        print("error: the batch is not valid JSON", file=sys.stderr)
        return 1
    status, reply = call("POST", f"/application/{application_id}/questions", batch)
    if status != 201:
        print(f"error: {status} {reply.get('reason', '')} {reply.get('message', '')}".strip(), file=sys.stderr)
        return 1
    print(reply["question_id"])
    return 0


def wait(application_id: str, question_id: str, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    failures = 0
    while True:
        status, reply = call("GET", f"/application/{application_id}/questions/{question_id}")
        if status == 200:
            failures = 0
            if reply["status"] == "answered":
                print(json.dumps({"answers": reply["answers"]}))
                return 0
            if reply["status"] == "cancelled":
                print("cancelled")
                return 4
        elif status in (401, 404):
            print(f"error: {status} {reply.get('message', '')}", file=sys.stderr)
            return 1
        else:
            failures += 1  # the service restarting, or Slack settings changing: keep waiting a while
            if failures >= 12:
                print(f"error: {status} {reply.get('message', '')}", file=sys.stderr)
                return 1
        if time.monotonic() >= deadline:
            print("pending")
            return 3
        time.sleep(POLL_SECONDS)


def cancel(application_id: str, question_id: str) -> int:
    status, reply = call("DELETE", f"/application/{application_id}/questions/{question_id}")
    if status == 200 or reply.get("reason") == "not_pending":
        print("cancelled" if status == 200 else "not pending")
        return 0
    print(f"error: {status} {reply.get('message', '')}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("post")
    p.add_argument("application_id")
    p.add_argument("batch", help="a JSON file, or - for stdin")
    w = sub.add_parser("wait")
    w.add_argument("application_id")
    w.add_argument("question_id")
    w.add_argument("--timeout", type=float, default=540)
    c = sub.add_parser("cancel")
    c.add_argument("application_id")
    c.add_argument("question_id")
    args = parser.parse_args(argv)
    if args.command == "post":
        return post(args.application_id, args.batch)
    if args.command == "wait":
        return wait(args.application_id, args.question_id, args.timeout)
    return cancel(args.application_id, args.question_id)


if __name__ == "__main__":
    sys.exit(main())
