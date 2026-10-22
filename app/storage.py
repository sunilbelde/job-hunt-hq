import json
import logging
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Protocol

RESUME_FILE_NAME = "SUNIL BELDE.pdf"
COVER_LETTER_FILE_NAME = "SUNIL BELDE - Cover Letter.pdf"
TMP_PREFIX = ".tmp-"
MAX_FOLDER_CHARS = 100
UNKNOWN_COMPANY = "unknown-company"
# The application store and its -wal/-journal/-shm siblings live in OUTPUT_DIR next to the company folders.
STORE_FILE_PREFIX = "applications.sqlite3"
PATH_BREAKING = frozenset("/\\:")
# How application folders were named before IDs became UUIDs.
LEGACY_FOLDER = re.compile(r"[1-9][0-9]*")

logger = logging.getLogger("app.storage")


class StorageError(Exception):
    """Raised when a file cannot be written to the output directory."""


class Storage(Protocol):
    def save_resume(self, company: str, application_id: str, content: bytes) -> Path:
        """Write the resume for an application, replacing any earlier one, and return its absolute path."""
        ...

    def save_cover_letter(self, company: str, application_id: str, content: bytes) -> Path:
        """Write the cover letter for an application, replacing any earlier one, and return its absolute path."""
        ...


def resume_path(root: Path, company: str, application_id: str) -> Path:
    """Where an application's resume is saved for its company as it is now."""
    return Path(root) / company_folder(company) / str(application_id) / RESUME_FILE_NAME


def cover_letter_path(root: Path, company: str, application_id: str) -> Path:
    """Where an application's cover letter is saved: the folder its resume uses, whether or not that exists."""
    return Path(root) / company_folder(company) / str(application_id) / COVER_LETTER_FILE_NAME


def company_folder(company: str) -> str:
    """The folder name for a company: readable in Finder, but never a path separator, '..' or the store file."""
    name = "".join(
        "-" if c in PATH_BREAKING or unicodedata.category(c) == "Cc" else c for c in company
    )
    name = name.strip(" .")[:MAX_FOLDER_CHARS].strip(" .")
    if not name:
        return UNKNOWN_COMPANY
    if name.lower().startswith(STORE_FILE_PREFIX):
        return "_" + name
    return name


class LocalStorage:
    """Saves resumes and cover letters under a local directory that only the service user can read."""

    def __init__(self, root: Path):
        self._root = Path(root)
        try:
            self._root.mkdir(parents=True, mode=0o700, exist_ok=True)
            with tempfile.TemporaryFile(dir=self._root):
                pass
        except OSError as exc:
            raise StorageError(f"OUTPUT_DIR {self._root} is not writable: {exc}") from exc

    def save_resume(self, company: str, application_id: str, content: bytes) -> Path:
        root = self._root.resolve()
        return self._write(root, resume_path(root, company, application_id), content)

    def save_cover_letter(self, company: str, application_id: str, content: bytes) -> Path:
        root = self._root.resolve()
        return self._write(root, cover_letter_path(root, company, application_id), content)

    @staticmethod
    def _write(root: Path, path: Path, content: bytes) -> Path:
        folder = path.parent
        if not folder.resolve().is_relative_to(root):  # company_folder already rules this out
            raise StorageError("output path escapes OUTPUT_DIR")
        tmp_name = None
        try:
            folder.parent.mkdir(mode=0o700, exist_ok=True)
            folder.mkdir(mode=0o700, exist_ok=True)
            # mkstemp creates the file 0600; the rename replaces any earlier file in one step.
            fd, tmp_name = tempfile.mkstemp(prefix=TMP_PREFIX, dir=folder)
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except OSError as exc:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)
            raise StorageError(f"write failed: {type(exc).__name__}: {exc}") from exc
        return path


def rename_legacy_folders(root: Path, mapping: dict[int, str]) -> int:
    """Rename application folders still named by an integer ID to the UUID that replaced it.

    Runs at every start while the store remembers integer IDs, so an interrupted run finishes
    later. Conflicts and errors are logged, never raised: the API does not need old folders.
    Returns how many folders were renamed.
    """
    if not mapping:
        return 0
    renamed = 0
    try:
        companies = [p for p in Path(root).iterdir() if p.is_dir() and not p.is_symlink()]
    except OSError as exc:
        _log_rename_error(root, exc)
        return 0
    for company in companies:
        try:
            folders = list(company.iterdir())
        except OSError as exc:
            _log_rename_error(company, exc)
            continue
        for folder in folders:
            if not LEGACY_FOLDER.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir():
                continue
            new_id = mapping.get(int(folder.name))
            if new_id is None:
                continue
            target = company / new_id
            # os.rename would silently replace an empty target folder, so check first.
            if target.exists() or target.is_symlink():
                logger.warning(json.dumps(
                    {"event": "legacy_folder_conflict", "folder": str(folder), "target": str(target)}))
                continue
            try:
                os.rename(folder, target)
            except OSError as exc:
                _log_rename_error(folder, exc)
                continue
            renamed += 1
            logger.info(json.dumps({"event": "legacy_folder_renamed", "folder": str(folder), "target": str(target)}))
    return renamed


def _log_rename_error(path: Path, exc: OSError) -> None:
    logger.error(json.dumps({"event": "legacy_folder_error", "path": str(path), "error": f"{type(exc).__name__}: {exc}"}))
