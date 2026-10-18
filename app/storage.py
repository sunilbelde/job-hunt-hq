import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Protocol

RESUME_FILE_NAME = "SUNIL BELDE.pdf"
TMP_PREFIX = ".tmp-"
MAX_FOLDER_CHARS = 100
UNKNOWN_COMPANY = "unknown-company"
# The application store and its -wal/-journal/-shm siblings live in OUTPUT_DIR next to the company folders.
STORE_FILE_PREFIX = "applications.sqlite3"
PATH_BREAKING = frozenset("/\\:")


class StorageError(Exception):
    """Raised when a file cannot be written to the output directory."""


class Storage(Protocol):
    def save_resume(self, company: str, application_id: int, content: bytes) -> Path:
        """Write the resume for an application, replacing any earlier one, and return its absolute path."""
        ...


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
    """Saves resumes under a local directory that only the service user can read."""

    def __init__(self, root: Path):
        self._root = Path(root)
        try:
            self._root.mkdir(parents=True, mode=0o700, exist_ok=True)
            with tempfile.TemporaryFile(dir=self._root):
                pass
        except OSError as exc:
            raise StorageError(f"OUTPUT_DIR {self._root} is not writable: {exc}") from exc

    def save_resume(self, company: str, application_id: int, content: bytes) -> Path:
        root = self._root.resolve()
        folder = root / company_folder(company) / str(application_id)
        if not folder.resolve().is_relative_to(root):  # company_folder already rules this out
            raise StorageError("resume path escapes OUTPUT_DIR")
        path = folder / RESUME_FILE_NAME
        tmp_name = None
        try:
            folder.parent.mkdir(mode=0o700, exist_ok=True)
            folder.mkdir(mode=0o700, exist_ok=True)
            # mkstemp creates the file 0600; the rename replaces any earlier resume in one step.
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
