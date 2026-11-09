from pathlib import Path
import os
import stat
import shutil

import pytest

from scripts.migrate_evidence import migrate_evidence


EXECUTION_ID = "a" * 32


def test_migration_reports_conflict_and_preserves_existing_file(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    source_file = source / f"generalized_latency_{EXECUTION_ID}.json"
    destination_file = destination / source_file.name
    source_file.write_text('{"new": true}\n', encoding="utf-8")
    destination_file.write_text('{"existing": true}\n', encoding="utf-8")
    os.chmod(destination_file, 0o600)

    conflicts, imported = migrate_evidence(source, destination, os.getegid())

    assert conflicts == [str(destination_file)]
    assert imported == []
    assert destination_file.read_text(encoding="utf-8") == '{"existing": true}\n'
    assert stat.S_IMODE(destination_file.stat().st_mode) == 0o600


def test_migration_imports_only_new_evidence_and_sets_new_file_mode(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "existing"
    source.mkdir()
    destination.mkdir()
    os.chmod(destination, 0o2750)
    json_source = source / f"generalized_constraints_{EXECUTION_ID}.json"
    markdown_source = source / f"generalized_constraints_{EXECUTION_ID}.md"
    json_source.write_text("{}", encoding="utf-8")
    markdown_source.write_text("# evidence\n", encoding="utf-8")

    conflicts, imported = migrate_evidence(source, destination, os.getegid())

    assert conflicts == []
    assert len(imported) == 2
    assert stat.S_IMODE(destination.stat().st_mode) == 0o2750
    for target_name in (json_source.name, markdown_source.name):
        target = destination / target_name
        assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_migration_rejects_destination_symlink(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "destination"
    destination.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Symlink is not allowed"):
        migrate_evidence(source, destination, os.getegid())

    assert list(outside.iterdir()) == []


def test_migration_rejects_source_directory_symlink(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    source = tmp_path / "source"
    source.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Symlink is not allowed"):
        migrate_evidence(source, tmp_path / "destination", os.getegid())


def test_migration_skips_symlinked_source_evidence(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    outside = tmp_path / "outside.json"
    outside.write_text('{"outside": true}', encoding="utf-8")
    linked = source / f"generalized_latency_{EXECUTION_ID}.json"
    linked.symlink_to(outside)

    conflicts, imported = migrate_evidence(source, destination, os.getegid())

    assert conflicts == []
    assert imported == []
    assert not (destination / linked.name).exists()


def test_migration_cleans_temporary_file_after_copy_failure(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    source_file = source / f"generalized_latency_{EXECUTION_ID}.json"
    source_file.write_text("{}", encoding="utf-8")

    def fail_copy(_source, _destination):
        raise OSError("simulated partial copy")

    monkeypatch.setattr(shutil, "copyfileobj", fail_copy)

    with pytest.raises(OSError, match="simulated partial copy"):
        migrate_evidence(source, destination, os.getegid())

    assert list(destination.iterdir()) == []


def test_migration_rejects_source_mutation_during_copy_and_cleans_temp(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    source_file = source / f"generalized_latency_{EXECUTION_ID}.json"
    source_file.write_text("{}", encoding="utf-8")

    def mutate_source(_input_file, output_file):
        output_file.write(b"{}")
        source_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(shutil, "copyfileobj", mutate_source)

    with pytest.raises(OSError, match="Source evidence changed while being copied"):
        migrate_evidence(source, destination, os.getegid())

    assert list(destination.iterdir()) == []


def test_migration_does_not_create_new_destination_after_copy_failure(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "source"
    destination = tmp_path / "missing" / "destination"
    source.mkdir()
    destination.parent.mkdir()
    source_file = source / f"generalized_latency_{EXECUTION_ID}.json"
    source_file.write_text("{}", encoding="utf-8")

    def fail_copy(_source, _destination):
        raise OSError("simulated partial copy")

    monkeypatch.setattr(shutil, "copyfileobj", fail_copy)

    with pytest.raises(OSError, match="simulated partial copy"):
        migrate_evidence(source, destination, os.getegid())

    assert not destination.exists()


def test_migration_handles_exdev_as_copy_failure_and_cleans_temp(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    source_file = source / f"generalized_latency_{EXECUTION_ID}.json"
    source_file.write_text("{}", encoding="utf-8")

    def fail_cross_filesystem(_source, _target, **_kwargs):
        raise OSError("EXDEV: simulated cross-filesystem publish")

    monkeypatch.setattr(os, "link", fail_cross_filesystem)

    with pytest.raises(OSError, match="EXDEV"):
        migrate_evidence(source, destination, os.getegid())

    assert list(destination.iterdir()) == []


def test_migration_race_conflict_is_reported_and_temp_is_cleaned(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    source_file = source / f"generalized_latency_{EXECUTION_ID}.json"
    source_file.write_text("{}", encoding="utf-8")

    def report_race(_source, _target, **_kwargs):
        raise FileExistsError("target appeared during migration")

    monkeypatch.setattr(os, "link", report_race)

    conflicts, imported = migrate_evidence(source, destination, os.getegid())

    assert conflicts == [str(destination / source_file.name)]
    assert imported == []
    assert list(destination.iterdir()) == []


def test_migration_copies_legacy_execution_evidence(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o2750)
    legacy = source / "run_1793710625.json"
    legacy.write_text('{"execution_id": "1793710625"}\n', encoding="utf-8")

    conflicts, imported = migrate_evidence(source, destination, os.getegid())

    assert conflicts == []
    assert imported == [str(destination / legacy.name)]
    assert (destination / legacy.name).read_text(encoding="utf-8") == legacy.read_text(
        encoding="utf-8"
    )
    assert stat.S_IMODE((destination / legacy.name).stat().st_mode) == 0o640


def test_migration_rejects_unsafe_existing_destination_without_changing_it(
    tmp_path: Path,
):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    destination.chmod(0o777)

    with pytest.raises(ValueError, match="Existing evidence destination"):
        migrate_evidence(source, destination, os.getegid())

    assert stat.S_IMODE(destination.stat().st_mode) == 0o777


def test_migration_rejects_relative_destination_component_symlink(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    component = tmp_path / "component"
    component.symlink_to(outside, target_is_directory=True)
    destination = Path("component") / "destination"
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Symlink is not allowed"):
        migrate_evidence(source, destination, os.getegid())
