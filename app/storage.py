import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

logger = logging.getLogger("app.storage")

KEY_RE = re.compile(r"outputs/\d{4}-\d{2}-\d{2}/[0-9a-f-]{36}\.[a-z0-9]{1,8}")
TMP_PREFIX = ".tmp-"
STALE_TMP_SECONDS = 3600
CONTENT_TYPES = {"pdf": "application/pdf"}


class StorageError(Exception):
    """Raised when storing a file or signing its link fails."""


class Storage(Protocol):
    def upload(self, content: bytes, content_type: str, extension: str) -> str:
        """Store the content and return its key."""
        ...

    def presigned_url(self, key: str, ttl_seconds: int) -> str:
        """Return a time-limited GET URL for the key."""
        ...

    def verify_link(self, key: str, expires: str | None, sig: str | None) -> bool:
        """True if the link parameters are a valid, unexpired signature for the key."""
        ...

    def path_for(self, key: str) -> Path:
        """Return the stored file's path; raise ValueError for an invalid key."""
        ...

    def cleanup(self, max_age_seconds: float) -> int:
        """Delete files older than max_age_seconds and return how many were deleted."""
        ...


def build_key(extension: str, now: datetime | None = None) -> str:
    day = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return f"outputs/{day}/{uuid.uuid4()}.{extension}"


def is_valid_key(key: str) -> bool:
    """True only for keys in the exact format build_key produces, so no traversal is possible."""
    return KEY_RE.fullmatch(key) is not None


def content_type_for(key: str) -> str:
    extension = key.rsplit(".", 1)[-1]
    return CONTENT_TYPES.get(extension) or mimetypes.guess_type(key)[0] or "application/octet-stream"


class LinkSigner:
    """Signs and verifies expiring download links with HMAC-SHA256. Stateless, so links survive restarts."""

    def __init__(self, secret: str, base_url: str):
        self._secret = secret.encode()
        self._base_url = base_url.rstrip("/")

    def _signature(self, key: str, expires: int) -> str:
        return hmac.new(self._secret, f"{key}\n{expires}".encode(), hashlib.sha256).hexdigest()

    def url(self, key: str, ttl_seconds: int, now: float | None = None) -> str:
        expires = int(now if now is not None else time.time()) + ttl_seconds
        return (
            f"{self._base_url}/files/{quote(key, safe='/')}"
            f"?expires={expires}&sig={self._signature(key, expires)}"
        )

    def verify(self, key: str, expires: str | None, sig: str | None, now: float | None = None) -> bool:
        if not expires or not sig or not expires.isdigit():
            return False
        expected = self._signature(key, int(expires))
        if not hmac.compare_digest(sig.encode(), expected.encode()):
            return False
        return int(expires) > (now if now is not None else time.time())


class LocalStorage:
    """Stores files under a local directory that only the service user can read."""

    def __init__(self, root: Path, signer: LinkSigner):
        self._root = Path(root)
        self._signer = signer
        try:
            self._root.mkdir(parents=True, mode=0o700, exist_ok=True)
            (self._root / "outputs").mkdir(mode=0o700, exist_ok=True)
            with tempfile.TemporaryFile(dir=self._root / "outputs"):
                pass
        except OSError as exc:
            raise StorageError(f"OUTPUT_DIR {self._root} is not writable: {exc}") from exc

    def upload(self, content: bytes, content_type: str, extension: str) -> str:
        key = build_key(extension)
        path = self._root / key
        tmp_name = None
        try:
            path.parent.mkdir(mode=0o700, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=TMP_PREFIX, dir=path.parent)
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except OSError as exc:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)
            raise StorageError(f"write failed: {type(exc).__name__}: {exc}") from exc
        return key

    def presigned_url(self, key: str, ttl_seconds: int) -> str:
        return self._signer.url(key, ttl_seconds)

    def verify_link(self, key: str, expires: str | None, sig: str | None) -> bool:
        return self._signer.verify(key, expires, sig)

    def path_for(self, key: str) -> Path:
        """Path of a stored file. Raises ValueError for any key outside the output tree."""
        if not is_valid_key(key):
            raise ValueError("invalid key")
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ValueError("invalid key")
        return path

    def cleanup(self, max_age_seconds: float, now: float | None = None) -> int:
        """Delete files older than max_age_seconds, stale temp files and empty date dirs."""
        now = now if now is not None else time.time()
        deleted = 0
        outputs = self._root / "outputs"
        if not outputs.is_dir():
            return 0
        for day_dir in outputs.iterdir():
            if not day_dir.is_dir():
                continue
            for path in day_dir.iterdir():
                limit = STALE_TMP_SECONDS if path.name.startswith(TMP_PREFIX) else max_age_seconds
                try:
                    if path.is_file() and now - path.stat().st_mtime > limit:
                        path.unlink()
                        deleted += 1
                except OSError as exc:
                    logger.warning(json.dumps({"event": "cleanup_error", "path": str(path), "error": str(exc)}))
            try:
                if not any(day_dir.iterdir()):
                    day_dir.rmdir()
            except OSError as exc:
                logger.warning(json.dumps({"event": "cleanup_error", "path": str(day_dir), "error": str(exc)}))
        return deleted
