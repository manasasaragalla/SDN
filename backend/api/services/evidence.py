from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.api.schemas import ExecutionDetail, ExecutionSummary
from backend.orchestration.latency_evidence import (
    JSON_OUTPUT_DIR,
    MARKDOWN_OUTPUT_DIR,
)

_EVIDENCE_PATTERN = re.compile(
    r"^(?P<prefix>generalized_constraints|generalized_latency)_(?P<id>[0-9a-f]{32})\.json$"
)
_LEGACY_PATTERN = re.compile(r"^run_(?P<id>[0-9]+)\.json$")
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


class EvidenceError(RuntimeError):
    pass


class EvidenceNotFoundError(EvidenceError):
    pass


def list_executions(limit: int = 100) -> list[ExecutionSummary]:
    paths = _evidence_files()
    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    summaries: list[ExecutionSummary] = []
    for path in paths[:limit]:
        try:
            data = _read_document(path)
            summaries.append(_summary_for(path, data))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise EvidenceError(f"Could not read execution evidence {path.name}: {exc}") from exc
    return summaries


def get_execution(execution_id: str) -> ExecutionDetail:
    for path in _evidence_files():
        match = _EVIDENCE_PATTERN.match(path.name) or _LEGACY_PATTERN.match(path.name)
        if match and match.group("id") == execution_id:
            try:
                data = _read_document(path)
                return ExecutionDetail(
                    **_summary_for(path, data).model_dump(),
                    evidence=data,
                )
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise EvidenceError(
                    f"Could not read execution evidence {path.name}: {exc}"
                ) from exc
    raise EvidenceNotFoundError(f"No persisted execution evidence for {execution_id}.")


def _evidence_files() -> list[Path]:
    if not JSON_OUTPUT_DIR.exists():
        return []
    try:
        paths = []
        for path in JSON_OUTPUT_DIR.iterdir():
            if not (_EVIDENCE_PATTERN.match(path.name) or _LEGACY_PATTERN.match(path.name)):
                continue
            if path.is_symlink() or not path.is_file():
                raise EvidenceError(f"Refusing non-regular evidence file {path.name}.")
            paths.append(path)
        return paths
    except OSError as exc:
        raise EvidenceError(f"Could not list execution evidence: {exc}") from exc


def _read_document(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_EVIDENCE_BYTES:
        raise EvidenceError(f"Evidence file exceeds {MAX_EVIDENCE_BYTES} bytes.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EvidenceError("Evidence JSON must contain an object.")
    return data


def _summary_for(path: Path, data: dict[str, Any]) -> ExecutionSummary:
    evidence_match = _EVIDENCE_PATTERN.match(path.name)
    legacy_match = _LEGACY_PATTERN.match(path.name)
    if evidence_match:
        prefix = evidence_match.group("prefix")
        execution_id = str(data.get("execution_id") or evidence_match.group("id"))
        raw_status = data.get("execution_status")
        started = _parse_datetime(data.get("started_at"))
        completed = _parse_datetime(data.get("completed_at"))
        request = data.get("request")
        final = data.get("final")
        path_nodes = (
            final.get("selected_path", {}).get("nodes")
            if isinstance(final, dict)
            and isinstance(final.get("selected_path"), dict)
            else None
        )
        measurement = (
            final.get("connectivity", {}).get("measurement")
            if isinstance(final, dict)
            and isinstance(final.get("connectivity"), dict)
            else None
        )
        markdown_name = f"{prefix}_{evidence_match.group('id')}.md"
    elif legacy_match:
        execution_id = str(data.get("execution_id") or legacy_match.group("id"))
        raw_status = _legacy_status(data)
        started = _parse_datetime(data.get("timestamp"))
        completed = None
        request = {"natural_language": data.get("raw_intent")}
        path_nodes = data.get("selected_path")
        measurement = data.get("final_measurement")
        markdown_name = None
    else:
        raise EvidenceError("Evidence file name did not match an allowed format.")

    markdown_path = MARKDOWN_OUTPUT_DIR / markdown_name if markdown_name else None
    return ExecutionSummary(
        execution_id=execution_id,
        submitted_intent=request if isinstance(request, (dict, str)) else None,
        started_at=started,
        completed_at=completed,
        status=raw_status if isinstance(raw_status, str) else "UNKNOWN",
        selected_path=path_nodes if isinstance(path_nodes, list) else None,
        final_measurement=measurement if isinstance(measurement, dict) else None,
        evidence_json=path.name,
        evidence_markdown=(
            markdown_name
            if markdown_path is not None and markdown_path.is_file()
            else None
        ),
    )


def _legacy_status(data: dict[str, Any]) -> str:
    if data.get("error"):
        return "FAILED"
    if data.get("intent_satisfied") is True:
        return "SUCCEEDED"
    return "UNKNOWN"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
