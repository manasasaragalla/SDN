from datetime import datetime, timedelta, timezone
import json

import pytest

from backend.execution.models import (
    PortOperationalState,
    PreflightStatus,
    SnapshotStatus,
    TopologySnapshot,
)
from backend.models.measurement import LatencyResult
from backend.models.network import Host, Link, TopologyGraph
from backend.models.deployment import (
    PhysicalCleanupResult,
    PhysicalCleanupState,
    PhysicalDeploymentResult,
    PhysicalDeploymentState,
)
from backend.models.fingerprints import model_fingerprint
from backend.orchestration import generalized_latency as orchestration
from backend.orchestration import latency_evidence
from backend.planner.candidate_selection import ObjectiveObservation, SelectionStatus, physical_candidate_id
from backend.planner.constraint_evaluation import (
    FreshnessPolicy,
    MetricFreshnessLimit,
    ObservationStatus,
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.path_enumeration import enumerate_candidate_paths


@pytest.fixture(autouse=True)
def isolate_execution_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(latency_evidence, "JSON_OUTPUT_DIR", tmp_path / "results")
    monkeypatch.setattr(latency_evidence, "MARKDOWN_OUTPUT_DIR", tmp_path / "reports")


def _host(name, ip, switch, port):
    return Host(
        name=name,
        ip=ip,
        mac=f"00:00:00:00:00:{int(ip.rsplit('.', 1)[1]):02x}",
        switch=switch,
        switch_port=port,
    )


def _graph(capacity=10.0):
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h1": _host("h1", "10.0.0.1", "s1", 1),
            "h4": _host("h4", "10.0.0.4", "s4", 1),
        },
        links=[
            Link(
                node_a="s1", port_a=2, node_b="s2", port_b=1,
                bw_mbps=capacity, intf_a="s1-eth2", intf_b="s2-eth1",
            ),
            Link(
                node_a="s2", port_a=2, node_b="s4", port_b=2,
                bw_mbps=capacity, intf_a="s2-eth2", intf_b="s4-eth2",
            ),
            Link(
                node_a="s1", port_a=3, node_b="s3", port_b=1,
                bw_mbps=capacity * 5, intf_a="s1-eth3", intf_b="s3-eth1",
            ),
            Link(
                node_a="s3", port_a=2, node_b="s4", port_b=3,
                bw_mbps=capacity * 5, intf_a="s3-eth2", intf_b="s4-eth3",
            ),
        ],
    )


def _snapshot(graph, *, down_port=None):
    ports = set()
    for host in graph.hosts.values():
        ports.add((graph.switches[host.switch], host.switch_port))
    for link in graph.links:
        ports.add((graph.switches[link.node_a], link.port_a))
        ports.add((graph.switches[link.node_b], link.port_b))
    now = datetime.now(timezone.utc)
    return TopologySnapshot(
        configured_topology=graph,
        captured_at=now,
        status=SnapshotStatus.COMPLETE,
        connected_switch_dpids=tuple(sorted(graph.switches.values())),
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


def _success_deployment(cookie, count=8):
    return PhysicalDeploymentResult(
        operation_cookie=cookie,
        dpids=(1, 2, 3, 4),
        requested_count=count,
        accepted_count=count,
        verified_count=count,
        state=PhysicalDeploymentState.SUCCEEDED,
    )


def _cleanup(cookie, *, succeeded=True):
    return PhysicalCleanupResult(
        operation_cookie=cookie,
        requested_dpids=(1, 2, 3, 4),
        accepted_delete_count=4 if succeeded else 0,
        remaining_flow_count=0 if succeeded else 2,
        state=(
            PhysicalCleanupState.SUCCEEDED
            if succeeded
            else PhysicalCleanupState.FAILED
        ),
    )


def _valid_ping(rtt=2.0, count=3):
    return LatencyResult(
        packets_sent=count,
        packets_received=count,
        packet_loss_pct=0.0,
        packets_requested=count,
        rtt_avg_ms=rtt,
        raw_output="measured ping result",
    )


def _run(monkeypatch, *, graph=None, measurements=None, deployments=None,
         cleanup_results=None, snapshots=None, ping_count=3,
         measurement_error=False):
    graph = graph or _graph()
    planned = _snapshot(graph)
    snapshot_iter = iter(snapshots or [])
    deploy_iter = iter(deployments or [])
    cleanup_iter = iter(cleanup_results or [])
    measurement_iter = iter(measurements or [_valid_ping(), _valid_ping(4), _valid_ping(2)])
    deploy_calls = []
    cleanup_calls = []

    def fresh_snapshot():
        try:
            snapshot = next(snapshot_iter)
            return TopologySnapshot(
                configured_topology=snapshot.configured_topology,
                captured_at=datetime.now(timezone.utc),
                status=snapshot.status,
                connected_switch_dpids=snapshot.connected_switch_dpids,
                port_states=snapshot.port_states,
            )
        except StopIteration:
            return _snapshot(graph)

    def deploy(rules, base_url):
        deploy_calls.append((rules, base_url))
        try:
            return next(deploy_iter)
        except StopIteration:
            return _success_deployment(0x1000 + len(deploy_calls), len(rules))

    def cleanup(deployment, base_url):
        cleanup_calls.append(deployment.operation_cookie)
        try:
            return next(cleanup_iter)
        except StopIteration:
            return _cleanup(deployment.operation_cookie)

    def measure(*_args, **_kwargs):
        if measurement_error:
            raise RuntimeError("ping command failed")
        return next(measurement_iter)

    monkeypatch.setattr(orchestration, "deploy_physical_path_rules", deploy)
    monkeypatch.setattr(orchestration, "cleanup_physical_path_deployment", cleanup)
    monkeypatch.setattr(orchestration, "measure_latency", measure)
    result = orchestration.run_generalized_latency_demo(
        graph,
        object(),
        planned,
        fresh_snapshot_provider=fresh_snapshot,
        base_url="http://ryu.test",
        ping_count=ping_count,
    )
    return result, deploy_calls, cleanup_calls


def test_measures_both_paths_selects_lowest_rtt_and_deploys_final(monkeypatch):
    graph = _graph()
    result, deployed, cleaned = _run(
        monkeypatch,
        graph=graph,
        measurements=[_valid_ping(3), _valid_ping(8), _valid_ping(3.2)],
    )

    assert result.status == orchestration.GeneralizedLatencyStatus.SUCCEEDED
    assert len(result.probes) == 2
    assert all(probe.observation.status == ObservationStatus.VALID for probe in result.probes)
    assert result.selection.status == SelectionStatus.SELECTED
    assert result.selection.selected_candidate.path.nodes == (
        "h1", "s1", "s2", "s4", "h4"
    )
    assert len(deployed) == 3
    assert len(cleaned) == 2
    assert result.final_deployment.success
    assert result.final_measurement.rtt_avg_ms == 3.2
    assert result.final_preflight.status == PreflightStatus.PASSED
    evidence = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    report = open(result.evidence_markdown_path, encoding="utf-8").read()
    assert evidence["execution_id"] == result.execution_id
    assert len(evidence["candidate_discovery"]["paths"]) == 2
    assert len(evidence["candidates"]) == 2
    assert len({candidate["measurement_run_id"] for candidate in evidence["candidates"]}) == 2
    assert all(candidate["deployment"]["success"] for candidate in evidence["candidates"])
    assert all(
        candidate["deployment"]["readback"]["status"] == "VERIFIED"
        for candidate in evidence["candidates"]
    )
    assert all(candidate["cleanup"]["success"] for candidate in evidence["candidates"])
    assert evidence["selection"]["objective"]["direction"] == "MINIMIZE"
    assert sorted(
        item["objective_value"]
        for item in evidence["selection"]["candidate_values"]
    ) == [3.0, 8.0]
    assert evidence["final"]["selected_path"]["nodes"] == [
        "h1", "s1", "s2", "s4", "h4"
    ]
    assert evidence["final"]["preflight"]["status"] == "PASSED"
    assert evidence["final"]["deployment"]["verified_count"] == 12
    assert evidence["final"]["connectivity"]["measurement"]["raw_output"] == "measured ping result"
    assert evidence["configuration"]["ping_count"] == 3
    assert "Raw final ping output" in report
    assert "Selection and final execution" in report
    for candidate in evidence["candidates"]:
        assert candidate["probe_operation_id"] in report
        assert f"cookie `{candidate['deployment']['operation_cookie']}`" in report
        assert str(candidate["measurement"]["rtt_avg_ms"]) in report
    assert result.evidence_json_path.endswith(f"generalized_latency_{result.execution_id}.json")
    assert result.evidence_markdown_path.endswith(f"generalized_latency_{result.execution_id}.md")


@pytest.mark.parametrize(
    "measurement",
    [
        LatencyResult(
            packets_sent=3, packets_received=0, packet_loss_pct=100,
            packets_requested=3, rtt_avg_ms=None, raw_output="all lost",
        ),
        LatencyResult(
            packets_sent=3, packets_received=3, packet_loss_pct=0,
            packets_requested=3, rtt_avg_ms=None, raw_output="no RTT summary",
        ),
        LatencyResult(
            packets_sent=3, packets_received=3, packet_loss_pct=0,
            packets_requested=3, rtt_avg_ms=float("inf"), raw_output="invalid RTT",
        ),
    ],
)
def test_failed_ping_or_invalid_rtt_blocks_global_selection(monkeypatch, measurement):
    result, deployed, cleaned = _run(
        monkeypatch,
        measurements=[measurement],
    )

    assert result.status == orchestration.GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE
    assert result.selection is None
    assert result.probes[0].observation.status == ObservationStatus.FAILED
    assert len(deployed) == 1
    assert cleaned == [0x1001]


def test_measurement_exception_is_reported_after_probe_cleanup(monkeypatch):
    result, _, cleaned = _run(monkeypatch, measurement_error=True)

    assert result.status == orchestration.GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE
    assert "Temporary latency measurement failed: ping command failed" in result.error
    assert cleaned == [0x1001]


def test_each_run_gets_a_distinct_execution_id(monkeypatch):
    first, _, _ = _run(monkeypatch)
    second, _, _ = _run(monkeypatch)

    assert first.execution_id != second.execution_id
    assert first.evidence_json_path != second.evidence_json_path
    assert first.evidence_markdown_path != second.evidence_markdown_path


def test_temporary_deployment_failure_is_cleaned_and_stops(monkeypatch):
    partial = PhysicalDeploymentResult(
        operation_cookie=0x44,
        dpids=(1, 2),
        requested_count=8,
        accepted_count=4,
        verified_count=4,
        state=PhysicalDeploymentState.PARTIAL,
        errors=["one rule missing"],
    )
    result, deployed, cleaned = _run(monkeypatch, deployments=[partial])

    assert result.status == orchestration.GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE
    assert "Temporary deployment" in result.error
    assert len(deployed) == 1
    assert cleaned == [0x44]
    assert result.probes[0].measurement is None
    evidence = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert evidence["candidates"][0]["deployment"]["status"] == "PARTIAL"
    assert evidence["candidates"][0]["cleanup"]["success"] is True
    assert evidence["candidates"][1]["preflight"]["status"] == "NOT_REACHED"


def test_cleanup_failure_stops_without_selection(monkeypatch):
    result, _, cleaned = _run(
        monkeypatch,
        cleanup_results=[_cleanup(0x1001, succeeded=False)],
    )

    assert result.status == orchestration.GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE
    assert result.selection is None
    assert "cleanup failed or is uncertain" in result.error
    assert cleaned == [0x1001]
    evidence = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert evidence["candidates"][0]["cleanup"]["success"] is False
    assert evidence["candidates"][0]["stages"]["probe_cleanup"]["status"] == "FAILED"


def test_topology_change_before_probe_preflight_blocks_deployment(monkeypatch):
    graph = _graph()
    changed = _snapshot(_graph(capacity=12))
    result, deployed, _ = _run(monkeypatch, graph=graph, snapshots=[changed])

    assert result.status == orchestration.GeneralizedLatencyStatus.INSUFFICIENT_EVIDENCE
    assert "Topology changed since planning" in result.error
    assert deployed == []


def test_final_preflight_rejection_blocks_final_deployment(monkeypatch):
    graph = _graph()
    down_snapshot = _snapshot(graph, down_port=(1, 1))
    result, deployed, _ = _run(
        monkeypatch,
        graph=graph,
        snapshots=[_snapshot(graph), _snapshot(graph), down_snapshot],
    )

    assert result.status == orchestration.GeneralizedLatencyStatus.FAILED
    assert result.final_preflight.status == PreflightStatus.FAILED
    assert len(deployed) == 2


def test_final_deployment_readback_failure_is_reported(monkeypatch):
    failed_final = PhysicalDeploymentResult(
        operation_cookie=0x1003,
        dpids=(1, 2, 3, 4),
        requested_count=8,
        accepted_count=8,
        verified_count=7,
        state=PhysicalDeploymentState.PARTIAL,
        errors=["readback missing"],
    )
    result, deployed, cleaned = _run(
        monkeypatch,
        deployments=[
            _success_deployment(0x1001),
            _success_deployment(0x1002),
            failed_final,
        ],
    )

    assert result.status == orchestration.GeneralizedLatencyStatus.FAILED
    assert "Final deployment was not fully verified" in result.error
    assert len(deployed) == 3
    assert cleaned == [0x1001, 0x1002, 0x1003]
    evidence = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert evidence["final"]["deployment"]["status"] == "PARTIAL"
    assert evidence["final"]["deployment"]["verified_count"] == 7
    assert evidence["final"]["deployment"]["cleanup"]["success"] is True


def test_final_connectivity_failure_is_persisted_with_cleanup(monkeypatch):
    failed_ping = LatencyResult(
        packets_sent=3,
        packets_received=0,
        packet_loss_pct=100,
        packets_requested=3,
        raw_output="3 packets transmitted, 0 received, 100% packet loss",
    )
    result, _, cleaned = _run(
        monkeypatch,
        measurements=[_valid_ping(2), _valid_ping(4), failed_ping],
    )

    assert result.status == orchestration.GeneralizedLatencyStatus.FAILED
    assert result.final_cleanup.success
    assert cleaned == [0x1001, 0x1002, 0x1003]
    evidence = json.loads(open(result.evidence_json_path, encoding="utf-8").read())
    assert evidence["final"]["connectivity"]["status"] == "FAILED"
    assert evidence["final"]["connectivity"]["measurement"]["raw_output"] == failed_ping.raw_output
    assert evidence["final"]["stages"]["final_cleanup"]["status"] == "SUCCEEDED"


def test_unexpected_failure_still_persists_failure_record(monkeypatch):
    graph = _graph()
    monkeypatch.setattr(
        orchestration,
        "_run_generalized_latency_demo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected failure")),
    )

    with pytest.raises(RuntimeError, match="unexpected failure"):
        orchestration.run_generalized_latency_demo(
            graph,
            object(),
            _snapshot(graph),
            fresh_snapshot_provider=lambda: _snapshot(graph),
        )

    paths = list(latency_evidence.JSON_OUTPUT_DIR.glob("generalized_latency_*.json"))
    assert len(paths) == 1
    record = json.loads(paths[0].read_text(encoding="utf-8"))
    assert record["execution_status"] == "FAILED"
    assert record["failure"]["evidence_status"] == "PARTIAL"
    assert "unexpected failure" in record["failure"]["reason"]


def test_unexpected_selection_error_preserves_completed_probe_evidence(monkeypatch):
    graph = _graph()
    cookies = iter((0x7001, 0x7002, 0x7003))
    monkeypatch.setattr(
        orchestration,
        "deploy_physical_path_rules",
        lambda rules, base_url: _success_deployment(next(cookies), len(rules)),
    )
    monkeypatch.setattr(
        orchestration,
        "cleanup_physical_path_deployment",
        lambda deployment, base_url: _cleanup(deployment.operation_cookie),
    )
    monkeypatch.setattr(
        orchestration,
        "measure_latency",
        lambda *_args, **_kwargs: _valid_ping(2.5),
    )
    monkeypatch.setattr(
        orchestration,
        "select_latency_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("selector invariant failed")
        ),
    )

    with pytest.raises(RuntimeError, match="selector invariant failed"):
        orchestration.run_generalized_latency_demo(
            graph,
            object(),
            _snapshot(graph),
            fresh_snapshot_provider=lambda: _snapshot(graph),
        )

    paths = list(latency_evidence.JSON_OUTPUT_DIR.glob("generalized_latency_*.json"))
    assert len(paths) == 1
    record = json.loads(paths[0].read_text(encoding="utf-8"))
    assert record["execution_status"] == "FAILED"
    assert len(record["candidates"]) == 2
    assert all(candidate["measurement"]["valid"] for candidate in record["candidates"])
    assert all(candidate["cleanup"]["success"] for candidate in record["candidates"])
    assert "selector invariant failed" in record["failure"]["reason"]


def test_stale_and_misbound_objective_observations_are_rejected():
    graph = _graph()
    plan = orchestration.build_latency_plan(graph)
    enumeration = enumerate_candidate_paths(graph, "h1", "h4", candidate_limit=10)
    run_id = "observation-contract-test"
    now = datetime.now(timezone.utc)
    freshness = FreshnessPolicy(
        limits=(MetricFreshnessLimit(metric="latency", max_age=timedelta(seconds=5)),)
    )
    request_fp = planning_request_fingerprint(plan.request)
    plan_fp = model_fingerprint(plan)
    observations = []
    for path in enumeration.paths:
        observations.append(
            ObjectiveObservation(
                candidate_id=physical_candidate_id(plan, path),
                request_fingerprint=request_fp,
                plan_fingerprint=plan_fp,
                path_fingerprint=physical_path_fingerprint(path),
                observation_id="latency-objective-observation",
                requirement_id="latency-objective",
                evaluation_run_id=run_id,
                metric="latency",
                unit="ms",
                value=2.0,
                status=ObservationStatus.VALID,
                collected_at=now - timedelta(seconds=10),
                source="test",
            )
        )

    stale_result = orchestration.select_latency_candidates(
        plan,
        enumeration,
        tuple(observations),
        evaluation_run_id=run_id,
        evaluated_at=now,
        freshness_policy=freshness,
    )
    assert stale_result.status == SelectionStatus.INSUFFICIENT_EVIDENCE

    wrong_binding = observations[0].model_dump()
    wrong_binding["candidate_id"] = "other-candidate"
    with pytest.raises(ValueError, match="unknown candidate"):
        orchestration.select_latency_candidates(
            plan,
            enumeration,
            (ObjectiveObservation(**wrong_binding), observations[1]),
            evaluation_run_id=run_id,
            evaluated_at=now,
            freshness_policy=freshness,
        )


def test_live_snapshot_reader_uses_controller_observations(monkeypatch):
    graph = _graph()
    ports = {}
    for host in graph.hosts.values():
        ports.setdefault(graph.switches[host.switch], []).append(host.switch_port)
    for link in graph.links:
        ports.setdefault(graph.switches[link.node_a], []).append(link.port_a)
        ports.setdefault(graph.switches[link.node_b], []).append(link.port_b)

    def get_json(url):
        if url.endswith("/stats/switches"):
            return 200, [1, 2, 3, 4]
        dpid = int(url.rsplit("/", 1)[1])
        return 200, {
            str(dpid): [
                {"port_no": port, "config": 0, "state": 4}
                for port in ports[dpid]
            ]
        }

    monkeypatch.setattr(orchestration.ofctl_client, "_get_json", get_json)
    snapshot = orchestration.read_live_topology_snapshot(graph, "http://ryu.test")

    assert snapshot.status == SnapshotStatus.COMPLETE
    assert snapshot.connected_switch_dpids == (1, 2, 3, 4)
    assert len(snapshot.port_states) == 10
    assert all(port.admin_up and port.link_up for port in snapshot.port_states)
