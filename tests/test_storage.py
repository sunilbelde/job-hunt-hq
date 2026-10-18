import stat

import pytest

from app.applications import ApplicationStore
from app.storage import RESUME_FILE_NAME, LocalStorage, StorageError, company_folder


@pytest.fixture
def root(tmp_path):
    return tmp_path / "out"


@pytest.fixture
def storage(root):
    return LocalStorage(root)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


# --- company_folder ---

@pytest.mark.parametrize("company,folder", [
    ("Acme Corp", "Acme Corp"),
    ("Café Zürich", "Café Zürich"),
    ("AT&T / Mobility: West", "AT&T - Mobility- West"),
    ("Back\\slash", "Back-slash"),
    ("Tab\there\nnewline", "Tab-here-newline"),
    ("../../etc", "-..-etc"),
    ("/etc/passwd", "-etc-passwd"),
    ("..", "unknown-company"),
    ("", "unknown-company"),
    ("   ", "unknown-company"),
    (" . Acme Inc. ", "Acme Inc"),
    ("applications.sqlite3", "_applications.sqlite3"),
    ("Applications.SQLite3-wal", "_Applications.SQLite3-wal"),
    ("applications", "applications"),
])
def test_company_folder(company, folder):
    assert company_folder(company) == folder


def test_company_folder_cut_to_100_characters():
    assert company_folder("a" * 300) == "a" * 100
    # Trimmed again after the cut, so the name never ends in a space or dot.
    assert company_folder("a" * 99 + " b") == "a" * 99


# --- save_resume ---

def test_save_resume_path_and_content(storage, root):
    path = storage.save_resume("Acme Corp", 7, b"%PDF-1")
    assert path == root.resolve() / "Acme Corp" / "7" / RESUME_FILE_NAME
    assert path.is_absolute()
    assert path.read_bytes() == b"%PDF-1"


def test_two_applications_at_one_company(storage, root):
    a = storage.save_resume("Acme Corp", 7, b"a")
    b = storage.save_resume("Acme Corp", 9, b"b")
    assert a.parent.parent == b.parent.parent == root.resolve() / "Acme Corp"
    assert (a.read_bytes(), b.read_bytes()) == (b"a", b"b")


def test_regenerate_replaces_file(storage):
    first = storage.save_resume("Acme", 7, b"first")
    second = storage.save_resume("Acme", 7, b"second")
    assert first == second
    assert second.read_bytes() == b"second"
    assert [p.name for p in second.parent.iterdir()] == [RESUME_FILE_NAME]


def test_failed_write_keeps_previous_and_removes_temp(storage, monkeypatch):
    path = storage.save_resume("Acme", 7, b"first")

    def boom(src, dst):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("app.storage.os.replace", boom)
    with pytest.raises(StorageError):
        storage.save_resume("Acme", 7, b"second")
    assert path.read_bytes() == b"first"
    assert [p.name for p in path.parent.iterdir()] == [RESUME_FILE_NAME]


def test_folders_and_file_private(storage, root):
    path = storage.save_resume("Acme", 7, b"x")
    for folder in (root, path.parent.parent, path.parent):
        assert mode(folder) == 0o700
    assert mode(path) == 0o600


def test_traversal_company_stays_inside_root(storage, root, tmp_path):
    path = storage.save_resume("../../escape", 7, b"x")
    assert path.is_relative_to(root.resolve())
    assert not (tmp_path / "escape").exists()


def test_store_named_company_leaves_store_untouched(storage, root):
    store_path = root / "applications.sqlite3"
    store = ApplicationStore(store_path)
    before = store_path.read_bytes()
    path = storage.save_resume("applications.sqlite3", 1, b"x")
    assert path.parent.parent.name == "_applications.sqlite3"
    assert store_path.is_file() and store_path.read_bytes() == before
    assert store.get(1) is None


def test_company_folder_blocked_by_a_file_raises(storage, root):
    (root / "Acme").write_text("not a folder")
    with pytest.raises(StorageError):
        storage.save_resume("Acme", 7, b"x")


def test_unwritable_root_fails_naming_output_dir(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir(mode=0o500)
    try:
        with pytest.raises(StorageError, match="OUTPUT_DIR"):
            LocalStorage(ro / "out")
    finally:
        ro.chmod(0o700)


def test_startup_does_not_create_outputs_dir(storage, root):
    assert not (root / "outputs").exists()
