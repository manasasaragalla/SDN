"""Persistence for generalized latency execution evidence."""

from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

from backend.execution.preflight import (
    canonical_topology_fingerprint,
    topology_snapshot_fingerprint,
)
from backend.models.fingerprints import model_fingerprint
from backend.planner.candidate_selection import (
    CandidateSelectionResult,
    SelectionMethod,
    assess_path_feasibility,
    physical_candidate_id,
)
from backend.planner.constraint_evaluation import (
    ObservationStatus,
    physical_path_fingerprint,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _configured_evidence_directory(variable: str, default: Path) -> Path:
    configured = os.environ.get(variable)
    directory = Path(configured) if configured else default
    if not directory.is_absolute():
        raise ValueError(f"{variable} must be an absolute path.")
    return directory


JSON_OUTPUT_DIR = _configured_evidence_directory(
    "INTENTFLOW_EVIDENCE_JSON_DIR",
    PROJECT_ROOT / "evaluation" / "results",
)
MARKDOWN_OUTPUT_DIR = _configured_evidence_directory(
    "INTENTFLOW_EVIDENCE_MARKDOWN_DIR",
    PROJECT_ROOT / "docs" / "reports",
)
EVIDENCE_FILE_MODE = 0o640
EVIDENCE_DIRECTORY_MODE = 0o2750


class EvidencePersistenceError(RuntimeError):
    """Raised when an execution record cannot be durably written."""


def persist_latency_execution(
    result: Any | None,
    *,
    execution_id: str,
    started_at: datetime,
    completed_at: datetime,
    error: str | None = None,
    graph: Any | None = None,
    source: str = "h1",
    destination: str = "h4",
    configuration: dict[str, Any] | None = None,
    filename_prefix: str = "generalized_latency",
) -> tuple[Path, Path]:
    """Write an allowlisted JSON record and matching Markdown summary."""
    if not re.fullmatch(r"[0-9a-f]{32}", execution_id):
        raise ValueError("execution_id must be a lowercase UUID hex string")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", filename_prefix):
        raise ValueError("filename_prefix must be a lowercase identifier")

    document = _build_document(
        result,
        execution_id=execution_id,
        started_at=started_at,
        completed_at=completed_at,
        error=error,
        graph=graph,
        source=source,
        destination=destination,
        configuration=configuration or {},
    )
    json_path = JSON_OUTPUT_DIR / f"{filename_prefix}_{execution_id}.json"
    markdown_path = MARKDOWN_OUTPUT_DIR / f"{filename_prefix}_{execution_id}.md"
    encoded = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    markdown = _render_markdown(document)

    staged: list[tuple[Path, Path]] = []
    published: list[tuple[Path, tuple[int, int]]] = []
    try:
        _prepare_evidence_directory(JSON_OUTPUT_DIR)
        _prepare_evidence_directory(MARKDOWN_OUTPUT_DIR)
        for target, content in ((json_path, encoded), (markdown_path, markdown)):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                staged.append((temporary_path, target))
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
                _set_evidence_file_permissions(output.fileno())
        for temporary, target in staged:
            os.link(temporary, target)
            info = target.lstat()
            published.append((target, (info.st_dev, info.st_ino)))
            temporary.unlink()
        for directory in (JSON_OUTPUT_DIR, MARKDOWN_OUTPUT_DIR):
            _fsync_directory(directory)
    except FileExistsError as exc:
        _cleanup_staged(staged)
        _remove_owned_publications(published)
        raise EvidencePersistenceError(
            f"Execution evidence already exists for execution ID {execution_id}"
        ) from exc
    except OSError as exc:
        _cleanup_staged(staged)
        _remove_owned_publications(published)
        raise EvidencePersistenceError(
            f"Could not persist latency execution evidence to {json_path} and {markdown_path}: {exc}"
        ) from exc
    except EvidencePersistenceError:
        _cleanup_staged(staged)
        _remove_owned_publications(published)
        raise
    return json_path, markdown_path


def persist_evidence_file(path: Path, content: str) -> Path:
    """Atomically publish one evidence file without replacing an existing path."""
    _prepare_evidence_directory(path.parent)
    temporary: Path | None = None
    published_identity: tuple[int, int] | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
            _set_evidence_file_permissions(output.fileno())
        os.link(temporary, path)
        info = path.lstat()
        published_identity = (info.st_dev, info.st_ino)
        temporary.unlink()
        _fsync_directory(path.parent)
        return path
    except FileExistsError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise EvidencePersistenceError(
            f"Evidence already exists and will not be overwritten: {path}"
        ) from exc
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if published_identity is not None:
            _remove_owned_publications([(path, published_identity)])
        raise EvidencePersistenceError(
            f"Could not persist evidence file {path}: {exc}"
        ) from exc


def _cleanup_staged(staged: list[tuple[Path, Path]]) -> None:
    for temporary, _ in staged:
        temporary.unlink(missing_ok=True)


def _remove_owned_publications(
    published: list[tuple[Path, tuple[int, int]]],
) -> None:
    for target, identity in published:
        try:
            info = target.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == identity:
            target.unlink()


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _configured_evidence_gid() -> int:
    value = os.environ.get("INTENTFLOW_EVIDENCE_GID")
    if value is None:
        return os.getegid()
    try:
        gid = int(value)
    except ValueError as exc:
        raise EvidencePersistenceError(
            "INTENTFLOW_EVIDENCE_GID must be a non-negative integer."
        ) from exc
    if gid < 0:
        raise EvidencePersistenceError(
            "INTENTFLOW_EVIDENCE_GID must be a non-negative integer."
        )
    return gid


def validate_evidence_permissions(
    info: os.stat_result,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int,
    directory: bool,
) -> None:
    """Validate evidence metadata without changing existing ownership or modes."""
    expected_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not expected_type
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != expected_mode
    ):
        kind = "directory" if directory else "file"
        raise EvidencePersistenceError(
            f"Evidence {kind} has unexpected type, ownership, or permissions."
        )


def _prepare_evidence_directory(directory: Path) -> None:
    if directory.is_symlink():
        raise EvidencePersistenceError(
            f"Evidence directory must not be a symlink: {directory}"
        )
    if directory.resolve(strict=False) != directory.absolute():
        raise EvidencePersistenceError(
            f"Evidence directory path contains a symlink or traversal: {directory}"
        )
    try:
        directory.mkdir(mode=EVIDENCE_DIRECTORY_MODE)
    except FileExistsError:
        expected_uid = 0 if os.geteuid() == 0 else os.geteuid()
        expected_gid = (
            _configured_evidence_gid()
            if os.geteuid() == 0
            else os.getegid()
        )
        try:
            info = directory.lstat()
        except OSError as exc:
            raise EvidencePersistenceError(
                f"Could not inspect evidence directory {directory}: {exc}"
            ) from exc
        try:
            validate_evidence_permissions(
                info,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_mode=EVIDENCE_DIRECTORY_MODE,
                directory=True,
            )
        except EvidencePersistenceError as exc:
            raise EvidencePersistenceError(
                f"Existing evidence directory {directory} has unexpected "
                "ownership or permissions; refusing to change it."
            ) from exc
    except OSError as exc:
        raise EvidencePersistenceError(
            f"Could not create evidence directory {directory}: {exc}"
        ) from exc
    else:
        try:
            if os.geteuid() == 0:
                os.chown(directory, 0, _configured_evidence_gid())
            os.chmod(directory, EVIDENCE_DIRECTORY_MODE)
        except OSError as exc:
            raise EvidencePersistenceError(
                f"Could not secure newly created evidence directory {directory}: {exc}"
            ) from exc
        validate_evidence_permissions(
            directory.lstat(),
            expected_uid=0 if os.geteuid() == 0 else os.geteuid(),
            expected_gid=(
                _configured_evidence_gid()
                if os.geteuid() == 0
                else os.getegid()
            ),
            expected_mode=EVIDENCE_DIRECTORY_MODE,
            directory=True,
        )


def _set_evidence_file_permissions(file_descriptor: int) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        os.fchown(file_descriptor, 0, _configured_evidence_gid())
    os.fchmod(file_descriptor, EVIDENCE_FILE_MODE)
    validate_evidence_permissions(
        os.fstat(file_descriptor),
        expected_uid=0 if os.geteuid() == 0 else os.geteuid(),
        expected_gid=(
            _configured_evidence_gid() if os.geteuid() == 0 else os.getegid()
        ),
        expected_mode=EVIDENCE_FILE_MODE,
        directory=False,
    )


def _build_document(
    result: Any | None,
    *,
    execution_id: str,
    started_at: datetime,
    completed_at: datetime,
    error: str | None,
    graph: Any | None,
    source: str,
    destination: str,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    plan = getattr(result, "plan", None)
    enumeration = getattr(result, "enumeration", None)
    probes = tuple(getattr(result, "probes", ()))
    selection: CandidateSelectionResult | None = getattr(result, "selection", None)
    plan_evaluation = (
        selection.plan_evaluation
        if selection is not None
        else getattr(result, "plan_evaluation", None)
    )
    evaluations_by_id = (
        {
            candidate.candidate_id: candidate
            for candidate in plan_evaluation.candidates
        }
        if plan_evaluation is not None
        else {}
    )
    topology = graph or (plan.request.topology if plan is not None else None)

    candidate_selection = (
        {candidate.candidate_id: candidate for candidate in selection.candidates}
        if selection is not None
        else {}
    )
    probes_by_path = {probe.path: probe for probe in probes}
    candidates: list[dict[str, Any]] = []
    all_paths = enumeration.paths if enumeration is not None else tuple(
        probe.path for probe in probes
    )
    for path in all_paths:
        probe = probes_by_path.get(path)
        candidate_id = (
            probe.candidate_id
            if probe is not None
            else physical_candidate_id(plan, path)
            if plan is not None
            else "unknown"
        )
        if probe is None:
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "measurement_run_id": None,
                    "probe_operation_id": None,
                    "path": _path_data(path),
                    "path_fingerprint": None,
                    "preflight": {
                        "status": "NOT_REACHED",
                        "missing_evidence_reason": (
                            "Execution stopped before this candidate was processed."
                        ),
                    },
                    "compiled_rules": [],
                    "deployment": _deployment_data(None),
                    "measurement": _ping_data(None),
                    "measurements": {},
                    "observation": _observation_data(None),
                    "constraint_observations": [],
                    "constraint_evaluation": [],
                    "objective": {
                        "metric": plan.optimization.metric if plan and plan.optimization else None,
                        "unit": plan.optimization.unit if plan and plan.optimization else None,
                        "value": None,
                        "valid": None,
                    },
                    "eligibility": {
                        "status": "NOT_RECORDED",
                        "reason": "Candidate selection was not reached for this candidate.",
                    },
                    "cleanup": _cleanup_data(None),
                    "stage_timestamps": {},
                    "failure_reason": (
                        getattr(result, "error", None)
                        or "Candidate processing was not reached."
                    ),
                    "stages": {
                        stage: {
                            "status": "NOT_REACHED",
                            "reason": "Execution stopped before this stage.",
                        }
                        for stage in (
                            "probe_preflight",
                            "physical_path_compilation",
                            "temporary_deployment",
                            "latency_measurement",
                            "probe_cleanup",
                        )
                    },
                }
            )
            continue
        deployment = probe.deployment
        cleanup = probe.cleanup
        observation = probe.observation
        ping = probe.measurement
        measurement_records = _probe_measurements(probe)
        selected = candidate_selection.get(probe.candidate_id)
        phase3c = evaluations_by_id.get(probe.candidate_id)
        if selected is not None:
            objective_value = selected.objective_value
            eligibility = {
                "feasibility": selected.feasibility.value,
                "hard_constraint_status": selected.hard_constraint_status.value,
                "reasons": list(
                    next(
                        (
                            assessment.reasons
                            for assessment in selection.plan_evaluation.candidates
                            if assessment.candidate_id == probe.candidate_id
                        ),
                        (),
                    )
                ),
            }
        else:
            objective_value = (
                observation.value if observation is not None else None
            )
            if phase3c is not None:
                eligibility = {
                    "feasibility": phase3c.feasibility.value,
                    "hard_constraint_status": phase3c.status.value,
                    "eligible": (
                        phase3c.feasibility.value == "CANDIDATE"
                        and phase3c.status.value == "SATISFIED"
                    ),
                    "reasons": list(phase3c.reasons),
                }
            elif plan is not None:
                assessment = assess_path_feasibility(plan, probe.path)
                eligibility = {
                    "feasibility": assessment.feasibility.value,
                    "reasons": list(assessment.reasons),
                    "status": "ASSESSMENT_ONLY",
                    "reason": (
                        "Candidate selection was not completed; this is only "
                        "the deterministic feasibility assessment."
                    ),
                }
            else:
                eligibility = {
                    "status": "NOT_RECORDED",
                    "reason": "No plan was available for feasibility assessment.",
                }

        candidates.append(
            {
                "candidate_id": probe.candidate_id,
                "measurement_run_id": probe.measurement_run_id or None,
                "probe_operation_id": probe.operation_id or None,
                "path": _path_data(probe.path),
                "path_fingerprint": (
                    observation.path_fingerprint
                    if observation is not None
                    else physical_path_fingerprint(probe.path)
                ),
                "preflight": _preflight_data(
                    probe.preflight,
                    getattr(probe, "preflight_snapshot", None),
                ),
                "compiled_rules": [
                    _model_data(rule) for rule in getattr(probe, "compiled_rules", ())
                ],
                "deployment": _deployment_data(deployment),
                "measurement": _ping_data(ping),
                "measurements": measurement_records,
                "measurement_stages": _measurement_stage_data(
                    probe, plan, measurement_records
                ),
                "observation": _observation_data(
                    observation,
                    measurement_run_id=(
                        getattr(probe, "measurement_run_ids", {}).get(
                            observation.metric,
                            getattr(probe, "measurement_run_id", None),
                        )
                        if observation is not None
                        else None
                    ),
                ),
                "constraint_observations": [
                    _constraint_observation_data(item, probe)
                    for item in getattr(probe, "observations", ())
                ],
                "constraint_evaluation": (
                    [
                        {
                            "requirement_id": item.target.requirement_id,
                            "metric": item.metric,
                            "unit": item.unit,
                            "status": item.status.value,
                            "observed_value": item.observed_value,
                            "reason": item.reason,
                        }
                        for item in phase3c.requirements
                    ]
                    if phase3c is not None
                    else []
                ),
                "objective": {
                    "metric": plan.optimization.metric if plan and plan.optimization else None,
                    "unit": plan.optimization.unit if plan and plan.optimization else None,
                    "value": objective_value,
                    "valid": (
                        observation is not None
                        and observation.status == ObservationStatus.VALID
                    ),
                },
                "eligibility": eligibility,
                "cleanup": _cleanup_data(cleanup),
                "stage_timestamps": dict(getattr(probe, "stage_timestamps", {})),
                "failure_reason": probe.error,
                "skip_reason": getattr(probe, "skip_reason", None),
                "stages": {
                    "probe_preflight": {
                        "status": (
                            "SKIPPED_INFEASIBLE"
                            if getattr(probe, "skip_reason", None)
                            else "PASSED"
                            if probe.preflight is not None and probe.preflight.passed
                            else "FAILED"
                            if probe.preflight is not None
                            else "FAILED"
                        ),
                        "reason": (
                            probe.skip_reason
                            if getattr(probe, "skip_reason", None)
                            else "; ".join(probe.preflight.reasons)
                            if probe.preflight is not None
                            else probe.error or "Preflight did not return a result."
                        ),
                    },
                    "physical_path_compilation": {
                        "status": (
                            "SUCCEEDED"
                            if probe.compiled_rules
                            else "FAILED"
                            if "compilation_completed_at" in probe.stage_timestamps
                            else "NOT_REACHED"
                        ),
                        "reason": (
                            probe.error
                            if not probe.compiled_rules
                            else None
                        ),
                    },
                    "temporary_deployment": {
                        "status": (
                            deployment.state.value
                            if deployment is not None
                            else "UNCERTAIN"
                            if "deployment_started_at" in probe.stage_timestamps
                            else "NOT_REACHED"
                        ),
                        "reason": (
                            "; ".join(deployment.errors)
                            if deployment is not None and deployment.errors
                            else probe.error
                            if deployment is not None and not deployment.success
                            else probe.error if deployment is None else None
                        ),
                    },
                    "latency_measurement": {
                        "status": (
                            "VALID"
                            if ping is not None and _ping_is_valid(ping)
                            else "INVALID"
                            if ping is not None
                            else "FAILED"
                            if probe.error and "measurement" in probe.error.lower()
                            else "NOT_REACHED"
                        ),
                        "reason": (
                            probe.error
                            if ping is None or not _ping_is_valid(ping)
                            else None
                        ),
                    },
                    "probe_cleanup": {
                        "status": (
                            cleanup.state.value
                            if cleanup is not None
                            else "NOT_POSSIBLE"
                            if deployment is not None
                            and deployment.operation_cookie is None
                            else "NOT_POSSIBLE"
                            if deployment is None
                            and "deployment_started_at" in probe.stage_timestamps
                            else "UNCERTAIN"
                            if deployment is not None
                            and deployment.operation_cookie is not None
                            and "cleanup_started_at" in probe.stage_timestamps
                            else "NOT_REACHED"
                        ),
                        "reason": (
                            "; ".join(cleanup.errors)
                            if cleanup is not None and cleanup.errors
                            else probe.error
                            if cleanup is not None and not cleanup.success
                            else probe.error
                            if cleanup is None
                            and (
                                deployment is not None
                                or "deployment_started_at" in probe.stage_timestamps
                            )
                            else None
                        ),
                    },
                },
            }
        )

    selection_data = None
    if selection is not None:
        ranking_rationale = None
        if (
            plan.optimization is not None
            and selection.selection_method == SelectionMethod.OBJECTIVE_RANKING
            and selection.selected_candidate is not None
        ):
            direction = plan.optimization.direction.value
            ranking_rationale = (
                f"Selected by {direction} of measured {plan.optimization.metric} "
                f"({selection.selected_candidate.objective_value} "
                f"{plan.optimization.unit}) among "
                f"{sum(candidate.objective_value is not None for candidate in selection.candidates)} "
                "eligible candidate(s); equal values use ascending physical path fingerprint."
            )
        selection_data = {
            "status": selection.status.value,
            "objective": {
                "metric": plan.optimization.metric,
                "direction": plan.optimization.direction.value,
                "unit": plan.optimization.unit,
            } if plan.optimization is not None else None,
            "evaluation_run_id": selection.evaluation_run_id,
            "evaluated_at": selection.evaluated_at.isoformat(),
            "selection_method": (
                selection.selection_method.value
                if selection.selection_method is not None
                else None
            ),
            "selected_candidate_id": (
                selection.selected_candidate.candidate_id
                if selection.selected_candidate is not None
                else None
            ),
            "candidate_values": [
                {
                    "candidate_id": candidate.candidate_id,
                    "objective_value": candidate.objective_value,
                    "feasibility": candidate.feasibility.value,
                    "hard_constraint_status": candidate.hard_constraint_status.value,
                    "eligible": (
                        candidate.feasibility.value == "CANDIDATE"
                        and candidate.hard_constraint_status.value
                        in ("NOT_EVALUATED", "SATISFIED")
                    ),
                }
                for candidate in selection.candidates
            ],
            "reasons": list(selection.reasons),
            "ranking_rationale": ranking_rationale,
            "tie_breaking": (
                "Equal objective values are ordered by ascending physical path fingerprint."
                if plan.optimization is not None
                else None
            ),
        }

    final_snapshot = getattr(result, "final_snapshot", None)
    preflight = getattr(result, "final_preflight", None)
    if preflight is not None:
        final_snapshot = preflight.fresh_snapshot

    final_deployment = getattr(result, "final_deployment", None)
    final_cleanup = getattr(result, "final_cleanup", None)
    final_measurement = getattr(result, "final_measurement", None)
    final_rules = getattr(result, "final_rules", ())
    final_operation_id = getattr(result, "final_operation_id", None)
    selected_candidate = (
        selection.selected_candidate if selection is not None else None
    )

    final_data = {
        "selected_candidate_id": (
            selected_candidate.candidate_id if selected_candidate is not None else None
        ),
        "selected_path": (
            _path_data(selected_candidate.path)
            if selected_candidate is not None
            else None
        ),
        "preflight": {
            "status": preflight.status.value if preflight is not None else "NOT_REACHED",
            "checked_at": (
                preflight.checked_at.isoformat() if preflight is not None else None
            ),
            "planned_topology_fingerprint": (
                preflight.planned_topology_fingerprint if preflight is not None else None
            ),
            "fresh_topology_fingerprint": (
                preflight.fresh_topology_fingerprint if preflight is not None else None
            ),
            "planned_snapshot_fingerprint": (
                preflight.planned_snapshot_fingerprint if preflight is not None else None
            ),
            "fresh_snapshot_fingerprint": (
                preflight.fresh_snapshot_fingerprint if preflight is not None else None
            ),
            "snapshot": _snapshot_data(final_snapshot),
            "planned_snapshot": (
                _snapshot_data(preflight.planned_snapshot)
                if preflight is not None
                else None
            ),
            "reasons": list(preflight.reasons) if preflight is not None else [],
            "missing_evidence_reason": (
                None
                if preflight is not None
                else "Final preflight was not reached or its result was not returned."
            ),
        },
        "deployment": {
            "operation_id": final_operation_id,
            **_deployment_data(final_deployment),
            "compiled_rules": [_model_data(rule) for rule in final_rules],
            "cleanup": _cleanup_data(final_cleanup),
        },
        "connectivity": {
            "status": (
                "VERIFIED"
                if final_measurement is not None and _ping_is_valid(final_measurement)
                else "FAILED"
                if final_measurement is not None
                else "NOT_REACHED"
            ),
            "measurement": _ping_data(final_measurement),
        },
        "stages": {
            "final_preflight": {
                "status": (
                    preflight.status.value if preflight is not None else "NOT_REACHED"
                ),
                "reason": (
                    "; ".join(preflight.reasons)
                    if preflight is not None and preflight.reasons
                    else getattr(result, "error", None)
                    if preflight is not None
                    and preflight.status.value != "PASSED"
                    else getattr(result, "error", None)
                    if preflight is None
                    else None
                ),
            },
            "physical_path_compilation": {
                "status": (
                    "SUCCEEDED"
                    if final_rules
                    else "FAILED"
                    if "compilation_completed_at"
                    in getattr(result, "final_stage_timestamps", {})
                    else "NOT_REACHED"
                ),
                "reason": (
                    getattr(result, "error", None) if not final_rules else None
                ),
            },
            "final_deployment": {
                "status": (
                    final_deployment.state.value
                    if final_deployment is not None
                    else "UNCERTAIN"
                    if "deployment_started_at"
                    in getattr(result, "final_stage_timestamps", {})
                    else "NOT_REACHED"
                ),
                "reason": (
                    "; ".join(final_deployment.errors)
                    if final_deployment is not None and final_deployment.errors
                    else getattr(result, "error", None)
                    if final_deployment is not None and not final_deployment.success
                    else getattr(result, "error", None)
                    if final_deployment is None
                    else None
                ),
            },
            "final_connectivity": {
                "status": (
                    "VALID"
                    if final_measurement is not None
                    and _ping_is_valid(final_measurement)
                    else "INVALID"
                    if final_measurement is not None
                    else "FAILED"
                    if getattr(result, "error", None)
                    and "measurement" in result.error.lower()
                    else "NOT_REACHED"
                ),
                "reason": (
                    getattr(result, "error", None)
                    if final_measurement is None or not _ping_is_valid(final_measurement)
                    else None
                ),
            },
            "final_cleanup": {
                "status": (
                    final_cleanup.state.value
                    if final_cleanup is not None
                    else "NOT_POSSIBLE"
                    if final_deployment is not None
                    and final_deployment.operation_cookie is None
                    else "NOT_POSSIBLE"
                    if final_deployment is None
                    and "deployment_started_at"
                    in getattr(result, "final_stage_timestamps", {})
                    else "NOT_REQUIRED"
                    if final_deployment is not None
                    and final_deployment.success
                    and final_measurement is not None
                    and _ping_is_valid(final_measurement)
                    else "UNCERTAIN"
                    if "cleanup_started_at"
                    in getattr(result, "final_stage_timestamps", {})
                    else "NOT_REACHED"
                ),
                "reason": (
                    "; ".join(final_cleanup.errors)
                    if final_cleanup is not None and final_cleanup.errors
                    else getattr(result, "error", None)
                    if final_cleanup is not None and not final_cleanup.success
                    else getattr(result, "error", None)
                    if final_cleanup is None
                    and "cleanup_started_at"
                    in getattr(result, "final_stage_timestamps", {})
                    else None
                ),
            },
        },
    }

    status = getattr(getattr(result, "status", None), "value", "FAILED")
    execution_error = error or getattr(result, "error", None)
    topology_fingerprint = _try_topology_fingerprint(topology)
    request_fingerprint = (
        model_fingerprint(plan.request) if plan is not None else None
    )
    return {
        "schema_version": 1,
        "execution_id": execution_id,
        "execution_status": status,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": (completed_at - started_at).total_seconds(),
        "request": {
            "source": source,
            "destination": destination,
            "objective": (
                {
                    "metric": plan.optimization.metric,
                    "direction": plan.optimization.direction.value,
                    "unit": plan.optimization.unit,
                }
                if plan is not None and plan.optimization is not None
            else None
            ),
            "constraints": (
                [
                    {
                        "metric": item.constraint.metric,
                        "comparison": item.constraint.comparison.value,
                        "unit": item.constraint.unit,
                        "value": item.constraint.value,
                        "lower_bound": item.constraint.lower_bound,
                        "upper_bound": item.constraint.upper_bound,
                        "requirement_id": item.requirement_id,
                    }
                    for item in plan.hard_constraints
                ]
                if plan is not None
                else []
            ),
            "request_fingerprint": request_fingerprint,
        },
        "configuration": configuration,
        "topology": {
            "fingerprint": topology_fingerprint,
            "switches": (
                dict(sorted(topology.switches.items())) if topology is not None else None
            ),
        },
        "selection_evaluation_run_id": getattr(result, "measurement_run_id", None),
        "constraint_evaluation": (
            {
                "status": plan_evaluation.status.value,
                "evaluation_run_id": plan_evaluation.evaluation_run_id,
                "evaluated_at": plan_evaluation.evaluated_at.isoformat(),
                "candidates": [
                    {
                        "candidate_id": candidate.candidate_id,
                        "status": candidate.status.value,
                        "requirements": [
                            {
                                "requirement_id": requirement.target.requirement_id,
                                "metric": requirement.metric,
                                "unit": requirement.unit,
                                "status": requirement.status.value,
                                "observed_value": _finite_number(
                                    requirement.observed_value
                                ),
                                "reason": requirement.reason,
                            }
                            for requirement in candidate.requirements
                        ],
                    }
                    for candidate in plan_evaluation.candidates
                ],
            }
            if plan_evaluation is not None
            else {
                "status": "NOT_REACHED",
                "missing_evidence_reason": (
                    "Hard-constraint evaluation was not reached."
                ),
            }
        ),
        "candidate_discovery": {
            "status": (
                "COMPLETE"
                if enumeration is not None and not enumeration.truncated
                else "TRUNCATED"
                if enumeration is not None
                else "NOT_REACHED"
            ),
            "candidate_limit": (
                enumeration.candidate_limit if enumeration is not None else None
            ),
            "truncated": enumeration.truncated if enumeration is not None else None,
            "completed_at": (
                min(
                    (
                        probe.stage_timestamps["candidate_discovered_at"]
                        for probe in probes
                        if "candidate_discovered_at" in probe.stage_timestamps
                    ),
                    default=None,
                )
                if enumeration is not None
                else None
            ),
            "paths": [
                {
                    "candidate_id": (
                        next(
                            (
                                probe.candidate_id
                                for probe in probes
                                if probe.path == path
                            ),
                            physical_candidate_id(plan, path)
                            if plan is not None
                            else None,
                        )
                    ),
                    **_path_data(path),
                }
                for path in (enumeration.paths if enumeration is not None else ())
            ],
        },
        "candidates": candidates,
        "selection": selection_data
        or {
            "status": "NOT_REACHED",
            "objective": None,
            "candidate_values": [
                candidate["objective"] | {"candidate_id": candidate["candidate_id"]}
                for candidate in candidates
            ],
            "reasons": [execution_error or "Selection was not reached."],
        },
        "final": final_data,
        "final_stage_timestamps": dict(
            getattr(result, "final_stage_timestamps", {})
        ),
        "failure": {
            "reason": execution_error,
            "evidence_status": "RECORDED" if result is not None else "PARTIAL",
        },
    }


def _try_topology_fingerprint(topology: Any | None) -> str | None:
    if topology is None:
        return None
    try:
        return canonical_topology_fingerprint(topology)
    except (TypeError, ValueError):
        return None


def _path_data(path: Any) -> dict[str, Any]:
    return {
        "nodes": list(path.nodes),
        "connections": [
            {
                "kind": connection.kind.value,
                "from_node": connection.from_node,
                "to_node": connection.to_node,
                "from_port": connection.from_port,
                "to_port": connection.to_port,
                "link_identity": connection.link_identity,
            }
            for connection in path.connections
        ],
    }


def _preflight_data(preflight: Any, snapshot: Any) -> dict[str, Any]:
    if preflight is None:
        return {
            "status": "NOT_REACHED",
            "snapshot": _snapshot_data(snapshot),
            "missing_evidence_reason": "Probe preflight did not return a result.",
        }
    return {
        "status": preflight.status,
        "candidate_id": preflight.candidate_id,
        "path_fingerprint": preflight.path_fingerprint,
        "planned_snapshot_fingerprint": preflight.planned_snapshot_fingerprint,
        "fresh_snapshot_fingerprint": preflight.fresh_snapshot_fingerprint,
        "snapshot": _snapshot_data(snapshot),
        "reasons": list(preflight.reasons),
    }


def _snapshot_data(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "status": snapshot.status.value,
        "captured_at": snapshot.captured_at.isoformat(),
        "topology_fingerprint": canonical_topology_fingerprint(
            snapshot.configured_topology
        ),
        "snapshot_fingerprint": topology_snapshot_fingerprint(snapshot),
        "connected_switch_dpids": list(snapshot.connected_switch_dpids),
        "ports": [
            {
                "dpid": port.dpid,
                "port_no": port.port_no,
                "present": port.present,
                "admin_up": port.admin_up,
                "link_up": port.link_up,
            }
            for port in snapshot.port_states
        ],
    }


def _deployment_data(deployment: Any) -> dict[str, Any]:
    if deployment is None:
        return {
            "status": "NOT_REACHED",
            "operation_cookie": None,
            "affected_dpids": None,
            "requested_count": None,
            "accepted_count": None,
            "verified_count": None,
            "success": None,
            "readback": {
                "status": "NOT_REACHED",
                "missing_evidence_reason": "No deployment result was returned.",
            },
            "errors": [],
            "missing_evidence_reason": "Deployment returned no result.",
        }
    return {
        "status": deployment.state.value,
        "operation_cookie": deployment.operation_cookie,
        "affected_dpids": list(deployment.dpids),
        "requested_count": deployment.requested_count,
        "accepted_count": deployment.accepted_count,
        "verified_count": deployment.verified_count,
        "reconciled_count": deployment.reconciled_count,
        "success": deployment.success,
        "readback": {
            "status": "VERIFIED"
            if deployment.success
            else "PARTIAL"
            if deployment.verified_count > 0
            else "FAILED"
            if deployment.state.value in ("FAILED", "PARTIAL")
            else "UNCERTAIN",
            "verified_rule_count": deployment.verified_count,
            "requested_rule_count": deployment.requested_count,
            "verification_contract": (
                "Executor readback compared operation-owned cookie and exact "
                "rule match, priority, and actions."
            ),
        },
        "errors": list(deployment.errors),
    }


def _cleanup_data(cleanup: Any) -> dict[str, Any]:
    if cleanup is None:
        return {
            "status": "NOT_REACHED",
            "success": None,
            "remaining_flow_count": None,
            "missing_evidence_reason": "Cleanup returned no result.",
        }
    return {
        "status": cleanup.state.value,
        "operation_cookie": cleanup.operation_cookie,
        "requested_dpids": list(cleanup.requested_dpids),
        "accepted_delete_count": cleanup.accepted_delete_count,
        "remaining_flow_count": cleanup.remaining_flow_count,
        "success": cleanup.success,
        "errors": list(cleanup.errors),
    }


def _ping_data(ping: Any) -> dict[str, Any] | None:
    if ping is None:
        return {
            "status": "NOT_REACHED",
            "valid": None,
            "missing_evidence_reason": "No ping result was returned.",
        }
    return {
        "status": "VALID" if _ping_is_valid(ping) else "INVALID",
        "valid": _ping_is_valid(ping),
        "packets_requested": ping.packets_requested,
        "packets_sent": ping.packets_sent,
        "packets_received": ping.packets_received,
        "packet_loss_pct": _finite_number(ping.packet_loss_pct),
        "rtt_min_ms": _finite_number(ping.rtt_min_ms),
        "rtt_avg_ms": _finite_number(ping.rtt_avg_ms),
        "rtt_max_ms": _finite_number(ping.rtt_max_ms),
        "rtt_mdev_ms": _finite_number(ping.rtt_mdev_ms),
        "raw_output": ping.raw_output,
    }


def _probe_measurements(probe: Any) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for metric, result in getattr(probe, "measurements", {}).items():
        run_ids = getattr(probe, "measurement_run_ids", {})
        if hasattr(result, "rtt_avg_ms"):
            record = _ping_data(result) or {}
            if metric == "packet_loss":
                valid = bool(result.measurement_succeeded)
                record["status"] = "VALID" if valid else "INVALID"
                record["valid"] = valid
            records[metric] = {
                "measurement_run_id": run_ids.get(metric),
                "collected_at": _measurement_timestamp(probe, metric),
                **record,
            }
        elif hasattr(result, "achieved_mbps"):
            records[metric] = {
                "measurement_run_id": run_ids.get(metric),
                "collected_at": _measurement_timestamp(probe, metric),
                "status": "VALID" if _throughput_is_valid(result) else "INVALID",
                "valid": _throughput_is_valid(result),
                "sent_mbps": _finite_number(result.sent_mbps),
                "received_mbps": _finite_number(result.received_mbps),
                "achieved_mbps": _finite_number(result.achieved_mbps),
                "retransmits": result.retransmits,
                "duration_s": _finite_number(result.duration_s),
                "error": result.error,
                "raw_output": result.raw_output,
            }
        else:
            records[metric] = {
                "status": "UNKNOWN",
                "valid": False,
                "missing_evidence_reason": "Measurement result type is not recognized.",
            }
    return records


def _throughput_is_valid(result: Any) -> bool:
    value = result.received_mbps
    return (
        result.succeeded
        and value is not None
        and math.isfinite(value)
        and value >= 0
    )


def _constraint_observation_data(observation: Any, probe: Any) -> dict[str, Any]:
    target = observation.target
    return {
        "candidate_id": target.candidate_id,
        "request_fingerprint": target.request_fingerprint,
        "path_fingerprint": target.path_fingerprint,
        "requirement_id": target.requirement_id,
        "metric": observation.metric,
        "unit": observation.unit,
        "value": _finite_number(observation.value),
        "status": observation.status.value,
        "collected_at": observation.collected_at.isoformat(),
        "source": observation.source,
        "evaluation_run_id": observation.evaluation_run_id,
        "measurement_run_id": getattr(probe, "measurement_run_ids", {}).get(
            observation.metric
        ),
    }


def _measurement_stage_data(
    probe: Any,
    plan: Any,
    records: dict[str, Any],
) -> dict[str, Any]:
    required_metrics = (
        {item.metric for item in plan.required_observations}
        if plan is not None
        else set(records)
    )
    timestamps = getattr(probe, "stage_timestamps", {})
    stages: dict[str, Any] = {}
    for metric in sorted(required_metrics):
        record = records.get(metric)
        stages[metric] = {
            "status": record.get("status", "NOT_REACHED") if record else "NOT_REACHED",
            "measurement_run_id": (
                record.get("measurement_run_id") if record else None
            ),
            "collected_at": record.get("collected_at") if record else None,
            "started_at": timestamps.get("measurement_started_at"),
            "completed_at": timestamps.get("measurement_completed_at"),
            "reason": (
                None
                if record is not None and record.get("valid") is True
                else record.get("error")
                if record is not None and record.get("error")
                else "No valid measurement evidence was returned."
            ),
        }
    return stages


def _measurement_timestamp(probe: Any, metric: str) -> str | None:
    value = getattr(probe, "measurement_timestamps", {}).get(metric)
    return value.isoformat() if value is not None else None


def _ping_is_valid(ping: Any) -> bool:
    return (
        ping.measurement_succeeded
        and ping.packets_received > 0
        and ping.rtt_avg_ms is not None
        and math.isfinite(ping.rtt_avg_ms)
        and ping.rtt_avg_ms >= 0
    )


def _finite_number(value: Any) -> float | int | str | None:
    if value is None or type(value) is int:
        return value
    if type(value) is float and not math.isfinite(value):
        return repr(value)
    return value


def _observation_data(
    observation: Any,
    *,
    measurement_run_id: str | None = None,
) -> dict[str, Any] | None:
    if observation is None:
        return {
            "status": "NOT_CREATED",
            "missing_evidence_reason": "No candidate-bound observation was created.",
        }
    return {
        "candidate_id": observation.candidate_id,
        "request_fingerprint": observation.request_fingerprint,
        "plan_fingerprint": observation.plan_fingerprint,
        "path_fingerprint": observation.path_fingerprint,
        "observation_id": observation.observation_id,
        "requirement_id": observation.requirement_id,
        "evaluation_run_id": observation.evaluation_run_id,
        "measurement_run_id": measurement_run_id or None,
        "metric": observation.metric,
        "unit": observation.unit,
        "value": observation.value,
        "status": observation.status.value,
        "collected_at": observation.collected_at.isoformat(),
        "source": observation.source,
    }


def _model_data(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _render_markdown(document: dict[str, Any]) -> str:
    objective = document["request"].get("objective")
    objective_unit = objective["unit"] if objective is not None else "metric unit"
    objective_name = objective["metric"] if objective is not None else "constraints"
    objective_text = (
        f"`{objective['direction']} {objective['metric']}` ({objective['unit']})"
        if objective is not None
        else "none"
    )
    lines = [
        f"# Generalized routing execution {document['execution_id']}",
        "",
        f"- **Status:** `{document['execution_status']}`",
        f"- **Started:** {document['started_at']}",
        f"- **Completed:** {document['completed_at']}",
        f"- **Duration:** {document['duration_seconds']:.3f}s",
        f"- **Topology fingerprint:** `{document['topology']['fingerprint'] or 'not recorded'}`",
        f"- **Objective:** {objective_text}",
        f"- **Hard constraints:** {', '.join(item['metric'] + ' ' + item['comparison'] for item in document['request'].get('constraints', [])) or 'none'}",
        "",
        "## Candidate measurements",
        "",
        "| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |",
        "|---|---|---:|---:|---|---|---|---:|---|",
    ]
    selected_id = document["selection"].get("selected_candidate_id")
    for candidate in document["candidates"]:
        measurement = candidate["measurement"]
        deployment = candidate["deployment"]
        cleanup = candidate["cleanup"]
        packet_pair = (
            f"{measurement['packets_received']}/{measurement['packets_sent']}"
            if measurement.get("packets_sent") is not None
            else "not recorded"
        )
        lines.append(
            "| `{}` | `{}` | {} | {} | {} | {} | {} | {} | {} |".format(
                candidate["candidate_id"],
                " → ".join(candidate["path"]["nodes"]),
                measurement.get("rtt_avg_ms", "not recorded"),
                packet_pair,
                measurement.get("valid", "not recorded"),
                candidate["eligibility"].get("eligible", "not recorded"),
                candidate["candidate_id"] == selected_id,
                deployment.get("operation_cookie", "not recorded"),
                cleanup.get("status", "not recorded"),
            )
        )
        for metric, record in candidate.get("measurements", {}).items():
            value = (
                record.get("rtt_avg_ms")
                if metric == "latency"
                else record.get("packet_loss_pct")
                if metric == "packet_loss"
                else record.get("achieved_mbps")
            )
            unit = "ms" if metric == "latency" else "%" if metric == "packet_loss" else "Mbps"
            lines.append(
                f"- **{metric} measurement:** `{record.get('status')}`; "
                f"value `{value}` {unit}; run "
                f"`{record.get('measurement_run_id') or 'not recorded'}`"
            )
        for constraint in candidate.get("constraint_evaluation", []):
            lines.append(
                f"- **Constraint {constraint['requirement_id']}:** "
                f"`{constraint['status']}`; observed "
                f"`{constraint.get('observed_value')}`; "
                f"{constraint.get('reason') or 'no additional reason'}"
            )
    lines.extend(["", "## Candidate evidence", ""])
    for candidate in document["candidates"]:
        measurement = candidate["measurement"]
        deployment = candidate["deployment"]
        cleanup = candidate["cleanup"]
        lines.extend(
            [
                f"### {candidate['candidate_id']}",
                "",
                f"- **Path:** `{' → '.join(candidate['path']['nodes'])}`",
                f"- **Path fingerprint:** `{candidate.get('path_fingerprint') or 'not recorded'}`",
                f"- **Measurement run ID:** `{candidate.get('measurement_run_id') or 'not created'}`",
                f"- **Probe operation ID:** `{candidate.get('probe_operation_id') or 'not created'}`",
                f"- **Preflight:** `{candidate['stages']['probe_preflight']['status']}`",
                f"- **Deployment:** `{deployment.get('status')}`; cookie "
                f"`{deployment.get('operation_cookie')}`; DPIDs "
                f"`{deployment.get('affected_dpids')}`; readback "
                f"{deployment.get('verified_count')}/{deployment.get('requested_count')}",
                f"- **Observation:** `{(candidate.get('observation') or {}).get('status')}` "
                f"({(candidate.get('observation') or {}).get('observation_id') or 'not created'})",
                f"- **Cleanup:** `{cleanup.get('status')}`; remaining flows "
                f"`{cleanup.get('remaining_flow_count')}`",
            ]
        )
        if candidate.get("skip_reason"):
            lines.append(f"- **Skipped:** {candidate['skip_reason']}")
        observation = candidate.get("observation") or {}
        if observation.get("candidate_id"):
            lines.append(
                f"- **Observation identity:** candidate `{observation['candidate_id']}`, "
                f"evaluation run `{observation['evaluation_run_id']}`, request "
                f"`{observation['request_fingerprint']}`, plan "
                f"`{observation['plan_fingerprint']}`, path "
                f"`{observation['path_fingerprint']}`"
            )
        preflight = candidate["preflight"]
        if preflight.get("planned_snapshot_fingerprint"):
            lines.append(
                f"- **Probe snapshot fingerprints:** planned "
                f"`{preflight['planned_snapshot_fingerprint']}`, fresh "
                f"`{preflight['fresh_snapshot_fingerprint']}`"
            )
        probe_snapshot = preflight.get("snapshot")
        if probe_snapshot is not None:
            live_ports = [
                port
                for port in probe_snapshot["ports"]
                if port["present"] and port["admin_up"] and port["link_up"]
            ]
            lines.append(
                f"- **Probe snapshot:** `{probe_snapshot['status']}` at "
                f"{probe_snapshot['captured_at']}; connected DPIDs "
                f"`{probe_snapshot['connected_switch_dpids']}`; operational "
                f"data ports {len(live_ports)}/{len(probe_snapshot['ports'])}"
            )
        if candidate.get("failure_reason"):
            lines.append(f"- **Failure reason:** {candidate['failure_reason']}")
        if candidate.get("stage_timestamps"):
            lines.append(
                "- **Stage timestamps:** "
                + "; ".join(
                    f"{stage}={timestamp}"
                    for stage, timestamp in candidate["stage_timestamps"].items()
                )
            )
        if candidate.get("compiled_rules"):
            lines.extend(["", "Compiled probe rules:", "", "```json"])
            lines.append(
                json.dumps(candidate["compiled_rules"], indent=2, ensure_ascii=False)
            )
            lines.append("```")
        raw_output = measurement.get("raw_output")
        if raw_output:
            lines.extend(["", "Raw candidate ping output:", "", "```text", raw_output, "```"])
        for metric, record in candidate.get("measurements", {}).items():
            if metric == "bandwidth" and record.get("raw_output"):
                lines.extend(
                    [
                        "",
                        "Raw candidate iperf3 output:",
                        "",
                        "```text",
                        record["raw_output"],
                        "```",
                    ]
                )
        lines.append("")

    lines.extend(["## Selection and final execution", ""])
    selection = document["selection"]
    selected_candidate = next(
        (
            item
            for item in document["candidates"]
            if item["candidate_id"] == selection.get("selected_candidate_id")
        ),
        None,
    )
    selected_path_text = (
        " → ".join(selected_candidate["path"]["nodes"])
        if selected_candidate is not None
        else "not selected"
    )
    lines.extend(
        [
            f"- **Selection status:** `{selection.get('status')}`",
            f"- **Selected candidate:** `{selection.get('selected_candidate_id') or 'none'}`",
            f"- **Selected path:** `{selected_path_text}`",
            f"- **Selection method:** `{selection.get('selection_method') or 'not reached'}`",
            "",
            f"| Candidate | {objective_name} value ({objective_unit}) | Feasibility | Eligible |",
            "|---|---:|---|---|",
        ]
    )
    for candidate in selection.get("candidate_values", []):
        lines.append(
            f"| `{candidate.get('candidate_id')}` | "
            f"{candidate.get('objective_value', 'not recorded')} | "
            f"{candidate.get('feasibility', 'not recorded')} | "
            f"{candidate.get('eligible', 'not recorded')} |"
        )
    if selection.get("reasons"):
        lines.extend(["", "Selection reasoning:"])
        lines.extend(f"- {reason}" for reason in selection["reasons"])
    if selection.get("ranking_rationale"):
        lines.append(f"- {selection['ranking_rationale']}")

    final = document["final"]
    final_preflight = final["preflight"]
    final_deployment = final["deployment"]
    final_measurement = final["connectivity"].get("measurement") or {}
    final_snapshot = final_preflight.get("snapshot")
    lines.extend(
        [
            f"- **Final preflight:** `{final_preflight['status']}`",
            f"- **Final topology fingerprints:** planned "
            f"`{final_preflight.get('planned_topology_fingerprint') or 'not recorded'}`, "
            f"fresh `{final_preflight.get('fresh_topology_fingerprint') or 'not recorded'}`",
            f"- **Connected DPIDs:** "
            f"`{(final_preflight.get('snapshot') or {}).get('connected_switch_dpids', 'not recorded')}`",
            f"- **Operational data ports:** "
            f"{sum(port['present'] and port['admin_up'] and port['link_up'] for port in final_snapshot['ports'])}/"
            f"{len(final_snapshot['ports'])}"
            if final_snapshot is not None
            else "- **Operational data ports:** not recorded",
            f"- **Final deployment operation ID:** "
            f"`{final_deployment.get('operation_id') or 'not created'}`",
            f"- **Final selected path:** "
            f"`{' → '.join((final.get('selected_path') or {}).get('nodes', [])) or 'not selected'}`",
            f"- **Final deployment:** `{final_deployment['status']}` "
            f"(cookie `{final_deployment.get('operation_cookie')}`, DPIDs "
            f"`{final_deployment.get('affected_dpids')}`)",
            f"- **Verified rules:** {final_deployment.get('verified_count')} / "
            f"{final_deployment.get('requested_count')} "
            f"(executor reported exact readback status)",
            f"- **Connectivity:** `{final['connectivity']['status']}`",
            f"- **Final packets:** {final_measurement.get('packets_received', 'not recorded')}/"
            f"{final_measurement.get('packets_sent', 'not recorded')} received; "
            f"loss {final_measurement.get('packet_loss_pct', 'not recorded')}%",
            f"- **Final RTT:** {final_measurement.get('rtt_avg_ms', 'not recorded')} ms",
        ]
    )
    if final_deployment.get("compiled_rules"):
        lines.extend(["", "Compiled final rules:", "", "```json"])
        lines.append(
            json.dumps(final_deployment["compiled_rules"], indent=2, ensure_ascii=False)
        )
        lines.append("```")
    if final_measurement.get("raw_output"):
        lines.extend(
            [
                "",
                "Raw final ping output:",
                "",
                "```text",
                final_measurement["raw_output"],
                "```",
            ]
        )
    if document.get("final_stage_timestamps"):
        lines.extend(
            [
                "",
                "**Final-stage timestamps:** "
                + "; ".join(
                    f"{stage}={timestamp}"
                    for stage, timestamp in document["final_stage_timestamps"].items()
                ),
            ]
        )
    if document["failure"]["reason"]:
        lines.extend(["", "## Failure or limitation", "", document["failure"]["reason"]])
    lines.extend(
        [
            "",
            "## Evidence availability",
            "",
            "The JSON companion contains stage outcomes, exact physical connections, "
            "deployment results, packet evidence, and explicit not-reached markers. "
            "Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.",
            "",
        ]
    )
    return "\n".join(lines)
