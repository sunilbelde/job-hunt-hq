import stat

import pytest

from app.applications import ApplicationStore
from app.storage import (
    COVER_LETTER_FILE_NAME,
    RESUME_FILE_NAME,
    LocalStorage,
    StorageError,
    company_folder,
    cover_letter_path,
    rename_legacy_folders,
)

A = "3f2b9c1e-8d4a-4c6e-9b1f-2a7d5e8c0b13"
B = "9a1c7e2d-5b3f-4e8a-a6d0-1c2b3d4e5f60"


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
    path = storage.save_resume("Acme Corp", A, b"%PDF-1")
    assert path == root.resolve() / "Acme Corp" / A / RESUME_FILE_NAME
    assert path.is_absolute()
    assert path.read_bytes() == b"%PDF-1"


def test_two_applications_at_one_company(storage, root):
    a = storage.save_resume("Acme Corp", A, b"a")
    b = storage.save_resume("Acme Corp", B, b"b")
    assert a.parent.parent == b.parent.parent == root.resolve() / "Acme Corp"
    assert (a.read_bytes(), b.read_bytes()) == (b"a", b"b")


def test_regenerate_replaces_file(storage):
    first = storage.save_resume("Acme", A, b"first")
    second = storage.save_resume("Acme", A, b"second")
    assert first == second
    assert second.read_bytes() == b"second"
    assert [p.name for p in second.parent.iterdir()] == [RESUME_FILE_NAME]


def test_failed_write_keeps_previous_and_removes_temp(storage, monkeypatch):
    path = storage.save_resume("Acme", A, b"first")

    def boom(src, dst):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr("app.storage.os.replace", boom)
    with pytest.raises(StorageError):
        storage.save_resume("Acme", A, b"second")
    assert path.read_bytes() == b"first"
    assert [p.name for p in path.parent.iterdir()] == [RESUME_FILE_NAME]


def test_folders_and_file_private(storage, root):
    path = storage.save_resume("Acme", A, b"x")
    for folder in (root, path.parent.parent, path.parent):
        assert mode(folder) == 0o700
    assert mode(path) == 0o600


@pytest.mark.parametrize("company,folder", [
    ("Acme Corp", "Acme Corp"),
    ("AT&T / Mobility: West", "AT&T - Mobility- West"),
])
def test_cover_letter_path_beside_resume(storage, root, company, folder):
    resume = storage.save_resume(company, A, b"x")
    path = cover_letter_path(resume)
    assert path == root.resolve() / folder / A / COVER_LETTER_FILE_NAME
    assert COVER_LETTER_FILE_NAME == "SUNIL BELDE - Cover Letter.pdf"
    assert not path.exists()
    assert [p.name for p in resume.parent.iterdir()] == [RESUME_FILE_NAME]


def test_traversal_company_stays_inside_root(storage, root, tmp_path):
    path = storage.save_resume("../../escape", A, b"x")
    assert path.is_relative_to(root.resolve())
    assert not (tmp_path / "escape").exists()


def test_store_named_company_leaves_store_untouched(storage, root):
    store_path = root / "applications.sqlite3"
    store = ApplicationStore(store_path)
    before = store_path.read_bytes()
    path = storage.save_resume("applications.sqlite3", A, b"x")
    assert path.parent.parent.name == "_applications.sqlite3"
    assert store_path.is_file() and store_path.read_bytes() == before
    assert store.get(A) is None


def test_company_folder_blocked_by_a_file_raises(storage, root):
    (root / "Acme").write_text("not a folder")
    with pytest.raises(StorageError):
        storage.save_resume("Acme", A, b"x")


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


# --- rename_legacy_folders ---

def legacy_resume(root, company, folder, content=b"%PDF-old"):
    path = root / company / folder / RESUME_FILE_NAME
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return path


def test_legacy_folder_renamed_with_content(root):
    legacy_resume(root, "Acme Corp", "1")
    assert rename_legacy_folders(root, {1: A}) == 1
    assert (root / "Acme Corp" / A / RESUME_FILE_NAME).read_bytes() == b"%PDF-old"
    assert not (root / "Acme Corp" / "1").exists()


def test_same_id_under_two_company_folders(root):
    legacy_resume(root, "Acme", "1", b"one")
    legacy_resume(root, "Acme Inc", "1", b"two")
    assert rename_legacy_folders(root, {1: A}) == 2
    assert (root / "Acme" / A / RESUME_FILE_NAME).read_bytes() == b"one"
    assert (root / "Acme Inc" / A / RESUME_FILE_NAME).read_bytes() == b"two"


def test_unmapped_and_other_folders_left_alone(root):
    legacy_resume(root, "Acme Corp", "5")
    legacy_resume(root, "Acme Corp", B)
    legacy_resume(root, "Acme Corp", "01")
    (root / "Beta").mkdir()
    (root / "Beta" / "1").write_text("a file, not a folder")
    assert rename_legacy_folders(root, {1: A}) == 0
    assert sorted(p.name for p in (root / "Acme Corp").iterdir()) == sorted(["5", B, "01"])
    assert (root / "Beta" / "1").is_file()


def test_existing_target_kept_and_logged(root, caplog):
    legacy_resume(root, "Acme Corp", "1", b"old")
    (root / "Acme Corp" / A).mkdir()  # even an empty target is not replaced
    assert rename_legacy_folders(root, {1: A}) == 0
    assert (root / "Acme Corp" / "1" / RESUME_FILE_NAME).read_bytes() == b"old"
    assert (root / "Acme Corp" / A).is_dir()
    assert "legacy_folder_conflict" in caplog.text


def test_second_run_changes_nothing(root):
    legacy_resume(root, "Acme Corp", "1")
    rename_legacy_folders(root, {1: A})
    before = sorted(str(p) for p in root.rglob("*"))
    assert rename_legacy_folders(root, {1: A}) == 0
    assert sorted(str(p) for p in root.rglob("*")) == before


def test_symlinked_company_not_followed(root, tmp_path):
    outside = tmp_path / "outside"
    legacy_resume(outside, "Acme", "1")
    root.mkdir()
    (root / "Linked").symlink_to(outside / "Acme")
    assert rename_legacy_folders(root, {1: A}) == 0
    assert (outside / "Acme" / "1").is_dir()


def test_rename_error_logged_not_raised(root, monkeypatch, caplog):
    legacy_resume(root, "Acme Corp", "1")

    def boom(src, dst):
        raise PermissionError("denied")
    monkeypatch.setattr("app.storage.os.rename", boom)
    assert rename_legacy_folders(root, {1: A}) == 0
    assert (root / "Acme Corp" / "1").is_dir()
    assert "legacy_folder_error" in caplog.text


def test_empty_mapping_touches_nothing(root):
    legacy_resume(root, "Acme Corp", "1")
    assert rename_legacy_folders(root, {}) == 0
    assert (root / "Acme Corp" / "1").is_dir()
