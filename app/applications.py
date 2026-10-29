import json
import os
import sqlite3
import uuid
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

# What an update may write. job_link and the verification fields are fixed once recorded.
UPDATABLE_FIELDS = frozenset({
    "status", "company", "role", "location", "work_type", "salary", "date_posted", "sponsorship",
    "why_it_fits", "company_careers_url", "official_employer_domain", "full_job_description",
})
DEFAULT_STATUS = "verified"

# Every column but the ID, in table order: what the integer-ID migration copies across.
COPIED_COLUMNS = ("job_link_key", "job_link", *FIELDS, "created_at", "status", "updated_at")


def _schema(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY,
    job_link_key TEXT NOT NULL UNIQUE,
    job_link TEXT NOT NULL,
    {", ".join(f"{name} TEXT" for name in FIELDS)},
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}',
    updated_at TEXT
)
"""


SCHEMA = _schema("applications")

# Stores created before UUIDs keep a record of which integer ID became which UUID.
LEGACY_IDS_TABLE = "legacy_application_ids"
LEGACY_IDS_SCHEMA = f"""
CREATE TABLE {LEGACY_IDS_TABLE} (
    old_id INTEGER PRIMARY KEY,
    application_id TEXT NOT NULL UNIQUE
)
"""

# The latest generation report per application, for the resume viewer. `report` is a JSON document;
# generated_at and saved_path are columns too, so listing can sort without parsing it. Removed by delete().
REPORTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS resume_reports (
    application_id TEXT PRIMARY KEY REFERENCES applications(id),
    generated_at TEXT NOT NULL,
    saved_path TEXT NOT NULL,
    report TEXT NOT NULL
)
"""
# The latest background run per application and kind, for the status endpoints. `result` is a JSON
# document: {"match": ...} for a resume, {"text": ...} for a cover letter. Removed by delete().
JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS generation_jobs (
    application_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('resume', 'cover_letter')),
    status TEXT NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    saved_path TEXT,
    error TEXT,
    result TEXT,
    PRIMARY KEY (application_id, kind)
)
"""
JOB_KINDS = ("resume", "cover_letter")
INTERRUPTED = "Interrupted by a service restart"
# get_job's answer for an application that exists but has never had a job of that kind.
NO_JOB = "no_job"

# What the application list carries from each report: scores and status, never posting text.
REPORT_SUMMARY = ("status", "threshold", "base_score", "tailored_score")
LIST_COLUMNS = ("id", "company", "role", "status", "created_at", "updated_at")

# Stores created before statuses existed get the columns added in place; SQLite fills existing
# rows with the default, so they all read as verified.
MIGRATION = (
    f"ALTER TABLE applications ADD COLUMN status TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}'",
    "ALTER TABLE applications ADD COLUMN updated_at TEXT",
)


class ApplicationStoreError(Exception):
    """Raised when the application store cannot be read or written."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _has_status(conn: sqlite3.Connection) -> bool:
    return any(column[1] == "status" for column in conn.execute("PRAGMA table_info(applications)"))


def _has_integer_ids(conn: sqlite3.Connection) -> bool:
    return any(
        column[1] == "id" and column[2].upper() == "INTEGER"
        for column in conn.execute("PRAGMA table_info(applications)")
    )


def _has_legacy_ids(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (LEGACY_IDS_TABLE,)
    ).fetchone() is not None


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
                self._migrate(conn)
                self._migrate_ids(conn)
                conn.execute(REPORTS_SCHEMA)
                conn.execute(JOBS_SCHEMA)
                conn.execute("BEGIN IMMEDIATE")  # write probe: fails on a read-only store
                # A job still running belongs to a process that is gone: its thread did not survive.
                conn.execute(
                    "UPDATE generation_jobs SET status = 'failed', finished_at = ?, error = ? WHERE status = 'running'",
                    (utc_now(), INTERRUPTED),
                )
                conn.commit()
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(
                f"OUTPUT_DIR {self._path.parent}: application store is not writable: {exc}"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        if _has_status(conn):
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Re-check under the write lock: another instance may have migrated meanwhile.
            if not _has_status(conn):
                for statement in MIGRATION:
                    conn.execute(statement)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def _migrate_ids(self, conn: sqlite3.Connection) -> None:
        """Give every row of an integer-ID store a random UUID, keeping the old-to-new mapping."""
        if not _has_integer_ids(conn):
            return
        # The backup API cannot read from a connection holding the write lock, so copy first.
        backup = self._backup(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Re-check under the write lock: another instance may have migrated meanwhile.
            if not _has_integer_ids(conn):
                backup.unlink()
            else:
                old_ids = [old_id for (old_id,) in conn.execute("SELECT id FROM applications")]
                conn.execute(LEGACY_IDS_SCHEMA)
                conn.executemany(
                    f"INSERT INTO {LEGACY_IDS_TABLE} (old_id, application_id) VALUES (?, ?)",
                    [(old_id, str(uuid.uuid4())) for old_id in old_ids],
                )
                # SQLite cannot change a primary key's type, so the table is rebuilt.
                columns = ", ".join(COPIED_COLUMNS)
                conn.execute(_schema("applications_new"))
                conn.execute(
                    f"INSERT INTO applications_new (id, {columns}) "
                    f"SELECT m.application_id, {', '.join(f'a.{name}' for name in COPIED_COLUMNS)} "
                    f"FROM applications a JOIN {LEGACY_IDS_TABLE} m ON m.old_id = a.id"
                )
                conn.execute("DROP TABLE applications")
                conn.execute("ALTER TABLE applications_new RENAME TO applications")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def _backup(self, conn: sqlite3.Connection) -> Path:
        """Copy the store as it is now to a private file beside it, and return its path."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self._path.with_name(f"{self._path.name}.pre-uuid-{stamp}.bak")
        os.close(os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600))
        with closing(sqlite3.connect(path)) as target:
            conn.backup(target)
        return path

    def legacy_ids(self) -> dict[int, str]:
        """Old integer ID to UUID, for stores migrated from integer IDs; empty otherwise."""
        try:
            with closing(self._connect()) as conn:
                if not _has_legacy_ids(conn):
                    return {}
                return dict(conn.execute(f"SELECT old_id, application_id FROM {LEGACY_IDS_TABLE}"))
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc

    def record(self, fields: dict) -> tuple[str, bool]:
        """Store the application unless its link is already known. Returns (id, created)."""
        job_link = fields["job_link"]
        key = dedupe_key(job_link)
        created_at = utc_now()
        columns = ("id", "job_link_key", "job_link", *FIELDS, "created_at")
        values = (str(uuid.uuid4()), key, job_link, *(fields.get(name) for name in FIELDS), created_at)
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

    def update(self, application_id: str, changes: dict) -> str | None:
        """Write the given fields to one row. Returns its status after the update, or None if absent."""
        unknown = set(changes) - UPDATABLE_FIELDS
        if not changes or unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}" if unknown else "no fields to update")
        # Column names come from UPDATABLE_FIELDS only, never from the client.
        columns = sorted(changes)
        assignments = ", ".join(f"{name} = ?" for name in (*columns, "updated_at"))
        values = (*(changes[name] for name in columns), utc_now(), application_id)
        try:
            with closing(self._connect()) as conn, conn:
                result = conn.execute(
                    f"UPDATE applications SET {assignments} WHERE id = ? RETURNING status", values
                ).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return result[0] if result else None

    def delete(self, application_id: str) -> bool:
        """Remove the row for good, freeing its job_link. Returns whether a row was removed."""
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute("DELETE FROM resume_reports WHERE application_id = ?", (application_id,))
                conn.execute("DELETE FROM generation_jobs WHERE application_id = ?", (application_id,))
                cursor = conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return cursor.rowcount == 1

    def exists(self, application_id: str) -> bool:
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT 1 FROM applications WHERE id = ?", (application_id,)).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return row is not None

    def get(self, application_id: str) -> dict | None:
        """The stored row as a dict (without its dedupe key), or None if absent."""
        columns = ("id", "job_link", *FIELDS, "status", "created_at", "updated_at")
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    f"SELECT {', '.join(columns)} FROM applications WHERE id = ?", (application_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return dict(zip(columns, row)) if row else None

    def save_report(self, application_id: str, generated_at: str, saved_path: str, report: dict) -> bool:
        """Store the application's generation report, replacing any earlier one. Returns False, storing
        nothing, when the application no longer exists."""
        try:
            with closing(self._connect()) as conn, conn:
                cursor = conn.execute(
                    "INSERT INTO resume_reports (application_id, generated_at, saved_path, report) "
                    "SELECT ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM applications WHERE id = ?) "
                    "ON CONFLICT(application_id) DO UPDATE SET generated_at = excluded.generated_at, "
                    "saved_path = excluded.saved_path, report = excluded.report",
                    (application_id, generated_at, saved_path, json.dumps(report), application_id),
                )
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return cursor.rowcount == 1

    def delete_report(self, application_id: str) -> bool:
        try:
            with closing(self._connect()) as conn, conn:
                cursor = conn.execute("DELETE FROM resume_reports WHERE application_id = ?", (application_id,))
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return cursor.rowcount == 1

    def get_report(self, application_id: str) -> dict | None:
        """The stored report with its generated_at and saved_path, or None if there is none."""
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT generated_at, saved_path, report FROM resume_reports WHERE application_id = ?",
                    (application_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        if row is None:
            return None
        generated_at, saved_path, report = row
        return {**json.loads(report), "generated_at": generated_at, "saved_path": saved_path}

    def list_with_reports(self) -> list[dict]:
        """Every application without its posting text, most recently generated first, then most recently
        recorded; each with a summary of its report, or report None."""
        columns = ", ".join(f"a.{name}" for name in LIST_COLUMNS)
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    f"SELECT {columns}, r.generated_at, r.report FROM applications a "
                    "LEFT JOIN resume_reports r ON r.application_id = a.id "
                    "ORDER BY r.generated_at IS NULL, r.generated_at DESC, a.created_at DESC"
                ).fetchall()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        listed = []
        for row in rows:
            item = dict(zip(LIST_COLUMNS, row))
            generated_at, report = row[len(LIST_COLUMNS):]
            if report is None:
                item["report"] = None
            else:
                data = json.loads(report)
                item["report"] = {"generated_at": generated_at, **{name: data.get(name) for name in REPORT_SUMMARY}}
            listed.append(item)
        return listed

    def start_job(self, application_id: str, kind: str, started_at: str) -> tuple[bool, str | None]:
        """Claim the application's job of this kind for a new run, unless one is already running.

        Returns (True, started_at) when claimed, (False, the running job's started_at) when a run is already
        in progress, and (False, None) when the application does not exist. One statement, so two requests,
        even on different listeners, can never both claim.
        """
        try:
            with closing(self._connect()) as conn, conn:
                cursor = conn.execute(
                    "INSERT INTO generation_jobs (application_id, kind, status, started_at) "
                    "SELECT ?, ?, 'running', ? FROM applications WHERE id = ? "
                    "ON CONFLICT(application_id, kind) DO UPDATE SET status = 'running', "
                    "started_at = excluded.started_at, finished_at = NULL, saved_path = NULL, error = NULL, "
                    "result = NULL WHERE generation_jobs.status != 'running'",
                    (application_id, kind, started_at, application_id),
                )
                if cursor.rowcount == 1:
                    return True, started_at
                row = conn.execute(
                    "SELECT j.started_at FROM applications a JOIN generation_jobs j "
                    "ON j.application_id = a.id AND j.kind = ? WHERE a.id = ? AND j.status = 'running'",
                    (kind, application_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return False, row[0] if row else None

    def finish_job(self, application_id: str, kind: str, started_at: str, status: str,
                   saved_path: str | None = None, error: str | None = None, result: dict | None = None) -> bool:
        """Record how the run that started at started_at ended. Returns False, changing nothing, when that run
        no longer owns the row: the application was deleted, or a restart already failed the job."""
        try:
            with closing(self._connect()) as conn, conn:
                cursor = conn.execute(
                    "UPDATE generation_jobs SET status = ?, finished_at = ?, saved_path = ?, error = ?, result = ? "
                    "WHERE application_id = ? AND kind = ? AND status = 'running' AND started_at = ?",
                    (status, utc_now(), saved_path, error, json.dumps(result) if result is not None else None,
                     application_id, kind, started_at),
                )
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return cursor.rowcount == 1

    def get_job(self, application_id: str, kind: str) -> dict | str | None:
        """The job record with its result fields decoded, NO_JOB when the application exists but has no job
        of this kind, or None when there is no such application."""
        try:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT j.status, j.started_at, j.finished_at, j.saved_path, j.error, j.result "
                    "FROM applications a LEFT JOIN generation_jobs j ON j.application_id = a.id AND j.kind = ? "
                    "WHERE a.id = ?",
                    (kind, application_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        if row is None:
            return None
        status, started_at, finished_at, saved_path, error, result = row
        if status is None:
            return NO_JOB
        return {"status": status, "started_at": started_at, "finished_at": finished_at, "saved_path": saved_path,
                "error": error, **(json.loads(result) if result else {})}
