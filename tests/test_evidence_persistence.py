from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from backend.orchestration import latency_evidence
from backend.cli import _write_experiment_log


def _configure_directories(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    results = tmp_path / "results"
    reports = tmp_path / "reports"
    results.mkdir()
    reports.mkdir()
    results.chmod(0o2750)
    reports.chmod(0o2750)
    monkeypatch.setattr(latency_evidence, "JSON_OUTPUT_DIR", results)
    monkeypatch.setattr(latency_evidence, "MARKDOWN_OUTPUT_DIR", reports)
    monkeypatch.setenv("INTENTFLOW_EVIDENCE_GID", str(os.getegid()))
    return results, reports


def _persist(results_id: str) -> tuple[Path, Path]:
    now = datetime.now(timezone.utc)
    return latency_evidence.persist_latency_execution(
        None,
        execution_id=results_id,
        started_at=now,
        completed_at=now,
    )


def test_existing_evidence_is_never_overwritten(monkeypatch, tmp_path: Path):
    results, reports = _configure_directories(monkeypatch, tmp_path)
    execution_id = "a" * 32
    existing_json = results / f"generalized_latency_{execution_id}.json"
    existing_json.write_text("preserve this evidence\n", encoding="utf-8")
    existing_json.chmod(0o600)

    with pytest.raises(
        latency_evidence.EvidencePersistenceError,
        match="already exists",
    ):
        _persist(execution_id)

    assert existing_json.read_text(encoding="utf-8") == "preserve this evidence\n"
    assert stat.S_IMODE(existing_json.stat().st_mode) == 0o600
    assert list(reports.iterdir()) == []
    assert not list(results.glob("*.tmp"))
    assert not list(reports.glob("*.tmp"))


def test_racing_report_conflict_preserves_conflict_and_rolls_back_own_json(
    monkeypatch,
    tmp_path: Path,
):
    results, reports = _configure_directories(monkeypatch, tmp_path)
    execution_id = "b" * 32
    report_path = reports / f"generalized_latency_{execution_id}.md"
    real_link = os.link
    calls = 0

    def publish_with_racing_conflict(source, destination, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            Path(destination).write_text("concurrent evidence\n", encoding="utf-8")
            raise FileExistsError("simulated concurrent publisher")
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(latency_evidence.os, "link", publish_with_racing_conflict)

    with pytest.raises(
        latency_evidence.EvidencePersistenceError,
        match="already exists",
    ):
        _persist(execution_id)

    assert report_path.read_text(encoding="utf-8") == "concurrent evidence\n"
    assert not (results / f"generalized_latency_{execution_id}.json").exists()
    assert not list(results.iterdir())
    assert list(reports.iterdir()) == [report_path]


def test_single_evidence_publication_is_exclusive(monkeypatch, tmp_path: Path):
    results, _ = _configure_directories(monkeypatch, tmp_path)
    target = results / "run_123.json"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o600)

    with pytest.raises(
        latency_evidence.EvidencePersistenceError,
        match="will not be overwritten",
    ):
        latency_evidence.persist_evidence_file(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_legacy_cli_log_uses_configured_json_directory(monkeypatch, tmp_path: Path):
    results = tmp_path / "results"
    results.mkdir()
    results.chmod(0o2750)
    monkeypatch.setattr(latency_evidence, "JSON_OUTPUT_DIR", results)
    monkeypatch.setenv("INTENTFLOW_EVIDENCE_GID", str(os.getegid()))

    written = _write_experiment_log({"execution_id": "legacy"})

    assert written.parent == results
    assert written.name.startswith("run_")
    assert written.read_text(encoding="utf-8") == '{\n  "execution_id": "legacy"\n}\n'
    assert stat.S_IMODE(written.stat().st_mode) == 0o640


def test_permission_validator_accepts_actual_owner_group_and_read_only_modes(
    tmp_path: Path,
):
    directory = tmp_path / "evidence"
    directory.mkdir()
    directory.chmod(0o2750)
    evidence_file = directory / "execution.json"
    evidence_file.write_text("{}", encoding="utf-8")
    evidence_file.chmod(0o640)

    latency_evidence.validate_evidence_permissions(
        directory.lstat(),
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        expected_mode=0o2750,
        directory=True,
    )
    latency_evidence.validate_evidence_permissions(
        evidence_file.lstat(),
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
        expected_mode=0o640,
        directory=False,
    )
    assert directory.stat().st_mode & stat.S_IWGRP == 0
    assert evidence_file.stat().st_mode & stat.S_IWGRP == 0


def test_permission_validator_checks_root_api_group_target_model():
    api_gid = 12345
    root_api_directory = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o2750,
        st_uid=0,
        st_gid=api_gid,
    )
    root_api_file = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o640,
        st_uid=0,
        st_gid=api_gid,
    )

    latency_evidence.validate_evidence_permissions(
        root_api_directory,
        expected_uid=0,
        expected_gid=api_gid,
        expected_mode=0o2750,
        directory=True,
    )
    latency_evidence.validate_evidence_permissions(
        root_api_file,
        expected_uid=0,
        expected_gid=api_gid,
        expected_mode=0o640,
        directory=False,
    )

    unsafe_directory = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o2770,
        st_uid=0,
        st_gid=api_gid,
    )
    with pytest.raises(
        latency_evidence.EvidencePersistenceError,
        match="unexpected type, ownership, or permissions",
    ):
        latency_evidence.validate_evidence_permissions(
            unsafe_directory,
            expected_uid=0,
            expected_gid=api_gid,
            expected_mode=0o2750,
            directory=True,
        )


def test_permission_validator_rejects_symlink_metadata():
    symlink = SimpleNamespace(
        st_mode=stat.S_IFLNK | 0o777,
        st_uid=0,
        st_gid=12345,
    )

    with pytest.raises(
        latency_evidence.EvidencePersistenceError,
        match="unexpected type, ownership, or permissions",
    ):
        latency_evidence.validate_evidence_permissions(
            symlink,
            expected_uid=0,
            expected_gid=12345,
            expected_mode=0o2750,
            directory=True,
        )
