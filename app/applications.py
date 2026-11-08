import difflib
import json
import os
import re
import sqlite3
import unicodedata
import uuid
from contextlib import closing
from dataclasses import dataclass
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
# How a row got here, fixed once recorded: anything not recorded by the apply-from-link workflow is manual.
DEFAULT_ADDED_VIA = "manual"

# Every column but the ID, in table order: what the integer-ID migration copies across.
COPIED_COLUMNS = ("job_link_key", "job_link", *FIELDS, "created_at", "status", "updated_at", "added_via")


def _schema(table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY,
    job_link_key TEXT NOT NULL UNIQUE,
    job_link TEXT NOT NULL,
    {", ".join(f"{name} TEXT" for name in FIELDS)},
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}',
    updated_at TEXT,
    added_via TEXT NOT NULL DEFAULT '{DEFAULT_ADDED_VIA}'
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
LIST_COLUMNS = ("id", "company", "role", "status", "added_via", "posting_source_type", "created_at", "updated_at")
# What the application list carries from each job: its state, never its result or saved path.
JOB_SUMMARY = ("status", "started_at", "finished_at", "error")

# Stores created before these columns existed get them added in place; SQLite fills existing rows
# with the default, so they all read as verified and manual.
MIGRATION = {
    "status": f"ALTER TABLE applications ADD COLUMN status TEXT NOT NULL DEFAULT '{DEFAULT_STATUS}'",
    "updated_at": "ALTER TABLE applications ADD COLUMN updated_at TEXT",
    "added_via": f"ALTER TABLE applications ADD COLUMN added_via TEXT NOT NULL DEFAULT '{DEFAULT_ADDED_VIA}'",
}


class ApplicationStoreError(Exception):
    """Raised when the application store cannot be read or written."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _missing_columns(conn: sqlite3.Connection) -> list[str]:
    present = {column[1] for column in conn.execute("PRAGMA table_info(applications)")}
    return [name for name in MIGRATION if name not in present]


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


# Email-driven status updates (POST /application/email-status). Names from an email rarely match the
# stored ones byte for byte, so both sides are normalized first; a fuzzy match is only a fallback.
COMPANY_SUFFIXES = frozenset({"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co",
                              "company", "plc", "gmbh", "ag", "sa", "bv", "pbc"})
ROLE_ABBREVIATIONS = {"sr": "senior", "jr": "junior"}
SIMILARITY_THRESHOLD = 0.9
NON_ALPHANUMERIC = re.compile(r"[^0-9a-z]+")


def normalize_name(value: str, kind: str) -> str:
    """A company ("company") or role ("role") name reduced to what matters for comparison."""
    text = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    text = text.casefold().replace("&", " and ")
    tokens = NON_ALPHANUMERIC.sub(" ", text).split()
    if kind == "company":
        if len(tokens) > 1 and tokens[0] == "the":
            tokens = tokens[1:]
        while len(tokens) > 1 and tokens[-1] in COMPANY_SUFFIXES:
            tokens = tokens[:-1]
    else:
        tokens = [ROLE_ABBREVIATIONS.get(token, token) for token in tokens]
    return " ".join(tokens)


def _tier(rows: list[dict], field: str, wanted: str) -> list[dict]:
    """The rows whose normalized field equals wanted; failing that, those at least 90% similar."""
    if not wanted:
        return []
    names = [(row, normalize_name(row[field] or "", field)) for row in rows]
    exact = [row for row, name in names if name == wanted]
    if exact:
        return exact
    return [row for row, name in names
            if name and difflib.SequenceMatcher(None, name, wanted).ratio() >= SIMILARITY_THRESHOLD]


def match_applications(rows: list[dict], company: str, role: str, job_link: str | None) -> list[dict]:
    """The applications an email names. Each row needs id, job_link_key, company and role. A job_link that
    identifies a stored posting decides alone; otherwise company and role must both match."""
    if job_link:
        key = dedupe_key(job_link)
        linked = [row for row in rows if row["job_link_key"] == key]
        if linked:
            return linked
    by_company = _tier(rows, "company", normalize_name(company, "company"))
    return _tier(by_company, "role", normalize_name(role, "role"))


EMAIL_STATUSES = ("Applied", "Rejected", "Response")


def email_status_target(current: str, email_status: str) -> str:
    """The status an email moves an application to. Never backwards: Applied only confirms, Response
    advances only an application not yet past applied, and withdrawn stays withdrawn."""
    if email_status == "Rejected" and current != "withdrawn":
        return "rejected"
    if email_status == "Response" and current in ("verified", "applied"):
        return "interviewing"
    return current


@dataclass(frozen=True)
class EmailStatusResult:
    """What apply_email_status did: matched none, several (match_count), or exactly one (the rest)."""

    match_count: int
    application_id: str | None = None
    company: str | None = None
    role: str | None = None
    previous_status: str | None = None
    status: str | None = None
    changed: bool = False


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
        if not _missing_columns(conn):
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Re-check under the write lock: another instance may have migrated meanwhile.
            for name in _missing_columns(conn):
                conn.execute(MIGRATION[name])
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
        columns = ("id", "job_link_key", "job_link", *FIELDS, "created_at", "added_via")
        values = (str(uuid.uuid4()), key, job_link, *(fields.get(name) for name in FIELDS), created_at,
                  fields.get("added_via", DEFAULT_ADDED_VIA))
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

    def apply_email_status(self, company: str, role: str, job_link: str | None,
                           email_status: str) -> EmailStatusResult:
        """Find the one application an email names and move its status. The write lock is taken before the
        read, so nothing can change the row between the match and the update. Nothing is written unless
        exactly one application matches and its status changes."""
        if email_status not in EMAIL_STATUSES:
            raise ValueError("unknown email status")
        try:
            with closing(sqlite3.connect(self._path, timeout=5, isolation_level=None)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    columns = ("id", "job_link_key", "company", "role", "status")
                    rows = [dict(zip(columns, row)) for row in
                            conn.execute(f"SELECT {', '.join(columns)} FROM applications")]
                    matches = match_applications(rows, company, role, job_link)
                    if len(matches) != 1:
                        conn.execute("ROLLBACK")
                        return EmailStatusResult(match_count=len(matches))
                    row = matches[0]
                    target = email_status_target(row["status"], email_status)
                    if target != row["status"]:
                        conn.execute("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
                                     (target, utc_now(), row["id"]))
                    conn.execute("COMMIT")
                except BaseException:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        return EmailStatusResult(match_count=1, application_id=row["id"], company=row["company"], role=row["role"],
                                 previous_status=row["status"], status=target, changed=target != row["status"])

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
        columns = ("id", "job_link", *FIELDS, "status", "added_via", "created_at", "updated_at")
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

    def list_with_reports(self, job_link: str | None = None) -> list[dict]:
        """Every application without its posting text, most recently generated first, then most recently
        recorded; each with a summary of its report, or report None, and each kind's job state, or None.
        With job_link, only the application whose link has the same dedupe key."""
        where, parameters = ("WHERE a.job_link_key = ? ", (dedupe_key(job_link),)) if job_link is not None else ("", ())
        columns = ", ".join(f"a.{name}" for name in LIST_COLUMNS)
        try:
            with closing(self._connect()) as conn:
                jobs = ", ".join(f"{alias}.{name}" for alias in ("jr", "jc") for name in JOB_SUMMARY)
                rows = conn.execute(
                    f"SELECT {columns}, r.generated_at, r.report, {jobs} FROM applications a "
                    "LEFT JOIN resume_reports r ON r.application_id = a.id "
                    "LEFT JOIN generation_jobs jr ON jr.application_id = a.id AND jr.kind = 'resume' "
                    "LEFT JOIN generation_jobs jc ON jc.application_id = a.id AND jc.kind = 'cover_letter' "
                    f"{where}ORDER BY r.generated_at IS NULL, r.generated_at DESC, a.created_at DESC",
                    parameters,
                ).fetchall()
        except sqlite3.Error as exc:
            raise ApplicationStoreError(f"{type(exc).__name__}: {exc}") from exc
        listed = []
        for row in rows:
            item = dict(zip(LIST_COLUMNS, row))
            generated_at, report = row[len(LIST_COLUMNS):len(LIST_COLUMNS) + 2]
            resume_job = row[len(LIST_COLUMNS) + 2:len(LIST_COLUMNS) + 2 + len(JOB_SUMMARY)]
            letter_job = row[len(LIST_COLUMNS) + 2 + len(JOB_SUMMARY):]
            item["jobs"] = {kind: dict(zip(JOB_SUMMARY, job)) if job[0] is not None else None
                            for kind, job in (("resume", resume_job), ("cover_letter", letter_job))}
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
