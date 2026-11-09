from scripts.validate_dependency_locks import (
    LOCK_FILES,
    _validate_lock,
    _validate_source,
    main,
)


def test_checked_in_dependency_locks_are_valid():
    assert all(_validate_lock(lock) == [] for lock in LOCK_FILES)
    assert main() == 0


def test_dependency_lock_accepts_exact_version_and_sha256(tmp_path):
    lock = tmp_path / "lock.txt"
    lock.write_text(
        "example-package==1.2.3 \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    assert _validate_lock(lock) == []


def test_dependency_lock_rejects_unhashed_dependency(tmp_path):
    lock = tmp_path / "lock.txt"
    lock.write_text("example-package==1.2.3\n", encoding="utf-8")
    assert any("no SHA-256 hash" in error for error in _validate_lock(lock))


def test_dependency_lock_rejects_unpinned_dependency(tmp_path):
    lock = tmp_path / "lock.txt"
    lock.write_text(
        "example-package>=1.2.3 \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    assert any("exact == pin" in error for error in _validate_lock(lock))


def test_dependency_lock_rejects_orphan_hash(tmp_path):
    lock = tmp_path / "lock.txt"
    lock.write_text(
        "    --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    assert any("orphaned hash" in error for error in _validate_lock(lock))


def test_dependency_source_rejects_unpinned_dependency(tmp_path):
    source = tmp_path / "requirements.in"
    source.write_text("example-package>=1.2.3\n", encoding="utf-8")
    assert any("exact == pin" in error for error in _validate_source(source))
