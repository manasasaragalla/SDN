from datetime import datetime, timedelta, timezone
import json

import pytest
from pydantic import BaseModel, ValidationError

from backend.capabilities import resolve_capabilities
from backend.execution.models import (
    PortOperationalState,
    PreflightResult,
    PreflightStatus,
    SnapshotStatus,
    TopologySnapshot,
)
from backend.execution.preflight import (
    PreflightInputError,
    canonical_topology_fingerprint,
    validate_preflight,
)
from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    TrafficScope,
)
from backend.models.network import Host, Link, TopologyGraph
from backend.planner.candidate_selection import (
    SelectedCandidate,
    SelectionStatus,
    assess_path_feasibility,
    physical_candidate_id,
    select_candidate,
)
from backend.planner.constraint_evaluation import (
    EvaluationCandidate,
    EvaluationTarget,
    FreshnessPolicy,
    MetricFreshnessLimit,
    MetricObservation,
    ObservationStatus,
    evaluate_hard_constraints,
    physical_path_fingerprint,
    planning_request_fingerprint,
)
from backend.planner.models import (
    CandidateFeasibility,
    HardConstraintRequirement,
    MetricObservationPurpose,
    Plan,
    PlanningReadiness,
    PlanningRequest,
    RequiredMetricObservation,
)
from backend.planner.path_enumeration import enumerate_candidate_paths
from backend.planner.path_enumeration import PathEnumerationResult


NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def _host(name, switch, switch_port, last_octet):
    return Host(
        name=name,
        ip=f"10.0.0.{last_octet}",
        mac=f"00:00:00:00:00:{last_octet:02x}",
        switch=switch,
        switch_port=switch_port,
    )


def _graph(*, capacity=100.0, host_port=1, parallel=False):
    links = [
        Link(
            node_a="s1",
            port_a=2,
            node_b="s2",
            port_b=2,
            bw_mbps=capacity,
            intf_a="s1-eth2",
            intf_b="s2-eth2",
        )
    ]
    if parallel:
        links.append(
            Link(
                node_a="s2",
                port_a=3,
                node_b="s1",
                port_b=3,
                bw_mbps=capacity + 10,
                intf_a="s2-eth3",
                intf_b="s1-eth3",
            )
        )
    return TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": _host("h1", "s1", host_port, 1),
            "h4": _host("h4", "s2", 1, 4),
        },
        links=links,
    )


def _snapshot(graph, *, captured_at=NOW, status=SnapshotStatus.COMPLETE, connected=None, down_ports=()):
    port_keys = {
        (graph.switches[host.switch], host.switch_port)
        for host in graph.hosts.values()
    }
    port_keys.update(
        (graph.switches[link.node_a], link.port_a) for link in graph.links
    )
    port_keys.update(
        (graph.switches[link.node_b], link.port_b) for link in graph.links
    )
    ports = tuple(
        PortOperationalState(
            dpid=dpid,
            port_no=port,
            present=True,
            admin_up=(dpid, port) not in down_ports,
            link_up=(dpid, port) not in down_ports,
        )
        for dpid, port in sorted(port_keys)
    )
    return TopologySnapshot(
        configured_topology=graph,
        captured_at=captured_at,
        status=status,
        connected_switch_dpids=(
            tuple(sorted(graph.switches.values()))
            if connected is None
            else tuple(connected)
        ),
        port_states=ports if status == SnapshotStatus.COMPLETE else (),
    )


def _selected(graph, *, candidate_limit=10):
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        constraints=[
            MetricConstraint(
                metric="latency",
                comparison=Comparison.LTE,
                value=30,
                unit="ms",
            )
        ],
    )
    capabilities = resolve_capabilities(intent, graph=graph)
    request = PlanningRequest(
        intent=intent,
        topology=graph,
        capabilities=capabilities,
    )
    requirement = HardConstraintRequirement(
        requirement_id="latency-limit",
        constraint=intent.constraints[0],
    )
    plan = Plan(
        request=request,
        capability_readiness=capabilities.eligibility,
        planning_readiness=PlanningReadiness.CONDITIONAL,
        hard_constraints=(requirement,),
        required_observations=(
            RequiredMetricObservation(
                observation_id="latency-observation",
                requirement_id="latency-limit",
                purpose=MetricObservationPurpose.HARD_CONSTRAINT,
                metric="latency",
                unit="ms",
            ),
        ),
    )
    enumeration = enumerate_candidate_paths(
        graph,
        "h1",
        "h4",
        candidate_limit=candidate_limit,
    )
    request_fp = planning_request_fingerprint(request)
    candidates = []
    observations = []
    for path in enumeration.paths:
        assessment = assess_path_feasibility(plan, path)
        candidates.append(
            EvaluationCandidate(
                candidate_id=assessment.candidate_id,
                request_fingerprint=request_fp,
                path=path,
                feasibility=CandidateFeasibility.CANDIDATE,
            )
        )
        observations.append(
            MetricObservation(
                target=EvaluationTarget(
                    candidate_id=assessment.candidate_id,
                    request_fingerprint=request_fp,
                    path_fingerprint=physical_path_fingerprint(path),
                    requirement_id="latency-limit",
                ),
                metric="latency",
                unit="ms",
                value=20,
                status=ObservationStatus.VALID,
                collected_at=NOW,
                source="test",
                evaluation_run_id="run-1",
            )
        )
    freshness = FreshnessPolicy(
        limits=(
            MetricFreshnessLimit(
                metric="latency",
                max_age=timedelta(minutes=5),
            ),
        )
    )
    evaluation = evaluate_hard_constraints(
        plan,
        candidates,
        observations,
        evaluated_at=NOW,
        freshness_policy=freshness,
        evaluation_run_id="run-1",
    )
    selection = select_candidate(
        plan,
        enumeration,
        evaluation,
        evaluation_run_id="run-1",
        evaluated_at=NOW,
        freshness_policy=freshness,
    )
    assert selection.status == SelectionStatus.SELECTED
    return selection


def test_canonical_fingerprint_ignores_only_ordering_and_link_endpoint_orientation():
    graph = _graph(parallel=True)
    reversed_graph = TopologyGraph(
        switches={"s2": 2, "s1": 1},
        hosts={"h4": graph.hosts["h4"], "h1": graph.hosts["h1"]},
        links=[
            Link(
                node_a=link.node_b,
                port_a=link.port_b,
                node_b=link.node_a,
                port_b=link.port_a,
                bw_mbps=link.bw_mbps,
                intf_a=link.intf_b,
                intf_b=link.intf_a,
            )
            for link in reversed(graph.links)
        ],
    )

    assert canonical_topology_fingerprint(graph) == canonical_topology_fingerprint(
        reversed_graph
    )


@pytest.mark.parametrize(
    "changed_graph",
    [
        _graph(capacity=101.0),
        _graph(host_port=5),
        _graph(parallel=True),
    ],
)
def test_preflight_rejects_configured_topology_drift(changed_graph):
    planned_graph = _graph()
    selection = _selected(planned_graph)

    result = validate_preflight(
        selection,
        _snapshot(planned_graph, captured_at=NOW - timedelta(minutes=1)),
        _snapshot(changed_graph),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.FAILED
    assert "changed since planning" in result.reasons[0]


def test_preflight_passes_only_for_same_selected_physical_candidate():
    graph = _graph(parallel=True)
    selection = _selected(graph)

    result = validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
        _snapshot(graph),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.PASSED
    assert result.candidate_id == selection.selected_candidate.candidate_id
    assert result.path_fingerprint == selection.selected_candidate.path_fingerprint
    assert result.planned_topology_fingerprint == result.fresh_topology_fingerprint
    assert selection.selected_candidate.path.connections[1].link_identity in {
        (("s1", 2), ("s2", 2)),
        (("s1", 3), ("s2", 3)),
    }


def test_preflight_reports_stale_snapshot_as_unknown():
    graph = _graph()
    selection = _selected(graph)

    result = validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=10)),
        _snapshot(graph, captured_at=NOW - timedelta(minutes=10)),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.UNKNOWN
    assert "older than" in result.reasons[0]


@pytest.mark.parametrize(
    "status",
    [SnapshotStatus.UNAVAILABLE, SnapshotStatus.INCOMPLETE, SnapshotStatus.CONTRADICTORY],
)
def test_preflight_blocks_non_complete_snapshots(status):
    graph = _graph()
    selection = _selected(graph)

    result = validate_preflight(
        selection,
        _snapshot(graph, status=status),
        _snapshot(graph),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.UNKNOWN


def test_preflight_rejects_disconnected_switches():
    graph = _graph()
    selection = _selected(graph)

    result = validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
        _snapshot(graph, connected=(1,)),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.FAILED
    assert "connectivity" in result.reasons[0]


def test_preflight_rejects_down_configured_port():
    graph = _graph()
    selection = _selected(graph)

    result = validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
        _snapshot(graph, down_ports={(1, 2)}),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.FAILED
    assert "port" in result.reasons[0]


def test_preflight_rejects_explicitly_missing_configured_port():
    graph = _graph()
    selection = _selected(graph)
    snapshot = _snapshot(graph)
    observed_ports = list(snapshot.port_states)
    observed_ports[0] = PortOperationalState(
        dpid=observed_ports[0].dpid,
        port_no=observed_ports[0].port_no,
        present=False,
        admin_up=None,
        link_up=None,
    )
    missing_port_snapshot = TopologySnapshot(
        configured_topology=graph,
        captured_at=NOW,
        status=SnapshotStatus.COMPLETE,
        connected_switch_dpids=snapshot.connected_switch_dpids,
        port_states=tuple(observed_ports),
    )

    result = validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
        missing_port_snapshot,
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == PreflightStatus.FAILED
    assert "missing" in result.reasons[0]


def test_complete_snapshot_requires_every_configured_port():
    graph = _graph()
    with pytest.raises(ValidationError, match="every configured topology port"):
        TopologySnapshot(
            configured_topology=graph,
            captured_at=NOW,
            status=SnapshotStatus.COMPLETE,
            connected_switch_dpids=(1, 2),
            port_states=(),
        )


def test_execution_models_detach_mutable_topology_and_reject_unvalidated_copy():
    graph = _graph()
    snapshot = _snapshot(graph)

    exposed_graph = snapshot.configured_topology
    exposed_graph.switches["s1"] = 99
    assert snapshot.configured_topology.switches["s1"] == 1
    with pytest.raises(TypeError, match="model_copy"):
        snapshot.model_copy(update={"status": SnapshotStatus.INCOMPLETE})


def _passed_preflight(graph=None, *, candidate_limit=10):
    graph = graph or _graph()
    selection = _selected(graph, candidate_limit=candidate_limit)
    return validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
        _snapshot(graph),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )


def test_preflight_rejects_candidate_with_forged_path_fingerprint():
    graph = _graph()
    selection = _selected(graph)
    candidate = selection.selected_candidate
    forged = BaseModel.model_construct.__func__(
        SelectedCandidate,
        candidate_id=candidate.candidate_id,
        path=candidate.path,
        path_fingerprint="f" * 64,
        feasibility=candidate.feasibility,
        hard_constraint_status=candidate.hard_constraint_status,
        objective_value=candidate.objective_value,
    )
    object.__setattr__(selection, "selected_candidate", forged)
    object.__setattr__(
        selection,
        "candidates",
        tuple(forged if item.candidate_id == forged.candidate_id else item
              for item in selection.candidates),
    )

    with pytest.raises(PreflightInputError, match="path fingerprint"):
        validate_preflight(
            selection,
            _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
            _snapshot(graph),
            checked_at=NOW,
            max_snapshot_age=timedelta(minutes=2),
        )


def test_preflight_rejects_candidate_with_forged_candidate_id():
    graph = _graph()
    selection = _selected(graph)
    candidate = selection.selected_candidate
    forged = BaseModel.model_construct.__func__(
        SelectedCandidate,
        candidate_id="forged-candidate",
        path=candidate.path,
        path_fingerprint=candidate.path_fingerprint,
        feasibility=candidate.feasibility,
        hard_constraint_status=candidate.hard_constraint_status,
        objective_value=candidate.objective_value,
    )
    object.__setattr__(selection, "selected_candidate", forged)
    object.__setattr__(
        selection,
        "candidates",
        tuple(forged if item.path == forged.path else item
              for item in selection.candidates),
    )

    with pytest.raises(PreflightInputError, match="candidate ID"):
        validate_preflight(
            selection,
            _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
            _snapshot(graph),
            checked_at=NOW,
            max_snapshot_age=timedelta(minutes=2),
        )


def test_preflight_rejects_candidate_path_removed_from_selection_enumeration():
    graph = _graph(parallel=True)
    selection = _selected(graph)
    candidate = selection.selected_candidate
    object.__setattr__(
        selection.enumeration,
        "paths",
        tuple(path for path in selection.enumeration.paths if path != candidate.path),
    )

    with pytest.raises(PreflightInputError, match="authoritative topology-derived"):
        validate_preflight(
            selection,
            _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
            _snapshot(graph),
            checked_at=NOW,
            max_snapshot_age=timedelta(minutes=2),
        )


def _enumeration_with(result, *, paths=None, candidate_limit=None, truncated=None):
    enumeration = result.enumeration
    return PathEnumerationResult(
        source=enumeration.source,
        destination=enumeration.destination,
        candidate_limit=(
            enumeration.candidate_limit
            if candidate_limit is None
            else candidate_limit
        ),
        paths=enumeration.paths if paths is None else paths,
        truncated=enumeration.truncated if truncated is None else truncated,
    )


def _assert_passed_result_rejects_enumeration(result, enumeration, *, json_round_trip=False):
    payload = result.model_dump(mode="json" if json_round_trip else "python")
    payload["enumeration"] = (
        enumeration.model_dump(mode="json" if json_round_trip else "python")
    )
    with pytest.raises(
        ValidationError,
        match="candidate limit does not match|authoritative topology-derived",
    ):
        if json_round_trip:
            PreflightResult.model_validate_json(json.dumps(payload))
        else:
            PreflightResult.model_validate(payload)


def test_passed_preflight_rejects_parallel_paths_reduced_to_one():
    graph = _graph(parallel=True)
    result = _passed_preflight(graph)
    reduced = _enumeration_with(
        result,
        paths=(result.selected_path,),
        truncated=False,
    )

    _assert_passed_result_rejects_enumeration(result, reduced)
    _assert_passed_result_rejects_enumeration(
        result,
        reduced,
        json_round_trip=True,
    )


def test_passed_preflight_rejects_falsely_truncated_single_path_enumeration():
    graph = _graph()
    result = _passed_preflight(graph)
    forged = _enumeration_with(
        result,
        paths=(result.selected_path,),
        candidate_limit=1,
        truncated=True,
    )

    _assert_passed_result_rejects_enumeration(result, forged)
    _assert_passed_result_rejects_enumeration(
        result,
        forged,
        json_round_trip=True,
    )


def test_passed_preflight_rejects_incorrect_candidate_limit():
    graph = _graph(parallel=True)
    result = _passed_preflight(graph)
    forged = _enumeration_with(
        result,
        candidate_limit=1,
        paths=(result.enumeration.paths[0],),
        truncated=False,
    )

    _assert_passed_result_rejects_enumeration(result, forged)


def test_passed_preflight_rejects_reordered_enumeration_paths():
    graph = _graph(parallel=True)
    result = _passed_preflight(graph)
    reordered = _enumeration_with(
        result,
        paths=tuple(reversed(result.enumeration.paths)),
    )

    _assert_passed_result_rejects_enumeration(result, reordered)
    _assert_passed_result_rejects_enumeration(
        result,
        reordered,
        json_round_trip=True,
    )


@pytest.mark.parametrize("changed_field", ["from_port", "link_identity"])
def test_passed_preflight_rejects_altered_physical_path_entry(changed_field):
    graph = _graph(parallel=True)
    result = _passed_preflight(graph)
    path = result.enumeration.paths[0]
    path_data = path.model_dump()
    connection = path_data["connections"][1]
    alternate = result.enumeration.paths[1].connections[1]
    if changed_field == "from_port":
        connection["from_port"] += 10
        connection["link_identity"] = tuple(
            sorted(
                (
                    (connection["from_node"], connection["from_port"]),
                    (connection["to_node"], connection["to_port"]),
                )
            )
        )
    else:
        connection["from_port"] = alternate.from_port
        connection["to_port"] = alternate.to_port
        connection["link_identity"] = alternate.link_identity
    connections = list(path_data["connections"])
    connections[1] = connection
    path_data["connections"] = tuple(connections)
    altered_path = type(path).model_validate(path_data)
    altered_paths = (altered_path, *result.enumeration.paths[1:])
    altered = _enumeration_with(result, paths=altered_paths)

    _assert_passed_result_rejects_enumeration(result, altered)
    _assert_passed_result_rejects_enumeration(
        result,
        altered,
        json_round_trip=True,
    )


def test_preflight_rejects_selection_with_incomplete_authoritative_enumeration():
    graph = _graph(parallel=True)
    selection = _selected(graph)
    object.__setattr__(
        selection,
        "enumeration",
        _enumeration_with(
            _passed_preflight(graph),
            paths=(selection.selected_candidate.path,),
            truncated=False,
        ),
    )

    with pytest.raises(PreflightInputError, match="authoritative topology-derived"):
        validate_preflight(
            selection,
            _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
            _snapshot(graph),
            checked_at=NOW,
            max_snapshot_age=timedelta(minutes=2),
        )


def test_complete_enumeration_passes_and_round_trips():
    result = _passed_preflight(_graph(parallel=True))
    restored = PreflightResult.model_validate_json(result.model_dump_json())

    assert result.enumeration.truncated is False
    assert len(result.enumeration.paths) == 2
    assert restored == result


def test_genuinely_truncated_enumeration_preserves_phase3d_semantics():
    graph = _graph(parallel=True)
    result = _passed_preflight(graph, candidate_limit=1)
    restored = PreflightResult.model_validate_json(result.model_dump_json())

    assert result.enumeration.truncated is True
    assert len(result.enumeration.paths) == 1
    assert restored == result


@pytest.mark.parametrize("json_round_trip", [False, True])
def test_preflight_rejects_enumeration_limit_changed_with_its_contents(
    json_round_trip,
):
    result = _passed_preflight(_graph(parallel=True))
    forged_enumeration = _enumeration_with(
        result,
        candidate_limit=1,
        paths=(result.selected_path,),
        truncated=True,
    )
    payload = result.model_dump(
        mode="json" if json_round_trip else "python"
    )
    payload["enumeration"] = forged_enumeration.model_dump(
        mode="json" if json_round_trip else "python"
    )

    with pytest.raises(
        ValidationError,
        match="candidate limit does not match the originating selection",
    ):
        if json_round_trip:
            PreflightResult.model_validate_json(json.dumps(payload))
        else:
            PreflightResult.model_validate(payload)


def test_preflight_result_binds_candidate_limit_from_selection():
    selection = _selected(_graph(parallel=True))
    result = validate_preflight(
        selection,
        _snapshot(
            selection.originating_plan.request.topology,
            captured_at=NOW - timedelta(minutes=1),
        ),
        _snapshot(selection.originating_plan.request.topology),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.selection_candidate_limit == selection.enumeration.candidate_limit


@pytest.mark.parametrize(
    "field,value",
    [
        ("planned_snapshot_fingerprint", "f" * 64),
        ("fresh_snapshot_fingerprint", "f" * 64),
        ("candidate_id", "unbound-candidate"),
        ("path_fingerprint", "f" * 64),
    ],
)
def test_passed_preflight_rejects_contradictory_ordinary_construction(field, value):
    passed = _passed_preflight()
    payload = passed.model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        PreflightResult(**payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("planned_snapshot_fingerprint", "f" * 64),
        ("fresh_snapshot_fingerprint", "f" * 64),
        ("candidate_id", "unbound-candidate"),
        ("path_fingerprint", "f" * 64),
    ],
)
def test_passed_preflight_rejects_contradictory_json_round_trip(field, value):
    passed = _passed_preflight()
    payload = passed.model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError):
        PreflightResult.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("field", ["candidate_id", "path_fingerprint"])
def test_passed_preflight_requires_candidate_and_path_identity(field):
    passed = _passed_preflight()
    payload = passed.model_dump()
    del payload[field]

    with pytest.raises(ValidationError):
        PreflightResult.model_validate(payload)


def test_valid_passed_preflight_constructs_and_json_round_trips():
    passed = _passed_preflight()

    constructed = PreflightResult(**passed.model_dump())
    restored = PreflightResult.model_validate_json(passed.model_dump_json())

    assert constructed.status == PreflightStatus.PASSED
    assert restored == constructed
    assert restored.path_fingerprint == passed.path_fingerprint


@pytest.mark.parametrize(
    ("changed_snapshot", "expected_status"),
    [
        (lambda graph: _snapshot(graph, status=SnapshotStatus.INCOMPLETE),
         PreflightStatus.UNKNOWN),
        (lambda graph: _snapshot(graph, connected=(1,)),
         PreflightStatus.FAILED),
    ],
)
def test_failure_preflight_results_remain_constructible(changed_snapshot, expected_status):
    graph = _graph()
    selection = _selected(graph)
    result = validate_preflight(
        selection,
        _snapshot(graph, captured_at=NOW - timedelta(minutes=1)),
        changed_snapshot(graph),
        checked_at=NOW,
        max_snapshot_age=timedelta(minutes=2),
    )

    assert result.status == expected_status
    assert PreflightResult.model_validate_json(result.model_dump_json()) == result


def test_candidate_identity_helper_uses_originating_request_and_exact_path():
    graph = _graph()
    selection = _selected(graph)
    candidate = selection.selected_candidate

    assert candidate.candidate_id == physical_candidate_id(
        selection.originating_plan,
        candidate.path,
    )
