import os
import re
import stat
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from app.storage import LinkSigner, LocalStorage, StorageError, content_type_for

KEY_RE = re.compile(r"^outputs/\d{4}-\d{2}-\d{2}/[0-9a-f-]{36}\.json$")
SECRET = "x" * 32
BASE = "https://mac-mini.tail1234.ts.net"
DAY = 86400


@pytest.fixture
def signer():
    return LinkSigner(SECRET, BASE)


@pytest.fixture
def storage(tmp_path, signer):
    return LocalStorage(tmp_path / "out", signer)


def split_link(url):
    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    return parts.path.removeprefix("/files/"), query["expires"], query["sig"]


def age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


# --- LocalStorage writes ---

def test_upload_key_and_file(storage, tmp_path):
    key = storage.upload(b"{}", "application/json", "json")
    assert KEY_RE.match(key)
    assert (tmp_path / "out" / key).read_bytes() == b"{}"


def test_keys_are_unique(storage):
    assert storage.upload(b"x", "text/plain", "txt") != storage.upload(b"x", "text/plain", "txt")


def test_no_temp_files_left(storage, tmp_path):
    key = storage.upload(b"x", "application/pdf", "pdf")
    siblings = [p.name for p in (tmp_path / "out" / key).parent.iterdir()]
    assert not [n for n in siblings if n.startswith(".tmp-")]


def test_directories_private(storage, tmp_path):
    key = storage.upload(b"x", "application/pdf", "pdf")
    root = tmp_path / "out"
    for d in (root, root / "outputs", (root / key).parent):
        assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / key).stat().st_mode) == 0o600


def test_unwritable_root_fails_naming_output_dir(tmp_path, signer):
    ro = tmp_path / "ro"
    ro.mkdir(mode=0o500)
    try:
        with pytest.raises(StorageError, match="OUTPUT_DIR"):
            LocalStorage(ro / "out", signer)
    finally:
        ro.chmod(0o700)


def test_write_error_wrapped_and_temp_removed(storage, tmp_path, monkeypatch):
    def boom(src, dst):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("app.storage.os.replace", boom)
    with pytest.raises(StorageError):
        storage.upload(b"x", "application/pdf", "pdf")
    assert not [p for p in (tmp_path / "out").rglob(".tmp-*")]


# --- Link signing ---

def test_link_round_trip(storage):
    key = storage.upload(b"x", "application/pdf", "pdf")
    url = storage.presigned_url(key, 600)
    assert url.startswith(f"{BASE}/files/{key}?")
    k, expires, sig = split_link(url)
    assert k == key and storage.verify_link(key, expires, sig)


def test_link_uses_ttl(signer):
    _, expires, _ = split_link(signer.url("outputs/k.pdf", 123, now=1000))
    assert expires == "1123"


def test_expired_link_rejected(signer):
    _, expires, sig = split_link(signer.url("outputs/k.pdf", 60, now=1000))
    assert signer.verify("outputs/k.pdf", expires, sig, now=1059)
    assert not signer.verify("outputs/k.pdf", expires, sig, now=1060)


def test_tampered_link_rejected(signer):
    key, expires, sig = split_link(signer.url("outputs/k.pdf", 600))
    assert not signer.verify("outputs/other.pdf", expires, sig)
    assert not signer.verify(key, str(int(expires) + 1), sig)
    assert not signer.verify(key, expires, sig[:-1] + ("0" if sig[-1] != "0" else "1"))
    assert not signer.verify(key, expires, None)
    assert not signer.verify(key, None, sig)
    assert not signer.verify(key, "-5", sig)


def test_link_survives_restart(signer):
    key, expires, sig = split_link(signer.url("outputs/k.pdf", 600))
    assert LinkSigner(SECRET, BASE).verify(key, expires, sig)
    assert not LinkSigner("y" * 32, BASE).verify(key, expires, sig)


# --- Key validation ---

def test_path_for_valid_key(storage, tmp_path):
    key = storage.upload(b"x", "application/pdf", "pdf")
    assert storage.path_for(key) == (tmp_path / "out" / key).resolve()


@pytest.mark.parametrize("key", [
    "../etc/passwd",
    "outputs/../../etc/passwd",
    "/etc/passwd",
    "outputs/2026-01-01/../x.pdf",
    "outputs/2026-01-01/not-a-uuid.pdf",
    "outputs/2026-01-01/12345678-1234-1234-1234-123456789abc.PDF",
    "other/2026-01-01/12345678-1234-1234-1234-123456789abc.pdf",
])
def test_path_for_rejects_bad_keys(storage, key):
    with pytest.raises(ValueError):
        storage.path_for(key)


def test_content_type_for():
    assert content_type_for("outputs/d/k.pdf") == "application/pdf"
    assert content_type_for("outputs/d/k.json") == "application/json"


# --- Cleanup ---

def test_cleanup_deletes_old_keeps_recent(storage, tmp_path):
    old = tmp_path / "out" / storage.upload(b"old", "application/pdf", "pdf")
    recent = tmp_path / "out" / storage.upload(b"new", "application/pdf", "pdf")
    age(old, 31 * DAY)
    age(recent, 29 * DAY)
    assert storage.cleanup(30 * DAY) == 1
    assert not old.exists() and recent.exists()


def test_cleanup_removes_stale_temp_and_empty_dirs(storage, tmp_path):
    day = tmp_path / "out" / "outputs" / "2020-01-01"
    day.mkdir()
    stale = day / ".tmp-abc"
    stale.write_bytes(b"partial")
    age(stale, 2 * 3600)
    fresh_dir = tmp_path / "out" / "outputs" / "2020-01-02"
    fresh_dir.mkdir()
    fresh_tmp = fresh_dir / ".tmp-def"
    fresh_tmp.write_bytes(b"in progress")
    storage.cleanup(30 * DAY)
    assert not day.exists()
    assert fresh_tmp.exists()


def test_cleanup_leaves_application_store(storage, tmp_path):
    from app.applications import ApplicationStore

    db = tmp_path / "out" / "applications.sqlite3"
    application_id, _ = ApplicationStore(db).record({
        "company": "Acme", "role": "Engineer", "job_link": "https://example.com/jobs/1",
        "posting_source_type": "employer_site", "verification_method": "employer_site",
        "official_apply_url": "",
    })
    age(db, 31 * DAY)
    storage.cleanup(30 * DAY)
    assert db.exists()
    assert ApplicationStore(db).record({"job_link": "https://example.com/jobs/1"}) == (application_id, False)


def test_cleanup_errors_are_logged_not_raised(storage, tmp_path, monkeypatch, caplog):
    path = tmp_path / "out" / storage.upload(b"old", "application/pdf", "pdf")
    age(path, 31 * DAY)
    monkeypatch.setattr("pathlib.Path.unlink", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError("denied")))
    assert storage.cleanup(30 * DAY) == 0
    assert "cleanup_error" in caplog.text
