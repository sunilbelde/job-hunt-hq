import os
import sqlite3
import stat
import threading
from contextlib import closing

import pytest

from app.applications import FIELDS, ApplicationStore, ApplicationStoreError, dedupe_key
from app.storage import StorageError

GH = "https://job-boards.greenhouse.io/acme/jobs/123"


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
    assert created and application_id > 0
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


def test_different_links_get_increasing_ids(store):
    first, _ = store.record(row(GH))
    second, _ = store.record(row(GH.replace("123", "456")))
    assert second > first


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
    for n in (1, 2):
        saved = stored(old_store_path, n)
        assert saved["status"] == "verified" and saved["updated_at"] is None
        assert saved["job_link"] == f"https://example.com/jobs/{n}/" and saved["salary"] == f"${n}"
        assert saved["created_at"] == "2026-10-01T00:00:00Z"
    assert store.update(1, {"status": "applied"}) == "applied"
    assert store.delete(2)


def test_reopening_migrated_store_keeps_statuses(old_store_path):
    ApplicationStore(old_store_path)
    with closing(sqlite3.connect(old_store_path)) as conn, conn:
        conn.execute("UPDATE applications SET status = 'offer' WHERE id = 1")
    ApplicationStore(old_store_path)
    assert stored(old_store_path, 1)["status"] == "offer"


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
    assert stored(old_store_path, 1)["status"] == "verified"


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
    assert store.update(999, {"status": "applied"}) is None
    assert store.delete(999) is False
    assert store.exists(999) is False


def test_delete_frees_link_for_new_row(store, db_path):
    application_id, _ = store.record(row())
    assert store.exists(application_id)
    assert store.delete(application_id)
    assert not store.exists(application_id)
    variant = GH + "/?utm_source=x"
    new_id, created = store.record(row(variant))
    assert created and new_id > application_id
    assert stored(db_path, new_id)["job_link"] == variant
    assert stored(db_path, new_id)["status"] == "verified"


def test_ids_not_reused_after_deleting_newest(store):
    store.record(row(GH.replace("123", "1")))
    newest, _ = store.record(row(GH.replace("123", "2")))
    store.delete(newest)
    replacement, _ = store.record(row(GH.replace("123", "3")))
    assert replacement > newest


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
        store.exists(1)


def test_get_returns_stored_row_without_key(store):
    application_id, _ = store.record(row(salary="$1"))
    got = store.get(application_id)
    assert got["id"] == application_id
    assert got["company"] == "Acme" and got["job_link"] == GH and got["salary"] == "$1"
    assert got["location"] is None and got["status"] == "verified" and got["updated_at"] is None
    assert got["created_at"]
    assert "job_link_key" not in got
    assert set(got) == {"id", "job_link", *FIELDS, "status", "created_at", "updated_at"}


def test_get_missing_or_deleted_is_none(store):
    assert store.get(999) is None
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
        store.get(1)
