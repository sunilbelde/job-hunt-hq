import os
import sqlite3
import stat
import threading

import pytest

from app.applications import ApplicationStore, dedupe_key
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
