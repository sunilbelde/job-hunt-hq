import os
import re
import sqlite3
import stat
import threading
import uuid
from contextlib import closing

import pytest

from app.applications import (
    FIELDS, INTERRUPTED, NO_JOB, ApplicationStore, ApplicationStoreError, dedupe_key, email_status_target,
    match_applications, normalize_name,
)
from app.storage import StorageError

GH = "https://job-boards.greenhouse.io/acme/jobs/123"
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


# --- dedupe_key ---

@pytest.mark.parametrize("link", [
    GH,
    GH + "/",
    GH + "//",
    GH + "#apply",
    "HTTPS://Job-Boards.Greenhouse.IO/acme/jobs/123",
    "https://job-boards.greenhouse.io:443/acme/jobs/123",
    GH + "?gh_src=abc",
    GH + "?utm_source=x&UTM_Campaign=y&utm_medium=z",
    GH + "?source=li&src=x&ref=y&lever-source=a&lever-origin=b&trk=c",
    GH + "/?gh_src=x&utm_source=y#apply",
])
def test_decorated_links_share_a_key(link):
    assert dedupe_key(link) == GH


def test_http_default_port_dropped():
    assert dedupe_key("http://Example.com:80/jobs/1") == "http://example.com/jobs/1"


def test_non_default_port_kept():
    assert dedupe_key("https://example.com:8443/jobs/1") == "https://example.com:8443/jobs/1"


def test_job_id_in_query_kept():
    a = dedupe_key("https://www.acme.com/careers?gh_jid=111")
    b = dedupe_key("https://www.acme.com/careers?gh_jid=222")
    assert a != b and a == "https://www.acme.com/careers?gh_jid=111"


def test_tracking_removed_but_job_id_kept():
    link = "https://www.acme.com/careers?utm_source=x&gh_jid=111&gh_src=y"
    assert dedupe_key(link) == "https://www.acme.com/careers?gh_jid=111"


def test_parameter_order_ignored():
    base = "https://boards.greenhouse.io/embed/job_app"
    assert dedupe_key(f"{base}?for=acme&token=12") == dedupe_key(f"{base}?token=12&for=acme")


def test_path_case_preserved():
    assert dedupe_key("https://acme.wd1.myworkdayjobs.com/Careers/job/1") != dedupe_key(
        "https://acme.wd1.myworkdayjobs.com/careers/job/1")


def test_encoded_values_untouched():
    encoded = dedupe_key("https://example.com/apply?next=a%2Fb")
    assert "a%2Fb" in encoded
    assert encoded != dedupe_key("https://example.com/apply?next=a/b")


def test_only_tracking_params_leaves_no_question_mark():
    assert dedupe_key("https://example.com/jobs/1?utm_source=x") == "https://example.com/jobs/1"


def test_other_param_names_are_case_sensitive():
    assert dedupe_key("https://example.com/jobs?Source=x") == "https://example.com/jobs?Source=x"


@pytest.mark.parametrize("link", ["not a url", "ftp://example.com/jobs/1/", "https://", "http://[bad"])
def test_non_http_values_are_their_own_key(link):
    assert dedupe_key(link) == link


# --- ApplicationStore ---

def row(job_link=GH, **overrides):
    return {
        "company": "Acme", "role": "Engineer", "job_link": job_link,
        "posting_source_type": "recruiting_platform", "verification_method": "official_apply_match",
        "official_apply_url": job_link, **overrides,
    }


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "out" / "applications.sqlite3"


@pytest.fixture
def store(db_path):
    return ApplicationStore(db_path)


def stored(db_path, application_id):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone())


def count(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT count(*) FROM applications").fetchone()[0]


def test_first_record_creates_repeat_returns_same_id(store, db_path):
    application_id, created = store.record(row(salary="$1"))
    assert created and UUID4.match(application_id)
    assert store.record(row(salary="$2")) == (application_id, False)
    assert stored(db_path, application_id)["salary"] == "$1"
    assert count(db_path) == 1


def test_decorated_variant_returns_existing_and_keeps_first_link(store, db_path):
    application_id, _ = store.record(row())
    variant = GH + "/?utm_source=x"
    assert store.record(row(variant)) == (application_id, False)
    saved = stored(db_path, application_id)
    assert saved["job_link"] == GH and saved["job_link_key"] == GH


def test_raw_link_retained_with_key(store, db_path):
    link = "https://example.com/jobs/1/?utm_source=x"
    application_id, _ = store.record(row(link))
    saved = stored(db_path, application_id)
    assert saved["job_link"] == link and saved["job_link_key"] == "https://example.com/jobs/1"


def test_different_links_get_distinct_uuids(store):
    first, _ = store.record(row(GH))
    second, _ = store.record(row(GH.replace("123", "456")))
    assert UUID4.match(first) and UUID4.match(second) and first != second


def test_rows_survive_restart(db_path):
    application_id, _ = ApplicationStore(db_path).record(row())
    assert ApplicationStore(db_path).record(row()) == (application_id, False)


def test_fields_stored_as_sent(store, db_path):
    application_id, _ = store.record(row(
        "https://acme.com/careers/1", posting_source_type="employer_site",
        verification_method="employer_site", official_apply_url=""))
    saved = stored(db_path, application_id)
    assert saved["official_apply_url"] == ""
    assert saved["location"] is None and saved["full_job_description"] is None
    assert saved["created_at"].endswith("Z")


def test_easy_apply_row_round_trips_and_lists_its_source(store):
    link = "https://www.linkedin.com/jobs/view/4012345678/"
    application_id, _ = store.record(row(link, posting_source_type="linkedin_easy_apply",
                                         verification_method="owner_confirmed", official_apply_url="", added_via="link"))
    saved = store.get(application_id)
    assert (saved["posting_source_type"], saved["verification_method"]) == ("linkedin_easy_apply", "owner_confirmed")
    assert saved["official_apply_url"] == "" and saved["added_via"] == "link"
    (listed,) = store.list_with_reports()
    assert listed["posting_source_type"] == "linkedin_easy_apply"


def test_file_private(store, db_path):
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_read_only_store_fails_naming_output_dir(store, db_path):
    db_path.chmod(0o400)
    try:
        with pytest.raises(StorageError, match="OUTPUT_DIR"):
            ApplicationStore(db_path)
    finally:
        db_path.chmod(0o600)


def test_concurrent_records_create_one_row(store, db_path):
    barrier = threading.Barrier(8)
    results = []

    def worker():
        barrier.wait()
        results.append(store.record(row()))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(results) == 8
    assert len({application_id for application_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    assert count(db_path) == 1


# --- status and migration ---

OLD_SCHEMA = f"""
CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_link_key TEXT NOT NULL UNIQUE,
    job_link TEXT NOT NULL,
    {", ".join(f"{name} TEXT" for name in FIELDS)},
    created_at TEXT NOT NULL
)
"""


@pytest.fixture
def old_store_path(db_path):
    """A store file as written before statuses existed, holding two rows."""
    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(OLD_SCHEMA)
        for n in (1, 2):
            conn.execute(
                "INSERT INTO applications (job_link_key, job_link, company, role, salary, created_at) "
                "VALUES (?, ?, 'Acme', 'Engineer', ?, '2026-10-01T00:00:00Z')",
                (f"https://example.com/jobs/{n}", f"https://example.com/jobs/{n}/", f"${n}"),
            )
    db_path.chmod(0o600)
    return db_path


def test_new_row_is_verified_without_updated_at(store, db_path):
    application_id, _ = store.record(row())
    saved = stored(db_path, application_id)
    assert saved["status"] == "verified" and saved["updated_at"] is None


def test_old_store_migrated_to_verified(old_store_path):
    store = ApplicationStore(old_store_path)
    ids = store.legacy_ids()
    for n in (1, 2):
        saved = stored(old_store_path, ids[n])
        assert saved["status"] == "verified" and saved["updated_at"] is None
        assert saved["job_link"] == f"https://example.com/jobs/{n}/" and saved["salary"] == f"${n}"
        assert saved["created_at"] == "2026-10-01T00:00:00Z"
    assert store.update(ids[1], {"status": "applied"}) == "applied"
    assert store.delete(ids[2])


def test_reopening_migrated_store_keeps_statuses(old_store_path):
    ids = ApplicationStore(old_store_path).legacy_ids()
    with closing(sqlite3.connect(old_store_path)) as conn, conn:
        conn.execute("UPDATE applications SET status = 'offer' WHERE id = ?", (ids[1],))
    ApplicationStore(old_store_path)
    assert stored(old_store_path, ids[1])["status"] == "offer"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unwritable_old_store_fails_naming_output_dir(old_store_path):
    old_store_path.chmod(0o400)
    try:
        with pytest.raises(StorageError, match="OUTPUT_DIR"):
            ApplicationStore(old_store_path)
    finally:
        old_store_path.chmod(0o600)


def test_concurrent_migration(old_store_path):
    barrier = threading.Barrier(2)
    errors = []

    def worker():
        barrier.wait()
        try:
            ApplicationStore(old_store_path)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    ids = ApplicationStore(old_store_path).legacy_ids()
    assert stored(old_store_path, ids[1])["status"] == "verified"
    assert len(backups(old_store_path)) == 1


# --- update, delete, exists ---

def test_update_changes_only_given_fields(store, db_path):
    application_id, _ = store.record(row(salary="$1", location="Remote"))
    before = stored(db_path, application_id)
    assert store.update(application_id, {"status": "applied", "salary": "$2"}) == "applied"
    after = stored(db_path, application_id)
    assert after["salary"] == "$2" and after["status"] == "applied"
    assert after["created_at"] == before["created_at"]
    assert after["updated_at"].endswith("Z") and after["updated_at"] >= after["created_at"]
    changed = {"status", "salary", "updated_at"}
    assert {k: v for k, v in after.items() if k not in changed} == {
        k: v for k, v in before.items() if k not in changed}


def test_update_returns_unchanged_status(store):
    application_id, _ = store.record(row())
    assert store.update(application_id, {"salary": "$2"}) == "verified"


def test_update_null_clears(store, db_path):
    application_id, _ = store.record(row(sponsorship="Yes"))
    store.update(application_id, {"sponsorship": None})
    assert stored(db_path, application_id)["sponsorship"] is None


@pytest.mark.parametrize("changes", [{}, {"job_link": "x"}, {"status": "applied", "id": 5}])
def test_update_rejects_non_updatable_columns(store, changes):
    application_id, _ = store.record(row())
    with pytest.raises(ValueError):
        store.update(application_id, changes)


def test_missing_id(store):
    unknown = str(uuid.uuid4())
    assert store.update(unknown, {"status": "applied"}) is None
    assert store.delete(unknown) is False
    assert store.exists(unknown) is False


def test_delete_frees_link_for_new_row(store, db_path):
    application_id, _ = store.record(row())
    assert store.exists(application_id)
    assert store.delete(application_id)
    assert not store.exists(application_id)
    variant = GH + "/?utm_source=x"
    new_id, created = store.record(row(variant))
    assert created and new_id != application_id
    assert stored(db_path, new_id)["job_link"] == variant
    assert stored(db_path, new_id)["status"] == "verified"


def test_new_id_after_delete(store):
    first, _ = store.record(row())
    store.delete(first)
    again, _ = store.record(row())
    assert UUID4.match(again) and again != first


def test_concurrent_updates_all_land(store, db_path):
    application_id, _ = store.record(row())
    fields = ["status", "location", "work_type", "salary", "date_posted", "sponsorship",
              "why_it_fits", "full_job_description"]
    barrier = threading.Barrier(len(fields))
    errors = []

    def worker(name):
        barrier.wait()
        try:
            store.update(application_id, {name: "offer" if name == "status" else f"new {name}"})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(name,)) for name in fields]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    saved = stored(db_path, application_id)
    assert saved["status"] == "offer"
    assert all(saved[name] == f"new {name}" for name in fields if name != "status")


def test_update_survives_restart(db_path):
    application_id, _ = ApplicationStore(db_path).record(row())
    ApplicationStore(db_path).update(application_id, {"status": "offer"})
    ApplicationStore(db_path)
    assert stored(db_path, application_id)["status"] == "offer"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_write_failures_raise_store_error(store, db_path):
    application_id, _ = store.record(row())
    db_path.chmod(0o400)
    try:
        with pytest.raises(ApplicationStoreError):
            store.update(application_id, {"status": "applied"})
        with pytest.raises(ApplicationStoreError):
            store.delete(application_id)
    finally:
        db_path.chmod(0o600)


def test_read_failure_raises_store_error(store, db_path):
    db_path.unlink()
    db_path.mkdir()  # a directory where the file was: sqlite cannot open it
    with pytest.raises(ApplicationStoreError):
        store.exists(str(uuid.uuid4()))


def test_get_returns_stored_row_without_key(store):
    application_id, _ = store.record(row(salary="$1"))
    got = store.get(application_id)
    assert got["id"] == application_id
    assert got["company"] == "Acme" and got["job_link"] == GH and got["salary"] == "$1"
    assert got["location"] is None and got["status"] == "verified" and got["updated_at"] is None
    assert got["created_at"]
    assert "job_link_key" not in got
    assert set(got) == {"id", "job_link", *FIELDS, "status", "added_via", "created_at", "updated_at"}


def test_get_missing_or_deleted_is_none(store):
    assert store.get(str(uuid.uuid4())) is None
    application_id, _ = store.record(row())
    store.delete(application_id)
    assert store.get(application_id) is None


def test_get_does_not_touch_updated_at(store, db_path):
    application_id, _ = store.record(row())
    store.get(application_id)
    assert stored(db_path, application_id)["updated_at"] is None


def test_get_read_failure_raises_store_error(store, db_path):
    db_path.unlink()
    db_path.mkdir()
    with pytest.raises(ApplicationStoreError):
        store.get(str(uuid.uuid4()))


# --- integer-ID migration ---

STATUS_SCHEMA = OLD_SCHEMA.replace(
    "created_at TEXT NOT NULL", "created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'verified', updated_at TEXT")


def backups(db_path):
    return sorted(db_path.parent.glob(db_path.name + ".pre-uuid-*.bak"))


@pytest.fixture
def int_store_path(db_path):
    """A store file with statuses but integer IDs, holding rows 1 and 2."""
    db_path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(STATUS_SCHEMA)
        conn.execute(
            "INSERT INTO applications (id, job_link_key, job_link, company, role, salary, created_at, status, updated_at) "
            "VALUES (1, 'https://example.com/jobs/1', 'https://example.com/jobs/1/', 'Acme', 'Engineer', '$1', "
            "'2026-10-01T00:00:00Z', 'applied', '2026-10-02T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO applications (id, job_link_key, job_link, company, role, created_at) "
            "VALUES (2, 'https://example.com/jobs/2', 'https://example.com/jobs/2', 'Beta', 'Engineer', "
            "'2026-10-03T00:00:00Z')"
        )
    db_path.chmod(0o600)
    return db_path


def raw_rows(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM applications")]


def with_origin(rows):
    """The rows as the migration leaves them: the origin column is added before the ID rebuild is tried."""
    return [{**r, "added_via": "manual"} for r in rows]


def test_integer_ids_migrated_keeping_fields(int_store_path):
    before = {r["id"]: r for r in raw_rows(int_store_path)}
    store = ApplicationStore(int_store_path)
    ids = store.legacy_ids()
    assert set(ids) == {1, 2} and len(set(ids.values())) == 2
    assert all(UUID4.match(v) for v in ids.values())
    for old_id, new_id in ids.items():
        after = stored(int_store_path, new_id)
        assert after == {**before[old_id], "id": new_id, "added_via": "manual"}


def test_migrated_store_keeps_working(int_store_path):
    store = ApplicationStore(int_store_path)
    ids = store.legacy_ids()
    assert store.record(row("https://example.com/jobs/1")) == (ids[1], False)
    new_id, created = store.record(row("https://example.com/jobs/3"))
    assert created and UUID4.match(new_id)
    assert store.update(ids[2], {"status": "offer"}) == "offer"


def test_old_integer_ids_name_nothing(int_store_path):
    store = ApplicationStore(int_store_path)
    for old in (1, "1"):
        assert store.get(old) is None and not store.exists(old)
        assert store.update(old, {"status": "offer"}) is None
        assert store.delete(old) is False
    assert len(raw_rows(int_store_path)) == 2


def test_backup_private_and_holds_integer_rows(int_store_path):
    before = raw_rows(int_store_path)
    ApplicationStore(int_store_path)
    [backup] = backups(int_store_path)
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert raw_rows(backup) == with_origin(before)


def test_pre_status_store_gets_status_and_uuids(old_store_path):
    store = ApplicationStore(old_store_path)
    ids = store.legacy_ids()
    assert set(ids) == {1, 2}
    assert all(stored(old_store_path, v)["status"] == "verified" for v in ids.values())


def test_restart_after_migration_changes_nothing(int_store_path):
    ids = ApplicationStore(int_store_path).legacy_ids()
    rows = raw_rows(int_store_path)
    assert ApplicationStore(int_store_path).legacy_ids() == ids
    assert raw_rows(int_store_path) == rows
    assert len(backups(int_store_path)) == 1


def test_new_store_has_no_legacy_ids(store):
    assert store.legacy_ids() == {}


def test_failed_migration_leaves_integer_store(int_store_path, monkeypatch):
    before = raw_rows(int_store_path)
    same = uuid.uuid4()
    monkeypatch.setattr("app.applications.uuid.uuid4", lambda: same)  # second mapping row breaks UNIQUE
    with pytest.raises(StorageError, match="OUTPUT_DIR"):
        ApplicationStore(int_store_path)
    assert raw_rows(int_store_path) == with_origin(before)
    monkeypatch.undo()
    assert set(ApplicationStore(int_store_path).legacy_ids()) == {1, 2}


# --- generation reports ---

REPORT = {"version": 1, "status": "tailored", "threshold": 70, "base_score": 57, "tailored_score": 81,
          "base": {"score": 57}, "tailored": {"score": 81}, "added_terms": ["Airflow"], "rejected_terms": []}


def reports(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("SELECT application_id FROM resume_reports").fetchall()


def test_report_stored_and_read_back(store):
    application_id, _ = store.record(row())
    assert store.get_report(application_id) is None
    assert store.save_report(application_id, "2026-10-20T10:00:00Z", "/out/Acme/x/JANE DOE.pdf", REPORT)
    assert store.get_report(application_id) == {**REPORT, "generated_at": "2026-10-20T10:00:00Z",
                                                "saved_path": "/out/Acme/x/JANE DOE.pdf"}


def test_new_report_replaces_the_old_one(store, db_path):
    application_id, _ = store.record(row())
    store.save_report(application_id, "2026-10-20T10:00:00Z", "/a.pdf", REPORT)
    store.save_report(application_id, "2026-10-20T11:00:00Z", "/b.pdf", {**REPORT, "status": "base_meets_threshold"})
    assert len(reports(db_path)) == 1
    got = store.get_report(application_id)
    assert (got["status"], got["saved_path"], got["generated_at"]) == ("base_meets_threshold", "/b.pdf", "2026-10-20T11:00:00Z")


def test_report_for_a_missing_application_is_not_stored(store, db_path):
    assert store.save_report(str(uuid.uuid4()), "2026-10-20T10:00:00Z", "/a.pdf", REPORT) is False
    assert reports(db_path) == []


def test_delete_removes_the_report(store, db_path):
    application_id, _ = store.record(row())
    store.save_report(application_id, "2026-10-20T10:00:00Z", "/a.pdf", REPORT)
    assert store.delete(application_id)
    assert reports(db_path) == [] and store.get_report(application_id) is None


def test_delete_report_only(store):
    application_id, _ = store.record(row())
    store.save_report(application_id, "2026-10-20T10:00:00Z", "/a.pdf", REPORT)
    assert store.delete_report(application_id) and not store.delete_report(application_id)
    assert store.get(application_id) is not None and store.get_report(application_id) is None


def test_update_keeps_the_report(store):
    application_id, _ = store.record(row())
    store.save_report(application_id, "2026-10-20T10:00:00Z", "/out/Acme/x/JANE DOE.pdf", REPORT)
    store.update(application_id, {"company": "Acme Inc"})
    assert store.get_report(application_id)["saved_path"] == "/out/Acme/x/JANE DOE.pdf"


def test_old_store_gets_the_reports_table_with_rows_unchanged(old_store_path):
    store = ApplicationStore(old_store_path)
    rows = store.list_with_reports()
    assert len(rows) == 2 and all(item["report"] is None for item in rows)
    assert {item["company"] for item in rows} == {"Acme"}


def test_list_orders_by_generation_then_recording(store, db_path):
    first, _ = store.record(row("https://example.com/1"))
    second, _ = store.record(row("https://example.com/2"))
    third, _ = store.record(row("https://example.com/3", full_job_description="secret posting"))
    with closing(sqlite3.connect(db_path)) as conn, conn:  # created_at ties within a test; make the order explicit
        for n, application_id in enumerate((first, second, third)):
            conn.execute("UPDATE applications SET created_at = ? WHERE id = ?", (f"2026-10-0{n + 1}T00:00:00Z", application_id))
    store.save_report(first, "2026-10-20T10:00:00Z", "/a.pdf", REPORT)
    store.save_report(second, "2026-10-20T09:00:00Z", "/b.pdf", {**REPORT, "status": "no_job_description",
                                                                 "base_score": None, "tailored_score": None})
    listed = store.list_with_reports()
    assert [item["id"] for item in listed] == [first, second, third]
    assert listed[0]["report"] == {"generated_at": "2026-10-20T10:00:00Z", "status": "tailored", "threshold": 70,
                                   "base_score": 57, "tailored_score": 81}
    assert listed[2]["report"] is None
    assert set(listed[2]) == {"id", "company", "role", "status", "added_via", "posting_source_type", "created_at",
                              "updated_at", "report", "jobs"}
    assert listed[2]["jobs"] == {"resume": None, "cover_letter": None}
    assert "secret posting" not in repr(listed)


def test_report_read_failure_raises_store_error(store, db_path):
    db_path.unlink()
    db_path.mkdir()
    for call in (lambda: store.get_report(str(uuid.uuid4())), store.list_with_reports,
                 lambda: store.save_report(str(uuid.uuid4()), "t", "/a.pdf", REPORT)):
        with pytest.raises(ApplicationStoreError):
            call()


# --- generation jobs ---

MATCH = {"status": "no_job_description", "threshold": 70, "base_score": None, "tailored_score": None, "added_terms": []}


def jobs(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("SELECT application_id, kind, status FROM generation_jobs ORDER BY kind").fetchall()


def test_old_store_gets_the_jobs_table_with_rows_unchanged(old_store_path):
    store = ApplicationStore(old_store_path)
    rows = store.list_with_reports()
    assert len(rows) == 2 and all(item["report"] is None for item in rows)
    assert jobs(old_store_path) == []
    assert all(store.get_job(item["id"], "resume") == NO_JOB for item in rows)


def test_list_carries_job_states_only(store):
    running, _ = store.record(row("https://example.com/1"))
    finished, _ = store.record(row("https://example.com/2"))
    idle, _ = store.record(row("https://example.com/3"))
    store.start_job(running, "resume", "2026-10-28T10:00:00Z")
    store.start_job(running, "cover_letter", "2026-10-28T10:00:01Z")
    store.finish_job(running, "cover_letter", "2026-10-28T10:00:01Z", "failed", error="Cover letter generation failed")
    store.start_job(finished, "resume", "2026-10-28T09:00:00Z")
    store.finish_job(finished, "resume", "2026-10-28T09:00:00Z", "done", saved_path="/out/Acme/secret/JANE DOE.pdf",
                     result={"match": MATCH})
    store.start_job(finished, "cover_letter", "2026-10-28T09:00:01Z")
    store.finish_job(finished, "cover_letter", "2026-10-28T09:00:01Z", "done", saved_path="/out/Acme/secret/letter.pdf",
                     result={"text": "Dear hiring team, secret letter"})
    by_id = {item["id"]: item["jobs"] for item in store.list_with_reports()}
    assert by_id[running]["resume"] == {"status": "running", "started_at": "2026-10-28T10:00:00Z", "finished_at": None,
                                        "error": None}
    assert by_id[running]["cover_letter"]["status"] == "failed"
    assert by_id[running]["cover_letter"]["error"] == "Cover letter generation failed"
    assert by_id[finished]["resume"]["status"] == by_id[finished]["cover_letter"]["status"] == "done"
    assert set(by_id[finished]["resume"]) == {"status", "started_at", "finished_at", "error"}
    assert by_id[idle] == {"resume": None, "cover_letter": None}
    assert "secret" not in repr(by_id) and "no_job_description" not in repr(by_id)


def test_new_job_claimed(store):
    application_id, _ = store.record(row())
    assert store.start_job(application_id, "resume", "2026-10-28T10:00:00.000001Z") == (True, "2026-10-28T10:00:00.000001Z")
    assert store.get_job(application_id, "resume") == {
        "status": "running", "started_at": "2026-10-28T10:00:00.000001Z", "finished_at": None,
        "saved_path": None, "error": None}


def test_claim_while_running_changes_nothing(store):
    application_id, _ = store.record(row())
    store.start_job(application_id, "resume", "t1")
    assert store.start_job(application_id, "resume", "t2") == (False, "t1")
    assert store.get_job(application_id, "resume")["started_at"] == "t1"


@pytest.mark.parametrize("outcome", ["done", "failed"])
def test_reclaim_after_finishing_clears_the_result(store, outcome):
    application_id, _ = store.record(row())
    store.start_job(application_id, "resume", "t1")
    store.finish_job(application_id, "resume", "t1", outcome, saved_path="/a.pdf", error="x", result={"match": MATCH})
    assert store.start_job(application_id, "resume", "t2") == (True, "t2")
    assert store.get_job(application_id, "resume") == {
        "status": "running", "started_at": "t2", "finished_at": None, "saved_path": None, "error": None}


def test_claim_for_unknown_application_stores_nothing(store, db_path):
    assert store.start_job(str(uuid.uuid4()), "resume", "t1") == (False, None)
    assert jobs(db_path) == []


def test_kinds_are_claimed_independently(store, db_path):
    application_id, _ = store.record(row())
    assert store.start_job(application_id, "resume", "t1")[0]
    assert store.start_job(application_id, "cover_letter", "t2")[0]
    assert jobs(db_path) == [(application_id, "cover_letter", "running"), (application_id, "resume", "running")]


def test_concurrent_claims_start_one_run(store):
    application_id, _ = store.record(row())
    barrier = threading.Barrier(8)
    claimed = []

    def claim(n):
        barrier.wait()
        claimed.append(store.start_job(application_id, "resume", f"t{n}")[0])

    threads = [threading.Thread(target=claim, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert claimed.count(True) == 1


def test_finish_records_done_with_result(store):
    application_id, _ = store.record(row())
    store.start_job(application_id, "resume", "t1")
    assert store.finish_job(application_id, "resume", "t1", "done", saved_path="/a.pdf", result={"match": MATCH})
    job = store.get_job(application_id, "resume")
    assert job["finished_at"] and job["error"] is None
    assert {k: job[k] for k in ("status", "saved_path", "match")} == {"status": "done", "saved_path": "/a.pdf", "match": MATCH}


def test_finish_records_failed_with_error(store):
    application_id, _ = store.record(row())
    store.start_job(application_id, "cover_letter", "t1")
    assert store.finish_job(application_id, "cover_letter", "t1", "failed", error="Cover letter generation failed")
    job = store.get_job(application_id, "cover_letter")
    assert (job["status"], job["error"], job["saved_path"]) == ("failed", "Cover letter generation failed", None)
    assert "text" not in job


def test_finish_with_text(store):
    application_id, _ = store.record(row())
    store.start_job(application_id, "cover_letter", "t1")
    store.finish_job(application_id, "cover_letter", "t1", "done", saved_path="/l.pdf", result={"text": "Dear"})
    assert store.get_job(application_id, "cover_letter")["text"] == "Dear"


def test_finish_for_another_run_changes_nothing(store):
    application_id, _ = store.record(row())
    store.start_job(application_id, "resume", "t1")
    assert not store.finish_job(application_id, "resume", "t0", "done", saved_path="/a.pdf")
    assert store.get_job(application_id, "resume")["status"] == "running"


def test_get_job_unknown_application_or_no_job(store):
    assert store.get_job(str(uuid.uuid4()), "resume") is None
    application_id, _ = store.record(row())
    store.start_job(application_id, "resume", "t1")
    assert store.get_job(application_id, "cover_letter") == NO_JOB


def test_delete_removes_jobs_and_a_late_finish_recreates_nothing(store, db_path):
    application_id, _ = store.record(row())
    store.start_job(application_id, "resume", "t1")
    store.start_job(application_id, "cover_letter", "t2")
    store.finish_job(application_id, "cover_letter", "t2", "done", saved_path="/l.pdf", result={"text": "x"})
    assert store.delete(application_id)
    assert jobs(db_path) == []
    assert not store.finish_job(application_id, "resume", "t1", "done", saved_path="/a.pdf")
    assert jobs(db_path) == [] and store.get_job(application_id, "resume") is None


def test_reopening_fails_only_running_jobs(store, db_path):
    ids = [store.record(row(f"https://example.com/{n}"))[0] for n in range(3)]
    for application_id in ids:
        store.start_job(application_id, "resume", "t1")
    store.finish_job(ids[1], "resume", "t1", "done", saved_path="/a.pdf", result={"match": MATCH})
    store.finish_job(ids[2], "resume", "t1", "failed", error="Resume generation failed")
    before = [store.get_job(application_id, "resume") for application_id in ids[1:]]

    reopened = ApplicationStore(db_path)
    interrupted = reopened.get_job(ids[0], "resume")
    assert (interrupted["status"], interrupted["error"]) == ("failed", INTERRUPTED) and interrupted["finished_at"]
    assert [reopened.get_job(application_id, "resume") for application_id in ids[1:]] == before
    assert reopened.start_job(ids[0], "resume", "t2") == (True, "t2")


def test_job_failures_raise_store_error(store, db_path):
    db_path.unlink()
    db_path.mkdir()
    application_id = str(uuid.uuid4())
    for call in (lambda: store.start_job(application_id, "resume", "t"),
                 lambda: store.finish_job(application_id, "resume", "t", "done"),
                 lambda: store.get_job(application_id, "resume")):
        with pytest.raises(ApplicationStoreError):
            call()


# --- how an application was added ---

def origin(path, application_id):
    return stored(path, application_id)["added_via"]


def test_new_row_is_manual_unless_told_otherwise(store, db_path):
    manual, _ = store.record(row())
    by_link, _ = store.record({**row(), "job_link": GH + "/other", "added_via": "link"})
    assert origin(db_path, manual) == "manual" and origin(db_path, by_link) == "link"


def test_origin_survives_updates_and_duplicates(store, db_path):
    application_id, _ = store.record(row())
    store.update(application_id, {"status": "applied", "salary": "$1"})
    store.record({**row(), "added_via": "link"})
    assert origin(db_path, application_id) == "manual"


def test_origin_listed_and_read_back(store):
    application_id, _ = store.record({**row(), "added_via": "link"})
    assert store.get(application_id)["added_via"] == "link"
    assert store.list_with_reports()[0]["added_via"] == "link"


def test_store_from_before_the_origin_gains_it_as_manual(store, db_path):
    application_id, _ = store.record(row())
    before = stored(db_path, application_id)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("ALTER TABLE applications DROP COLUMN added_via")
    ApplicationStore(db_path)
    assert stored(db_path, application_id) == {**before, "added_via": "manual"}


def test_restart_after_the_origin_migration_changes_nothing(store, db_path):
    application_id, _ = store.record({**row(), "added_via": "link"})
    ApplicationStore(db_path)
    assert origin(db_path, application_id) == "link"


def test_store_from_before_statuses_reads_as_manual(old_store_path):
    ids = ApplicationStore(old_store_path).legacy_ids()
    assert ids and all(origin(old_store_path, application_id) == "manual" for application_id in ids.values())


def test_store_with_integer_ids_reads_as_manual(int_store_path):
    ids = ApplicationStore(int_store_path).legacy_ids()
    assert ids and all(origin(int_store_path, application_id) == "manual" for application_id in ids.values())


# --- Email status matching and updates ---

def candidate(company, role, job_link=GH, application_id=None):
    return {"id": application_id or str(uuid.uuid4()), "job_link_key": dedupe_key(job_link),
            "company": company, "role": role}


@pytest.mark.parametrize(("stored_name", "sent", "kind"), [
    ("Ramp Business Corporation, Inc.", "ramp business corporation", "company"),
    ("The Acme Company", "ACME", "company"),
    ("Café & Co. GmbH", "cafe and co", "company"),
    ("Sr. Software Engineer - Payments", "Senior Software Engineer, Payments", "role"),
    ("Jr  Data   Analyst", "junior data analyst", "role"),
])
def test_names_equal_after_normalization(stored_name, sent, kind):
    assert normalize_name(stored_name, kind) == normalize_name(sent, kind)


def test_suffix_alone_is_kept():
    assert normalize_name("Co", "company") == "co"
    assert normalize_name("The", "company") == "the"


def test_company_suffix_and_case_match():
    rows = [candidate("Ramp Business Corporation, Inc.", "Applied AI Engineer")]
    assert match_applications(rows, "ramp business corporation", "Applied AI Engineer", None) == rows


def test_role_punctuation_and_abbreviation_match():
    rows = [candidate("Acme", "Sr. Software Engineer - Payments")]
    assert match_applications(rows, "Acme", "Senior Software Engineer, Payments", None) == rows


def test_small_typo_matches():
    rows = [candidate("Ramp", "Applied AI Engineer")]
    assert match_applications(rows, "Ramp", "Applied AI Enginer", None) == rows
    databricks = [candidate("Databricks", "Applied AI Engineer")]
    assert match_applications(databricks, "Databrick", "Applied AI Engineer", None) == databricks


def test_short_name_typo_is_not_close_enough():
    rows = [candidate("Ramp", "Applied AI Engineer")]
    assert match_applications(rows, "Rammp", "Applied AI Engineer", None) == []


def test_different_role_at_same_company_does_not_match():
    rows = [candidate("Ramp", "Product Designer")]
    assert match_applications(rows, "Ramp", "Applied AI Engineer", None) == []


def test_different_company_does_not_match():
    rows = [candidate("Ramp", "Applied AI Engineer")]
    assert match_applications(rows, "Brex", "Applied AI Engineer", None) == []


def test_link_decides_between_equal_names():
    first = candidate("Ramp", "Applied AI Engineer", GH)
    second = candidate("Ramp", "Applied AI Engineer", "https://job-boards.greenhouse.io/acme/jobs/456")
    assert match_applications([first, second], "Ramp", "Applied AI Engineer", GH + "/?utm_source=x") == [first]


def test_link_decides_even_against_names():
    linked = candidate("Ramp", "Applied AI Engineer", GH)
    assert match_applications([linked], "Someone Else", "Other Role", GH) == [linked]


def test_unknown_link_falls_back_to_names():
    rows = [candidate("Ramp", "Applied AI Engineer", GH)]
    assert match_applications(rows, "Ramp", "Applied AI Engineer", "https://example.com/other") == rows


def test_exact_match_beats_near_match():
    exact = candidate("Ramp", "Applied AI Engineer")
    near = candidate("Ramp", "Applied AI Engineers", "https://job-boards.greenhouse.io/acme/jobs/456")
    assert match_applications([exact, near], "Ramp", "Applied AI Engineer", None) == [exact]


def test_equal_names_are_all_returned():
    first = candidate("Ramp", "Applied AI Engineer", GH)
    second = candidate("Ramp", "Applied AI Engineer", "https://job-boards.greenhouse.io/acme/jobs/456")
    assert len(match_applications([first, second], "Ramp", "Applied AI Engineer", None)) == 2


def test_punctuation_only_name_matches_nothing():
    rows = [candidate("Ramp", "Applied AI Engineer")]
    assert match_applications(rows, "!!!", "Applied AI Engineer", None) == []


STATUSES = ("verified", "applied", "interviewing", "offer", "rejected", "withdrawn")
TRANSITIONS = {
    "Applied": dict(zip(STATUSES, STATUSES)),
    "Rejected": {"verified": "rejected", "applied": "rejected", "interviewing": "rejected", "offer": "rejected",
                 "rejected": "rejected", "withdrawn": "withdrawn"},
    "Response": {"verified": "interviewing", "applied": "interviewing", "interviewing": "interviewing",
                 "offer": "offer", "rejected": "rejected", "withdrawn": "withdrawn"},
}


@pytest.mark.parametrize("email_status", sorted(TRANSITIONS))
@pytest.mark.parametrize("current", STATUSES)
def test_email_status_transitions(current, email_status):
    assert email_status_target(current, email_status) == TRANSITIONS[email_status][current]


def test_email_status_updates_only_status(store, db_path):
    application_id, _ = store.record(row(company="Ramp", role="Applied AI Engineer", salary="$1"))
    before = stored(db_path, application_id)
    result = store.apply_email_status("ramp", "applied ai engineer", None, "Response")
    assert result.match_count == 1 and result.application_id == application_id
    assert (result.company, result.role) == ("Ramp", "Applied AI Engineer")
    assert (result.previous_status, result.status, result.changed) == ("verified", "interviewing", True)
    after = stored(db_path, application_id)
    assert after["status"] == "interviewing" and after["updated_at"]
    assert {k: v for k, v in after.items() if k not in ("status", "updated_at")} == \
        {k: v for k, v in before.items() if k not in ("status", "updated_at")}


def test_unchanged_status_keeps_updated_at(store, db_path):
    application_id, _ = store.record(row())
    store.update(application_id, {"status": "applied"})
    before = stored(db_path, application_id)
    result = store.apply_email_status("Acme", "Engineer", None, "Applied")
    assert (result.previous_status, result.status, result.changed) == ("applied", "applied", False)
    assert stored(db_path, application_id) == before


def test_repeated_rejection_changes_once(store):
    store.record(row())
    assert store.apply_email_status("Acme", "Engineer", None, "Rejected").changed is True
    second = store.apply_email_status("Acme", "Engineer", None, "Rejected")
    assert (second.status, second.changed) == ("rejected", False)


def test_no_match_writes_nothing(store, db_path):
    application_id, _ = store.record(row())
    before = stored(db_path, application_id)
    result = store.apply_email_status("Brex", "Engineer", None, "Rejected")
    assert result.match_count == 0 and result.application_id is None
    assert stored(db_path, application_id) == before


def test_ambiguous_match_writes_nothing(store, db_path):
    first, _ = store.record(row())
    second, _ = store.record(row(job_link="https://job-boards.greenhouse.io/acme/jobs/456"))
    before = (stored(db_path, first), stored(db_path, second))
    result = store.apply_email_status("Acme", "Engineer", None, "Rejected")
    assert result.match_count == 2 and result.application_id is None
    assert (stored(db_path, first), stored(db_path, second)) == before


def test_link_resolves_ambiguity_in_store(store):
    store.record(row())
    second, _ = store.record(row(job_link="https://job-boards.greenhouse.io/acme/jobs/456"))
    result = store.apply_email_status("Acme", "Engineer", "https://job-boards.greenhouse.io/acme/jobs/456/", "Rejected")
    assert result.application_id == second and result.status == "rejected"


def test_unknown_email_status_refused(store):
    with pytest.raises(ValueError):
        store.apply_email_status("Acme", "Engineer", None, "Offer")


@pytest.mark.parametrize("first", ["Rejected", "Response"])
def test_concurrent_emails_end_rejected(store, db_path, first):
    application_id, _ = store.record(row())
    store.update(application_id, {"status": "applied"})
    barrier = threading.Barrier(2)
    errors = []

    def worker(email_status):
        try:
            barrier.wait()
            store.apply_email_status("Acme", "Engineer", None, email_status)
        except Exception as exc:  # surfaced below
            errors.append(exc)

    order = [first, "Response" if first == "Rejected" else "Rejected"]
    threads = [threading.Thread(target=worker, args=(s,)) for s in order]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    assert stored(db_path, application_id)["status"] == "rejected"


def test_email_status_read_failure_raises_store_error(store, db_path):
    db_path.unlink()
    db_path.mkdir()
    with pytest.raises(ApplicationStoreError):
        store.apply_email_status("Acme", "Engineer", None, "Rejected")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_email_status_write_failure_raises_store_error(store, db_path):
    store.record(row())
    db_path.chmod(0o400)
    try:
        with pytest.raises(ApplicationStoreError):
            store.apply_email_status("Acme", "Engineer", None, "Rejected")
    finally:
        db_path.chmod(0o600)
