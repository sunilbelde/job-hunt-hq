"""Runs the write-cover-letter skill headlessly for one application and returns the checked letter.

The service prepares a throwaway work folder holding the skill (and the tailor-resume skill, whose modules
its scripts import), the posting and the owner's record, and runs `claude -p "/write-cover-letter ."` in it
with the same isolation and limits as resume tailoring (app/tailoring.py). One run lists the posting's
keywords and requirements and writes the letter. Then the repo's own copy of the skill script (`verify`)
re-checks it against the service's own template, profile, posting and job, and renders the PDF and the
text that get saved and returned.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app import tailoring
from app.models import StoredApplication
from app.rendering import TEMPLATE_DIR
from app.settings import Settings
from app.tailoring import MAX_POSTING_CHARS, MIN_POSTING_WORDS, RunStats, TailoringError

LETTER_SKILL_DIR = tailoring.SKILL_DIR.parent / "write-cover-letter"
LETTER_TOOL = LETTER_SKILL_DIR / "scripts" / "letter_tool.py"
LETTER_MAX_TURNS = 30  # fewer build cycles than a resume
PREPARE_TIMEOUT = 60
VERIFY_TIMEOUT = 120


@dataclass(frozen=True)
class LetterResult:
    pdf: bytes
    text: str
    run: RunStats


def posting_usable(text: str | None) -> bool:
    """Whether a letter can be tailored to the posting. Unlike resumes there is no unscored fallback, so a
    posting too long to hand to Claude is unusable too, not an error."""
    return text is not None and len(text) <= MAX_POSTING_CHARS and len(text.split()) >= MIN_POSTING_WORDS


def _prepare(application: StoredApplication, gate: Path) -> Path:
    """The run's work folder, and the service's own posting.md and job.json in `gate` for the final check."""
    (gate / "posting.md").write_text(tailoring.posting_markdown(application), encoding="utf-8")
    (gate / "job.json").write_text(json.dumps({"company": application.company, "role": application.role}),
                                   encoding="utf-8")
    work = Path(tempfile.mkdtemp(prefix="letter-")).resolve()  # mode 700, system temp, so no spaces in the path
    try:
        tailoring.copy_skills(work, LETTER_SKILL_DIR, tailoring.SKILL_DIR)
        (work / ".tmp").mkdir()
        cmd = [sys.executable, str(LETTER_TOOL), "prepare", "--template", str(TEMPLATE_DIR), "--out", str(work),
               "--profile", str(tailoring.PROFILE), "--posting", str(gate / "posting.md"),
               "--company", application.company, "--role", application.role]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=PREPARE_TIMEOUT)
        if result.returncode == tailoring.PROFILE_INVALID_EXIT:
            raise TailoringError("prepare", "profile_invalid", exit_code=result.returncode)
        if result.returncode != 0:
            raise TailoringError("prepare", "prepare_failed", exit_code=result.returncode)
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise TailoringError("prepare", "prepare_failed") from exc
    except TailoringError:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return work


def _verify(work: Path, gate: Path, stats: RunStats) -> dict:
    """The final gate: the repo's own script, against a snapshot of the run's analysis and the service's own
    template, profile, posting and job."""
    analysis = work / "out" / "analysis.json"
    if analysis.is_file() and not analysis.is_symlink():
        shutil.copyfile(analysis, gate / "analysis.json")
    verdict = tailoring._tool(
        ["verify", "--template", TEMPLATE_DIR, "--work", work, "--profile", tailoring.PROFILE,
         "--posting", gate / "posting.md", "--job", gate / "job.json", "--analysis", gate / "analysis.json",
         "--pdf-out", gate / "letter.pdf", "--text-out", gate / "letter.txt"],
        VERIFY_TIMEOUT, tool=LETTER_TOOL)
    if verdict is None:
        raise TailoringError("verify", "verify_error", run=stats)
    if not verdict.get("ok"):
        raise TailoringError("verify", tailoring.VERIFY_REASONS.get(verdict.get("stage"), "verify_error"),
                             failed_checks=verdict.get("failed", []), run=stats)
    return verdict


def run(application: StoredApplication, settings: Settings) -> LetterResult:
    """Write and check the cover letter for an application with usable posting text.

    One Claude run, under the same time limit and spend cap as a resume. Raises TailoringError when
    anything fails; the caller then saves nothing.
    """
    cred, binary = tailoring._ready(settings)
    runs = tailoring._Runs(settings, binary, cred)
    gate = Path(tempfile.mkdtemp(prefix="letter-gate-"))
    work = None
    try:
        work = _prepare(application, gate)
        runs.run("letter", work, lambda usd: tailoring.skill_command(
            settings, binary, work, LETTER_SKILL_DIR.name, LETTER_MAX_TURNS, usd))
        _verify(work, gate, runs.stats)
        return LetterResult((gate / "letter.pdf").read_bytes(), (gate / "letter.txt").read_text(encoding="utf-8"),
                            runs.stats)
    finally:
        for folder in (work, gate):
            if folder is not None:
                shutil.rmtree(folder, ignore_errors=True)
