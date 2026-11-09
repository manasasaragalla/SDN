from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.execution.models import (
    PortOperationalState,
    SnapshotStatus,
    TopologySnapshot,
)
from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    TrafficScope,
)
from backend.models.deployment import (
    PhysicalCleanupResult,
    PhysicalCleanupState,
    PhysicalDeploymentResult,
    PhysicalDeploymentState,
)
from backend.models.measurement import LatencyResult, ThroughputResult
from backend.models.network import Host, Link, TopologyGraph
from backend.orchestration import generalized_constraints as orchestration
from backend.orchestration import latency_evidence
from backend.planner.constraint_evaluation import (
    EvaluationCandidate,
    EvaluationInputError,
    EvaluationStatus,
    EvaluationTarget,
    FreshnessPolicy,
    MetricFreshnessLimit,
    MetricObservation,
    ObservationStatus,
    evaluate_hard_constraints,
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.path_enumeration import enumerate_candidate_paths


@pytest.fixture(autouse=True)
def isolate_execution_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(latency_evidence, "JSON_OUTPUT_DIR", tmp_path / "results")
    monkeypatch.setattr(latency_evidence, "MARKDOWN_OUTPUT_DIR", tmp_path / "reports")


def _graph(bandwidths=(100, 100)):
    return TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": Host(
                name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01",
                switch="s1", switch_port=1,
            ),
            "h4": Host(
                name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04",
                switch="s2", switch_port=1,
            ),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=2, bw_mbps=bandwidths[0]),
            Link(node_a="s1", port_a=3, node_b="s2", port_b=3, bw_mbps=bandwidths[1]),
        ],
    )


def _snapshot(graph, *, down_port=None):
    ports = {(1, 1), (2, 1), (1, 2), (2, 2), (1, 3), (2, 3)}
    return TopologySnapshot(
        configured_topology=graph,
        captured_at=datetime.now(timezone.utc),
        status=SnapshotStatus.COMPLETE,
        connected_switch_dpids=(1, 2),
        port_states=tuple(
            PortOperationalState(
                dpid=dpid,
                port_no=port,
                present=True,
                admin_up=(dpid, port) != down_port,
                link_up=(dpid, port) != down_port,
            )
            for dpid, port in sorted(ports)
        ),
    )


def _intent(*constraints, optimization=None):
    return CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=list(constraints),
        optimization=optimization,
    )


def _constraint(metric, comparison, value, unit):
    return MetricConstraint(
        metric=metric,
        comparison=comparison,
        value=value,
        unit=unit,
    )


def _ping(rtt=2.0, received=3):
    sent = 3
    return LatencyResult(
        packets_sent=sent,
        packets_received=received,
        packet_loss_pct=(sent - received) * 100 / sent,
        packets_requested=sent,
        rtt_avg_ms=rtt if received else None,
        raw_output=f"measured ping {received}/{sent}",
    )


def _throughput(mbps=30.0, *, succeeded=True):
    return ThroughputResult(
        sent_mbps=mbps,
        received_mbps=mbps,
        duration_s=1,
        succeeded=succeeded,
        error=None if succeeded else "iperf3 failed",
        raw_output="measured iperf3 JSON",
    )


class _Host:
    def __init__(self, name):
        self.name = name


def _deployment(rules, cookie, *, succeeded=True):
    count = len(rules)
    return PhysicalDeploymentResult(
        operation_cookie=cookie,
        dpids=(1, 2),
        requested_count=count,
        accepted_count=count if succeeded else 0,
        verified_count=count if succeeded else 0,
        state=(
            PhysicalDeploymentState.SUCCEEDED
            if succeeded
            else PhysicalDeploymentState.PARTIAL
        ),
        errors=[] if succeeded else ["partial readback"],
    )


def _cleanup(deployment, *, succeeded=True):
    return PhysicalCleanupResult(
        operation_cookie=deployment.operation_cookie,
        requested_dpids=deployment.dpids,
        accepted_delete_count=len(deployment.dpids) if succeeded else 0,
        remaining_flow_count=0 if succeeded else 1,
        state=(
            PhysicalCleanupState.SUCCEEDED
            if succeeded
            else PhysicalCleanupState.FAILED
        ),
        errors=[] if succeeded else ["cookie-owned flow remains"],
    )


def _install_mocks(
    monkeypatch,
    *,
    graph=None,
    pings=None,
    throughputs=None,
    failed_deployment_at=None,
    failed_cleanup_at=None,
    final_snapshot=None,
):
    pings = iter(pings or [_ping(), _ping(4), _ping()])
    throughputs = iter(throughputs or [_throughput(30), _throughput(22)])
    deploy_index = 0
    cleanup_index = 0
    deployments = []
    cleanups = []
    cookies = iter(range(1001, 1100))

    def deploy(rules, base_url=None):
        nonlocal deploy_index
        deploy_index += 1
        result = _deployment(
            rules,
            next(cookies),
            succeeded=deploy_index != failed_deployment_at,
        )
        deployments.append(result)
        return result

    def cleanup(deployment, base_url=None):
        nonlocal cleanup_index
        cleanup_index += 1
        result = _cleanup(deployment, succeeded=cleanup_index != failed_cleanup_at)
        cleanups.append(result)
        return result

    def get_ping(*args, **kwargs):
        return next(pings)

    def get_throughput(*args, **kwargs):
        return next(throughputs)

    snapshot_number = 0

    def fresh_snapshot():
        nonlocal snapshot_number
        snapshot_number += 1
        if final_snapshot is not None and snapshot_number > 2:
            return final_snapshot
        return _snapshot(graph)

    graph = graph or _graph()
    monkeypatch.setattr(orchestration, "deploy_physical_path_rules", deploy)
    monkeypatch.setattr(orchestration, "cleanup_physical_path_deployment", cleanup)
    monkeypatch.setattr(orchestration, "measure_latency", get_ping)
    monkeypatch.setattr(orchestration, "measure_throughput", get_throughput)
    return graph, fresh_snapshot, deployments, cleanups


def _run(monkeypatch, intent, *, orchestration_options=None, **mocks):
    graph, fresh, deployments, cleanups = _install_mocks(monkeypatch, **mocks)
    result = orchestration.run_generalized_constraint_demo(
        graph,
        source_host=_Host("h1"),
        destination_host=_Host("h4"),
        intent=intent,
        planned_snapshot=_snapshot(graph),
        fresh_snapshot_provider=fresh,
        ping_count=3,
        throughput_duration_s=1,
        **(orchestration_options or {}),
    )
    return result, deployments, cleanups


def test_bandwidth_latency_and_packet_loss_constraints_measure_both_paths(monkeypatch):
    intent = _intent(
        _constraint("latency", Comparison.LT, 50, "ms"),
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
        _constraint("packet_loss", Comparison.LT, 1, "%"),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        pings=[_ping(3), _ping(1), _ping()],
        throughputs=[_throughput(25), _throughput(40)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    assert result.selection.selected_candidate.path == result.probes[1].path
    assert len(result.probes) == 2
    assert all(probe.measurements["bandwidth"].received_mbps > 20 for probe in result.probes)
    assert all(len(probe.observations) == 3 for probe in result.probes)
    assert all(probe.observations[0].target.candidate_id == probe.candidate_id for probe in result.probes)
    assert all(item.success for item in cleanups[:2])
    assert len(deployments) == 3
    assert result.final_deployment.success
    record = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert record["request"]["constraints"][1]["metric"] == "bandwidth"
    assert record["candidates"][0]["measurements"]["bandwidth"]["received_mbps"] == 25
    assert record["candidates"][0]["observation"]["metric"] == "latency"
    assert record["candidates"][0]["observation"]["measurement_run_id"] == (
        record["candidates"][0]["measurements"]["latency"]["measurement_run_id"]
    )
    assert "Constraint" in open(result.evidence_markdown_path, encoding="utf-8").read()


def test_api_execution_id_is_used_for_persisted_evidence(monkeypatch):
    execution_id = "a" * 32
    result, _, _ = _run(
        monkeypatch,
        _intent(
            optimization=OptimizationObjective(
                metric="latency",
                direction=OptimizationDirection.MINIMIZE,
                unit="ms",
            )
        ),
        orchestration_options={"execution_id": execution_id},
    )
    assert result.execution_id == execution_id
    assert result.evidence_json_path.endswith(f"{execution_id}.json")
    assert result.evidence_markdown_path.endswith(f"{execution_id}.md")


def test_invalid_api_execution_id_is_rejected_before_measurement(monkeypatch):
    graph = _graph()
    with pytest.raises(ValueError, match="lowercase UUID hex"):
        orchestration.run_generalized_constraint_demo(
            graph,
            source_host=_Host("h1"),
            destination_host=_Host("h4"),
            intent=_intent(),
            planned_snapshot=_snapshot(graph),
            fresh_snapshot_provider=lambda: _snapshot(graph),
            execution_id="../unsafe",
        )


def test_minimize_latency_ranks_real_candidate_rtt_and_persists_scores(monkeypatch):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        pings=[_ping(4), _ping(1), _ping(2)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    assert result.selection.selection_method.value == "OBJECTIVE_RANKING"
    assert result.selection.selected_candidate.path == result.probes[1].path
    assert [item.objective_value for item in result.selection.candidates] == [4, 1]
    assert len(deployments) == 3
    assert len(cleanups) == 2
    assert all(item.success for item in cleanups)

    record = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert record["selection"]["objective"] == {
        "metric": "latency",
        "direction": "MINIMIZE",
        "unit": "ms",
    }
    assert [item["objective_value"] for item in record["selection"]["candidate_values"]] == [
        4,
        1,
    ]
    assert record["selection"]["selection_method"] == "OBJECTIVE_RANKING"
    assert "MINIMIZE of measured latency" in record["selection"]["ranking_rationale"]
    assert record["candidates"][1]["observation"]["plan_fingerprint"]
    report = open(result.evidence_markdown_path, encoding="utf-8").read()
    assert "MINIMIZE latency" in report
    assert "OBJECTIVE_RANKING" in report
    assert "Selected by MINIMIZE of measured latency" in report


def test_maximize_bandwidth_ranks_receiver_throughput_not_capacity_or_sender(
    monkeypatch,
):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="bandwidth",
            direction=OptimizationDirection.MAXIMIZE,
            unit="Mbps",
        )
    )
    result, _, _ = _run(
        monkeypatch,
        intent,
        graph=_graph(bandwidths=(100, 10)),
        throughputs=[
            ThroughputResult(
                sent_mbps=80,
                received_mbps=30,
                duration_s=1,
                succeeded=True,
                raw_output="sender 80 Mbps; receiver 30 Mbps",
            ),
            ThroughputResult(
                sent_mbps=35,
                received_mbps=40,
                duration_s=1,
                succeeded=True,
                raw_output="sender 35 Mbps; receiver 40 Mbps",
            ),
        ],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    assert result.selection.selection_method.value == "OBJECTIVE_RANKING"
    assert result.selection.selected_candidate.path == result.probes[1].path
    assert [item.objective_value for item in result.selection.candidates] == [30, 40]
    assert result.probes[1].measurements["bandwidth"].received_mbps == 40


def test_constrained_latency_objective_skips_infeasible_and_never_overrides_bandwidth(
    monkeypatch,
):
    intent = _intent(
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        graph=_graph(bandwidths=(10, 50)),
        pings=[_ping(1), _ping(2)],
        throughputs=[_throughput(25)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    assert result.probes[0].skip_reason is not None
    assert result.probes[0].deployment is None
    assert result.probes[1].observations[0].status == ObservationStatus.VALID
    assert result.probes[1].objective_observation.value == 1
    assert result.selection.selected_candidate.path == result.probes[1].path
    assert result.selection.selected_candidate.hard_constraint_status == (
        EvaluationStatus.SATISFIED
    )
    assert len(deployments) == 2
    assert len(cleanups) == 1


def test_failed_hard_constraint_prevents_objective_selection_and_final_deployment(
    monkeypatch,
):
    intent = _intent(
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        graph=_graph(bandwidths=(10, 50)),
        pings=[_ping(1), _ping(2)],
        throughputs=[_throughput(15)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.NO_SATISFYING_CANDIDATE
    assert result.selection.status.value == "NO_SATISFYING_CANDIDATE"
    assert result.selection.selected_candidate is None
    assert len(deployments) == 1
    assert len(cleanups) == 1
    assert result.final_deployment is None


def test_objective_missing_measurement_and_stale_measurement_are_insufficient(
    monkeypatch,
):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    missing, deployments, cleanups = _run(
        monkeypatch,
        intent,
        pings=[_ping(received=0), _ping(2), _ping(1)],
    )

    assert missing.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert missing.selection is not None
    assert missing.selection.selected_candidate is None
    assert len(deployments) == 2
    assert len(cleanups) == 2

    stale, _, _ = _run(
        monkeypatch,
        intent,
        orchestration_options={"measurement_max_age": timedelta(0)},
    )
    assert stale.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert stale.selection is not None
    assert stale.selection.selected_candidate is None


def test_no_valid_objective_measurements_return_insufficient_evidence(monkeypatch):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        pings=[_ping(received=0), _ping(received=0)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.selection is not None
    assert result.selection.selected_candidate is None
    assert len(deployments) == 2
    assert len(cleanups) == 2
    assert all(probe.objective_observation.status == ObservationStatus.FAILED for probe in result.probes)
    assert result.final_deployment is None


def test_objective_probe_cleanup_failure_blocks_selection(monkeypatch):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        failed_cleanup_at=1,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert "cleanup failed" in result.error.lower()
    assert len(deployments) == 1
    assert len(cleanups) == 1
    assert not cleanups[0].success
    assert result.selection is None


def test_objective_final_deployment_failure_is_reported_and_cleaned(monkeypatch):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        failed_deployment_at=3,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert result.selection.selected_candidate is not None
    assert result.final_deployment is not None
    assert not result.final_deployment.success
    assert len(deployments) == 3
    assert len(cleanups) == 3
    assert cleanups[-1].success


def test_objective_ties_use_deterministic_path_fingerprint(monkeypatch):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    result, _, _ = _run(
        monkeypatch,
        intent,
        pings=[_ping(2), _ping(2), _ping(2)],
    )

    expected = min(
        result.selection.candidates,
        key=lambda candidate: candidate.path_fingerprint,
    )
    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    assert result.selection.selected_candidate == expected


def test_truncated_objective_enumeration_does_not_probe_or_claim_optimality(
    monkeypatch,
):
    intent = _intent(
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        )
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        orchestration_options={"candidate_limit": 1},
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.enumeration.truncated
    assert not result.probes
    assert not deployments
    assert not cleanups
    record = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert record["candidate_discovery"]["truncated"] is True
    assert record["selection"]["status"] == "NOT_REACHED"


def test_measurement_failure_returns_insufficient_evidence_without_final_deploy(monkeypatch):
    intent = _intent(_constraint("latency", Comparison.LTE, 50, "ms"))
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        pings=[_ping(1, received=0), _ping(2), _ping()],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.selection is None
    assert len(deployments) == 2
    assert all(item.success for item in cleanups)


def test_bandwidth_does_not_fall_back_to_sender_rate_when_receiver_rate_is_missing(monkeypatch):
    intent = _intent(_constraint("bandwidth", Comparison.GTE, 20, "Mbps"))
    result, _, _ = _run(
        monkeypatch,
        intent,
        throughputs=[
            ThroughputResult(
                sent_mbps=35,
                received_mbps=None,
                succeeded=True,
                raw_output="sender rate only",
            ),
            _throughput(30),
        ],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.probes[0].observations[0].status == ObservationStatus.FAILED


def test_one_candidate_can_pass_while_another_fails(monkeypatch):
    intent = _intent(_constraint("bandwidth", Comparison.GTE, 20, "Mbps"))
    result, _, _ = _run(
        monkeypatch,
        intent,
        throughputs=[_throughput(15), _throughput(25)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    evaluations = result.selection.plan_evaluation.candidates
    assert [item.status for item in evaluations] == [
        EvaluationStatus.VIOLATED,
        EvaluationStatus.SATISFIED,
    ]
    assert result.selection.selected_candidate.path == result.probes[1].path


def test_statically_infeasible_candidate_is_skipped_and_other_path_is_measured(monkeypatch):
    intent = _intent(
        _constraint("latency", Comparison.LTE, 50, "ms"),
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
    )
    graph = _graph(bandwidths=(10, 50))
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        graph=graph,
        throughputs=[_throughput(35)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.SUCCEEDED
    assert len(result.probes) == 2
    assert result.probes[0].skip_reason is not None
    assert "statically infeasible" in result.probes[0].skip_reason.lower()
    assert result.probes[0].preflight.proven_infeasible
    assert result.probes[0].deployment is None
    assert result.probes[0].measurements == {}
    assert result.probes[1].skip_reason is None
    assert result.probes[1].measurements["bandwidth"].received_mbps == 35
    assert result.probes[1].observations[0].status == ObservationStatus.VALID
    assert result.probes[1].observations[1].status == ObservationStatus.VALID
    assert result.selection.selected_candidate.path == result.probes[1].path
    assert len(deployments) == 2
    assert len(cleanups) == 1
    assert cleanups[0].success

    record = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert record["candidates"][0]["stages"]["probe_preflight"]["status"] == (
        "SKIPPED_INFEASIBLE"
    )
    assert record["candidates"][0]["measurements"] == {}
    assert record["candidates"][1]["measurements"]["bandwidth"]["received_mbps"] == 35
    report = open(result.evidence_markdown_path, encoding="utf-8").read()
    assert "SKIPPED_INFEASIBLE" in report
    assert "statically infeasible" in report


def test_infeasible_candidate_still_requires_fresh_operational_preflight(monkeypatch):
    graph, fresh, deployments, cleanups = _install_mocks(
        monkeypatch, graph=_graph(bandwidths=(10, 50))
    )
    changed = _snapshot(graph, down_port=(1, 1))
    intent = _intent(
        _constraint("latency", Comparison.LTE, 50, "ms"),
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
    )
    result = orchestration.run_generalized_constraint_demo(
        graph,
        _Host("h1"),
        _Host("h4"),
        intent,
        _snapshot(graph),
        fresh_snapshot_provider=lambda: changed,
        ping_count=3,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert result.probes[0].preflight.status == "FAILED"
    assert result.probes[0].skip_reason is None
    assert not deployments
    assert not cleanups


def test_all_statically_infeasible_candidates_return_without_deployment(monkeypatch):
    intent = _intent(
        _constraint("latency", Comparison.LTE, 50, "ms"),
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
    )
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        graph=_graph(bandwidths=(10, 15)),
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.NO_FEASIBLE_CANDIDATE, (
        result.error,
        result.selection.status.value if result.selection else None,
    )
    assert result.selection is not None
    assert result.selection.status.value == "NO_ELIGIBLE_CANDIDATE"
    assert len(result.probes) == 2
    assert all(probe.skip_reason for probe in result.probes)
    assert not deployments
    assert not cleanups
    assert result.final_deployment is None
    assert result.final_preflight is None


def test_all_candidates_violating_constraints_returns_no_satisfying_candidate(monkeypatch):
    intent = _intent(_constraint("bandwidth", Comparison.GTE, 50, "Mbps"))
    result, _, _ = _run(
        monkeypatch,
        intent,
        throughputs=[_throughput(15), _throughput(25)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.NO_SATISFYING_CANDIDATE
    assert result.selection.status.value == "NO_SATISFYING_CANDIDATE"


def test_missing_rtt_is_not_valid_latency_constraint_evidence(monkeypatch):
    no_rtt = LatencyResult(
        packets_sent=3,
        packets_received=3,
        packet_loss_pct=0,
        packets_requested=3,
        rtt_avg_ms=None,
        raw_output="ping replies without RTT summary",
    )
    intent = _intent(_constraint("latency", Comparison.LTE, 50, "ms"))
    result, _, _ = _run(
        monkeypatch,
        intent,
        pings=[no_rtt, _ping(2), _ping()],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.probes[0].observations[0].status == ObservationStatus.FAILED


def test_invalid_measurement_blocks_global_selection_even_with_other_violation(monkeypatch):
    no_rtt = LatencyResult(
        packets_sent=3,
        packets_received=3,
        packet_loss_pct=0,
        packets_requested=3,
        raw_output="missing RTT",
    )
    intent = _intent(
        _constraint("latency", Comparison.LTE, 50, "ms"),
        _constraint("bandwidth", Comparison.GTE, 20, "Mbps"),
    )
    result, _, _ = _run(
        monkeypatch,
        intent,
        pings=[no_rtt, _ping(2), _ping()],
        throughputs=[_throughput(10), _throughput(25)],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.selection is None


def test_stale_candidate_measurements_are_insufficient(monkeypatch):
    intent = _intent(_constraint("latency", Comparison.LTE, 50, "ms"))
    result, _, _ = _run(
        monkeypatch,
        intent,
        orchestration_options={"measurement_max_age": timedelta(0)},
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert result.selection is None


def test_evaluator_rejects_candidate_identity_mismatch():
    graph = _graph()
    plan = orchestration.build_generalized_plan(
        graph, _intent(_constraint("latency", Comparison.LTE, 50, "ms"))
    )
    enumeration = enumerate_candidate_paths(graph, "h1", "h4", 10)
    paths = enumeration.paths
    first = orchestration.assess_path_feasibility(plan, paths[0])
    second = orchestration.assess_path_feasibility(plan, paths[1])
    request_id = planning_request_fingerprint(plan.request)
    mismatched = MetricObservation(
        target=EvaluationTarget(
            candidate_id=first.candidate_id,
            request_fingerprint=request_id,
            path_fingerprint=physical_path_fingerprint(paths[1]),
            requirement_id=plan.hard_constraints[0].requirement_id,
        ),
        metric="latency",
        unit="ms",
        value=2,
        status=ObservationStatus.VALID,
        collected_at=datetime.now(timezone.utc),
        source="mininet-ping",
        evaluation_run_id="identity-test",
    )
    with pytest.raises(EvaluationInputError, match="target"):
        evaluate_hard_constraints(
            plan,
            tuple(
                EvaluationCandidate(
                    candidate_id=assessment.candidate_id,
                    request_fingerprint=request_id,
                    path=path,
                    feasibility=assessment.feasibility,
                )
                for assessment, path in zip((first, second), paths, strict=True)
            ),
            (mismatched,),
            evaluated_at=datetime.now(timezone.utc),
            freshness_policy=FreshnessPolicy(
                limits=(
                    MetricFreshnessLimit(
                        metric="latency",
                        max_age=timedelta(minutes=1),
                    ),
                )
            ),
            evaluation_run_id="identity-test",
        )


def test_bandwidth_missing_receiver_measurement_is_insufficient(monkeypatch):
    intent = _intent(_constraint("bandwidth", Comparison.GTE, 20, "Mbps"))
    result, deployments, _ = _run(
        monkeypatch,
        intent,
        throughputs=[
            ThroughputResult(succeeded=True, raw_output="missing receiver rate"),
            _throughput(30),
        ],
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert len(deployments) == 2


def test_cleanup_failure_stops_before_selection_or_final_deployment(monkeypatch):
    intent = _intent(_constraint("bandwidth", Comparison.GTE, 20, "Mbps"))
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        failed_cleanup_at=1,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert "cleanup failed" in result.error.lower()
    assert len(deployments) == 1
    assert len(cleanups) == 1


def test_temporary_deployment_failure_stops_without_retry(monkeypatch):
    intent = _intent(_constraint("latency", Comparison.LTE, 50, "ms"))
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        failed_deployment_at=1,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert len(deployments) == 1
    assert len(cleanups) == 1
    assert cleanups[0].success


def test_changed_topology_is_rejected_by_candidate_probe_preflight(monkeypatch):
    graph, fresh, deployments, cleanups = _install_mocks(monkeypatch)
    changed = _snapshot(graph, down_port=(1, 2))
    result = orchestration.run_generalized_constraint_demo(
        graph,
        _Host("h1"),
        _Host("h4"),
        _intent(_constraint("latency", Comparison.LTE, 50, "ms")),
        _snapshot(graph),
        fresh_snapshot_provider=lambda: changed,
        ping_count=3,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert "preflight" in result.error.lower()
    assert not deployments
    assert not cleanups


def test_final_preflight_rejection_does_not_deploy_selected_candidate(monkeypatch):
    graph = _graph()
    changed = _snapshot(graph, down_port=(1, 2))
    result, deployments, cleanups = _run(
        monkeypatch,
        _intent(_constraint("latency", Comparison.LTE, 50, "ms")),
        final_snapshot=changed,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert result.final_preflight is not None
    assert result.final_preflight.status.value != "PASSED"
    assert len(deployments) == 2
    assert len(cleanups) == 2


def test_final_deployment_readback_failure_is_reported_and_cleaned(monkeypatch):
    intent = _intent(_constraint("bandwidth", Comparison.GTE, 20, "Mbps"))
    result, deployments, cleanups = _run(
        monkeypatch,
        intent,
        failed_deployment_at=3,
    )

    assert result.status == orchestration.GeneralizedConstraintStatus.FAILED
    assert result.final_deployment is not None
    assert not result.final_deployment.success
    assert len(deployments) == 3
    assert len(cleanups) == 3
    assert cleanups[-1].success


@pytest.mark.parametrize(
    ("comparison", "value", "lower", "upper", "expected"),
    [
        (Comparison.GT, 4, None, None, EvaluationStatus.SATISFIED),
        (Comparison.GTE, 5, None, None, EvaluationStatus.SATISFIED),
        (Comparison.LT, 6, None, None, EvaluationStatus.SATISFIED),
        (Comparison.LTE, 5, None, None, EvaluationStatus.SATISFIED),
        (Comparison.EQ, 5, None, None, EvaluationStatus.SATISFIED),
        (Comparison.BETWEEN, None, 4, 6, EvaluationStatus.SATISFIED),
    ],
)
def test_generalized_plan_evaluates_all_comparison_operators(
    comparison, value, lower, upper, expected
):
    constraint = MetricConstraint(
        metric="latency",
        comparison=comparison,
        unit="ms",
        value=value,
        lower_bound=lower,
        upper_bound=upper,
    )
    graph = _graph()
    plan = orchestration.build_generalized_plan(graph, _intent(constraint))
    enumeration = enumerate_candidate_paths(graph, "h1", "h4", 10)
    path = enumeration.paths[0]
    candidate_id = orchestration.physical_candidate_id(plan, path)
    request_id = planning_request_fingerprint(plan.request)
    observation = MetricObservation(
        target=EvaluationTarget(
            candidate_id=candidate_id,
            request_fingerprint=request_id,
            path_fingerprint=physical_path_fingerprint(path),
            requirement_id=plan.hard_constraints[0].requirement_id,
        ),
        metric="latency",
        unit="ms",
        value=5,
        status=ObservationStatus.VALID,
        collected_at=datetime.now(timezone.utc),
        source="mininet-ping",
        evaluation_run_id="comparison-test",
    )
    now = datetime.now(timezone.utc)
    evaluation = evaluate_hard_constraints(
        plan,
        (
            EvaluationCandidate(
                candidate_id=candidate_id,
                request_fingerprint=request_id,
                path=path,
                feasibility=orchestration.assess_path_feasibility(plan, path).feasibility,
            ),
        ),
        (observation,),
        evaluated_at=now,
        freshness_policy=FreshnessPolicy(
            limits=(MetricFreshnessLimit(metric="latency", max_age=timedelta(minutes=1)),)
        ),
        evaluation_run_id="comparison-test",
    )
    assert evaluation.candidates[0].status == expected


def test_unsupported_metric_returns_insufficient_evidence_without_deployment(monkeypatch):
    constraint = _constraint("jitter", Comparison.LTE, 5, "ms")
    result, deployments, cleanups = _run(monkeypatch, _intent(constraint))

    assert result.status == orchestration.GeneralizedConstraintStatus.INSUFFICIENT_EVIDENCE
    assert "unsupported" in result.error.lower()
    assert not deployments
    assert not cleanups
