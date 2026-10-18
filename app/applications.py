import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.storage import StorageError

# Query parameters that only say where a click came from. Anything else stays in the
# dedupe key: some job boards carry the job ID itself in the query (gh_jid, token, jobId).
TRACKING_PARAMS = frozenset({"gh_src", "source", "src", "ref", "lever-source", "lever-origin", "trk"})
DEFAULT_PORTS = {"http": ":80", "https": ":443"}

# Stored as sent, in this order. job_link is handled separately because it also feeds the key.
FIELDS = (
    "company", "role", "location", "work_type", "salary", "date_posted", "sponsorship",
    "why_it_fits", "company_careers_url", "official_employer_domain", "posting_source_type",
    "verification_method", "official_apply_url", "full_job_description",
)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_link_key TEXT NOT NULL UNIQUE,
    job_link TEXT NOT NULL,
    {", ".join(f"{name} TEXT" for name in FIELDS)},
    created_at TEXT NOT NULL
)
"""


class ApplicationStoreError(Exception):
    """Raised when the application store cannot be read or written."""


def _is_tracking(pair: str) -> bool:
    name = pair.split("=", 1)[0]
    return name in TRACKING_PARAMS or name.lower().startswith("utm_")


def dedupe_key(link: str) -> str:
    """The form of a job link used to spot duplicates. Non-http(s) values are their own key."""
    try:
        parts = urlsplit(link)
    except ValueError:
        return link
    if parts.scheme.lower() not in DEFAULT_PORTS or not parts.netloc:
        return link
    scheme = parts.scheme.lower()
    userinfo, at, hostport = parts.netloc.rpartition("@")
    hostport = hostport.lower().removesuffix(DEFAULT_PORTS[scheme])
    # Split by hand rather than parse_qsl so encoded values are compared exactly as sent.
    pairs = [p for p in parts.query.split("&") if p and not _is_tracking(p)]
    query = "&".join(sorted(pairs, key=lambda p: tuple(p.split("=", 1))))
    return urlunsplit((scheme, userinfo + at + hostport, parts.path.rstrip("/"), query, ""))


class ApplicationStore:
    """Verified job applications in a SQLite file, one row per job_link dedupe key."""

    def __init__(self, path: Path):
        self._path = Path(path)
        try:
            self._path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            # Create the file ourselves so it never exists with wider permissions.
            os.close(os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600))
            with closing(self._connect()) as conn:
                conn.execute(SCHEMA)
                conn.execute("BEGIN IMMEDIATE")  # write probe: fails on a read-only store
                conn.rollback()
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(
                f"OUTPUT_DIR {self._path.parent}: application store is not writable: {exc}"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def record(self, fields: dict) -> tuple[int, bool]:
        """Store the application unless its link is already known. Returns (id, created)."""
        job_link = fields["job_link"]
        key = dedupe_key(job_link)
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        columns = ("job_link_key", "job_link", *FIELDS, "created_at")
        values = (key, job_link, *(fields.get(name) for name in FIELDS), created_at)
        try:
            with closing(self._connect()) as conn, conn:
                cursor = conn.execute(
                    f"INSERT INTO applications ({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' * len(columns))}) "
                    "ON CONFLICT(job_link_key) DO NOTHING",
                    values,
                )
                created = cursor.rowcount == 1
                (application_id,) = conn.execute(
                    "SELECT id FROM applications WHERE job_link_key = ?", (key,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return application_id, created
