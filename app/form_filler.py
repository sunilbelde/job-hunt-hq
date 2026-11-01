"""Opens a Herdr tab running Claude Code with the job-application-form-filler skill for one application.

The viewer's Fill form button calls this. The tab is opened in the Herdr workspace named by
FILL_WORKSPACE (created if missing), labelled "<Company>-<Role>-<application id>", in the repo, and runs
`claude --chrome "/job-application-form-filler <id>"` there as an ordinary interactive session: the owner
watches it, approves its permissions and answers its questions. Nothing typed on a page reaches the
command: the only variable part is the application ID, which the caller has already parsed as a UUID.
"""

import json
import logging
import shlex
import subprocess
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger("app")

REPO_DIR = Path(__file__).resolve().parents[1]
SKILL = "job-application-form-filler"
HERDR_TIMEOUT_SECONDS = 15
LABEL_PART_LIMIT = 60


class HerdrUnavailable(Exception):
    """Herdr could not be run, or answered with an error or with JSON this module does not understand."""


@dataclass(frozen=True)
class FillStarted:
    tab_id: str
    tab_label: str
    workspace_id: str
    already_open: bool


Runner = Callable[[list[str]], str]


def run_herdr(herdr_bin: str) -> Runner:
    def run(args: list[str]) -> str:
        try:
            done = subprocess.run([herdr_bin, *args], capture_output=True, text=True, timeout=HERDR_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as exc:
            raise HerdrUnavailable(f"herdr {args[0]} {args[1]}: {type(exc).__name__}") from exc
        if done.returncode != 0:
            raise HerdrUnavailable(f"herdr {args[0]} {args[1]} exited {done.returncode}")
        return done.stdout
    return run


def label_part(text: str) -> str:
    """One part of the tab label: control characters dropped, whitespace collapsed, length capped."""
    kept = "".join(" " if c.isspace() else c for c in text if unicodedata.category(c)[0] != "C" or c.isspace())
    return " ".join(kept.split())[:LABEL_PART_LIMIT].strip()


def tab_label(company: str, role: str, application_id: str) -> str:
    return "-".join(part for part in (label_part(company), label_part(role), application_id) if part)


def fill_command(claude_bin: str, application_id: str) -> str:
    return f"{shlex.quote(claude_bin)} --chrome {shlex.quote(f'/{SKILL} {application_id}')}"


class FormFillLauncher:
    def __init__(self, herdr_bin: str, claude_bin: str, workspace_label: str, cwd: Path = REPO_DIR,
                 runner: Runner | None = None):
        self.claude_bin = claude_bin
        self.workspace_label = workspace_label
        self.cwd = cwd
        self.run = runner or run_herdr(herdr_bin)
        # One start at a time, so a double click cannot open two tabs for one application.
        self.lock = threading.Lock()

    def call(self, *args: str) -> dict:
        try:
            reply = json.loads(self.run(list(args)))
            return reply["result"]
        except (ValueError, KeyError, TypeError) as exc:
            raise HerdrUnavailable(f"herdr {args[0]} {args[1]}: unexpected reply") from exc

    def workspace(self) -> tuple[str, dict | None]:
        """The workspace's ID, creating it when missing; for a new one also its first tab and pane."""
        for workspace in self.call("workspace", "list")["workspaces"]:
            if workspace.get("label") == self.workspace_label:
                return workspace["workspace_id"], None
        created = self.call("workspace", "create", "--cwd", str(self.cwd), "--label", self.workspace_label,
                            "--no-focus")
        return created["workspace"]["workspace_id"], created

    def start(self, company: str, role: str, application_id: str) -> FillStarted:
        with self.lock:
            try:
                return self._start(company, role, application_id)
            except (KeyError, TypeError, AttributeError) as exc:
                # A reply without the fields this module reads: a Herdr version it does not understand.
                raise HerdrUnavailable(f"unexpected herdr reply: {type(exc).__name__}") from exc

    def _start(self, company: str, role: str, application_id: str) -> FillStarted:
        label = tab_label(company, role, application_id)
        workspace_id, created = self.workspace()
        if created is None:
            for tab in self.call("tab", "list", "--workspace", workspace_id)["tabs"]:
                # Matched by ID, so a company or role renamed since still finds the open session.
                if str(tab.get("label", "")).endswith(application_id):
                    return FillStarted(tab["tab_id"], tab["label"], workspace_id, already_open=True)
            created = self.call("tab", "create", "--workspace", workspace_id, "--cwd", str(self.cwd),
                                "--label", label, "--no-focus")
        else:
            self.call("tab", "rename", created["tab"]["tab_id"], label)
        tab_id, pane_id = created["tab"]["tab_id"], created["root_pane"]["pane_id"]
        # `pane run` prints nothing on success; its exit status is the answer.
        self.run(["pane", "run", pane_id, fill_command(self.claude_bin, application_id)])
        return FillStarted(tab_id, label, workspace_id, already_open=False)
