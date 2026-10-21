import os
import shutil
import subprocess
from pathlib import Path

from tests.conftest import SKILL_DIR

LAUNCHER = SKILL_DIR / "scripts" / "run"


def fake_python(path: Path, log: Path) -> Path:
    """An 'interpreter' that records how it was called instead of running anything."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\nprintf "%s\\n" "$0" "$@" > "{log}"\n')
    path.chmod(0o755)
    return path


def run_launcher(launcher: Path, *args: str, tailor_python: Path | None = None):
    env = {k: v for k, v in os.environ.items() if k != "TAILOR_PYTHON"}
    if tailor_python is not None:
        env["TAILOR_PYTHON"] = str(tailor_python)
    return subprocess.run([str(launcher), *args], env=env, capture_output=True, text=True, timeout=10)


def test_launcher_is_executable():
    assert os.access(LAUNCHER, os.X_OK)


def test_uses_tailor_python_when_set(tmp_path):
    log = tmp_path / "argv"
    # The service's interpreter lives under "claude Projects", so the path has a space.
    interpreter = fake_python(tmp_path / "with space" / "python", log)
    assert run_launcher(LAUNCHER, "build", "--flag", tailor_python=interpreter).returncode == 0
    assert log.read_text().splitlines() == [str(interpreter), str(LAUNCHER.parent / "resume_tool.py"), "build", "--flag"]


def test_falls_back_to_the_repo_venv(tmp_path):
    repo = tmp_path / "repo with space"
    launcher = repo / ".claude" / "skills" / "tailor-resume" / "scripts" / "run"
    launcher.parent.mkdir(parents=True)
    shutil.copy2(LAUNCHER, launcher)
    log = tmp_path / "argv"
    venv_python = fake_python(repo / ".venv" / "bin" / "python", log)
    assert run_launcher(launcher, "score", "base").returncode == 0
    called, *args = log.read_text().splitlines()
    assert Path(called).resolve() == venv_python.resolve()
    assert args == [str(launcher.parent / "resume_tool.py"), "score", "base"]
