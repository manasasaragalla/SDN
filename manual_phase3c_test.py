
from datetime import datetime, timedelta, timezone

from backend.models.network import Host, TopologyGraph, Link
from backend.models.canonical_intent import (
    CanonicalIntent,
    MetricConstraint,
    TrafficScope,
)
from backend.capabilities import resolve_capabilities

from backend.planner.models import (
    Plan,
    PlanningRequest,
    PlanningReadiness,
    HardConstraintRequirement,
    RequiredMetricObservation,
    MetricObservationPurpose,
    CandidateFeasibility,
)

from backend.planner.path_enumeration import enumerate_candidate_paths

from backend.planner.constraint_evaluation import (
    EvaluationCandidate,
    EvaluationTarget,
    MetricObservation,
    ObservationStatus,
    FreshnessPolicy,
    MetricFreshnessLimit,
    planning_request_fingerprint,
    physical_path_fingerprint,
    evaluate_hard_constraints,
)


# ============================================================
# 1. TOPOLOGY: TWO ALTERNATIVE PATHS
# ============================================================

graph = TopologyGraph(
    switches={
        "s1": 4,
        "s2": 4,
        "s3": 4,
        "s4": 4,
    },
    hosts={
        "h1": Host(
            name="h1",
            ip="10.0.0.1",
            mac="00:00:00:00:00:01",
            switch="s1",
            switch_port=1,
        ),
        "h4": Host(
            name="h4",
            ip="10.0.0.4",
            mac="00:00:00:00:00:04",
            switch="s2",
            switch_port=4,
        ),
    },
    links=[
        Link(node_a="s1", port_a=2, node_b="s2", port_b=1),
        Link(node_a="s1", port_a=3, node_b="s3", port_b=1),
        Link(node_a="s3", port_a=2, node_b="s4", port_b=1),
        Link(node_a="s4", port_a=2, node_b="s2", port_b=3),
    ],
)


# ============================================================
# 2. INTENT: TWO HARD CONSTRAINTS
# ============================================================

intent = CanonicalIntent(
    scope=TrafficScope(
        source="h1",
        destination="h4",
    ),
    constraints=[
        MetricConstraint(
            metric="latency",
            comparison="LTE",
            value=50,
            unit="ms",
        ),
        MetricConstraint(
            metric="bandwidth",
            comparison="GTE",
            value=20,
            unit="Mbps",
        ),
    ],
)


# ============================================================
# 3. CAPABILITY RESOLUTION
# ============================================================

capabilities = resolve_capabilities(intent, graph)

print("\n========== CAPABILITY DIAGNOSTICS ==========")
print("Overall eligibility:", capabilities.eligibility.value)

for item in capabilities.constraints:
    print(f"\nMetric: {item.metric}")
    print("Requirement:", item.requirement_id)
    print("Validated:", item.validated.status.value)
    print("Measurable:", item.measurable.status.value)
    print("Plannable:", item.plannable.status.value)
    print("Executable:", item.executable.status.value)

print("\nOverall reasons:")
for reason in capabilities.reasons:
    print("-", reason)


# ============================================================
# 4. PLANNING REQUEST AND PLAN
# ============================================================

request = PlanningRequest(
    intent=intent,
    topology=graph,
    capabilities=capabilities,
)

request_fp = planning_request_fingerprint(request)

plan = Plan(
    request=request,
    capability_readiness=capabilities.eligibility,
    planning_readiness=PlanningReadiness.CONDITIONAL,
    hard_constraints=tuple(
        HardConstraintRequirement(
            requirement_id=f"constraint:{i}:{constraint.metric}",
            constraint=constraint,
        )
        for i, constraint in enumerate(intent.constraints)
    ),
    required_observations=tuple(
        RequiredMetricObservation(
            observation_id=f"observation:{i}",
            requirement_id=f"constraint:{i}:{constraint.metric}",
            purpose=MetricObservationPurpose.HARD_CONSTRAINT,
            metric=constraint.metric,
            unit=constraint.unit,
        )
        for i, constraint in enumerate(intent.constraints)
    ),
)


# ============================================================
# 5. ENUMERATE PHYSICAL PATHS
# ============================================================

paths = enumerate_candidate_paths(
    graph,
    "h1",
    "h4",
    candidate_limit=10,
)

print("\n========== PATH ENUMERATION ==========")
print("Paths found:", len(paths.paths))
print("Truncated:", paths.truncated)

for i, path in enumerate(paths.paths, 1):
    print(f"Path {i}:", " -> ".join(path.nodes))

assert len(paths.paths) >= 2, "Expected two alternative paths"

candidate_specs = [
    ("candidate-A", paths.paths[0]),
    ("candidate-B", paths.paths[1]),
]

candidates = [
    EvaluationCandidate(
        candidate_id=candidate_id,
        request_fingerprint=request_fp,
        path=path,
        feasibility=CandidateFeasibility.CANDIDATE,
    )
    for candidate_id, path in candidate_specs
]

for candidate_id, path in candidate_specs:
    print(
        candidate_id,
        "| fingerprint:",
        physical_path_fingerprint(path)[:16],
    )


# ============================================================
# 6. FRESHNESS POLICY AND OBSERVATION HELPER
# ============================================================

now = datetime.now(timezone.utc)

freshness = FreshnessPolicy(
    limits=(
        MetricFreshnessLimit(
            metric="latency",
            max_age=timedelta(minutes=1),
        ),
        MetricFreshnessLimit(
            metric="bandwidth",
            max_age=timedelta(minutes=1),
        ),
    )
)


def observation(
    candidate_id,
    path,
    metric,
    unit,
    requirement_id,
    value=None,
    status=ObservationStatus.VALID,
    collected_at=None,
):
    target = EvaluationTarget(
        candidate_id=candidate_id,
        request_fingerprint=request_fp,
        path_fingerprint=physical_path_fingerprint(path),
        requirement_id=requirement_id,
    )

    return MetricObservation(
        target=target,
        metric=metric,
        unit=unit,
        value=value,
        status=status,
        collected_at=collected_at or now,
        source="manual-test",
    )


def evaluate_and_print(name, selected_candidates, observations):
    print(f"\n========== {name} ==========")

    result = evaluate_hard_constraints(
        plan,
        selected_candidates,
        observations,
        evaluated_at=now,
        freshness_policy=freshness,
    )

    for candidate in result.candidates:
        print(
            f"\n{candidate.candidate_id}: {candidate.status.value}"
        )

        for requirement in candidate.requirements:
            print(
                requirement.target.requirement_id,
                "=>",
                requirement.status.value,
                "|",
                requirement.reason,
            )

    print("\nOVERALL PLAN:", result.status.value)

    return result


# ============================================================
# 7. SINGLE-CANDIDATE EVALUATION TESTS
# ============================================================

candidate_a = candidates[0]
path_a = paths.paths[0]


# Scenario A: Both constraints satisfied
result_a = evaluate_and_print(
    "TEST A: BOTH CONSTRAINTS SATISFIED",
    [candidate_a],
    [
        observation(
            "candidate-A", path_a,
            "latency", "ms", "constraint:0:latency", 30
        ),
        observation(
            "candidate-A", path_a,
            "bandwidth", "Mbps", "constraint:1:bandwidth", 30
        ),
    ],
)

assert result_a.status.value == "SATISFIED"


# Scenario B: Latency violated
result_b = evaluate_and_print(
    "TEST B: LATENCY VIOLATED",
    [candidate_a],
    [
        observation(
            "candidate-A", path_a,
            "latency", "ms", "constraint:0:latency", 60
        ),
        observation(
            "candidate-A", path_a,
            "bandwidth", "Mbps", "constraint:1:bandwidth", 30
        ),
    ],
)

assert result_b.status.value == "VIOLATED"


# Scenario C: Bandwidth observation missing
result_c = evaluate_and_print(
    "TEST C: BANDWIDTH MISSING",
    [candidate_a],
    [
        observation(
            "candidate-A", path_a,
            "latency", "ms", "constraint:0:latency", 30
        ),
    ],
)

assert result_c.status.value == "UNKNOWN"


# Scenario D: Bandwidth measurement failed
result_d = evaluate_and_print(
    "TEST D: BANDWIDTH MEASUREMENT FAILED",
    [candidate_a],
    [
        observation(
            "candidate-A", path_a,
            "latency", "ms", "constraint:0:latency", 30
        ),
        observation(
            "candidate-A", path_a,
            "bandwidth", "Mbps", "constraint:1:bandwidth",
            value=None,
            status=ObservationStatus.FAILED,
        ),
    ],
)

assert result_d.status.value == "UNKNOWN"


# Scenario E: Violation takes precedence over UNKNOWN
result_e = evaluate_and_print(
    "TEST E: VIOLATION + UNKNOWN",
    [candidate_a],
    [
        observation(
            "candidate-A", path_a,
            "latency", "ms", "constraint:0:latency", 80
        ),
    ],
)

assert result_e.status.value == "VIOLATED"


# ============================================================
# 8. MULTI-CANDIDATE EVALUATION
# ============================================================

observations_multi = [
    # Candidate A: latency violated, bandwidth satisfied
    observation(
        "candidate-A", paths.paths[0],
        "latency", "ms", "constraint:0:latency", 60
    ),
    observation(
        "candidate-A", paths.paths[0],
        "bandwidth", "Mbps", "constraint:1:bandwidth", 30
    ),

    # Candidate B: both constraints satisfied
    observation(
        "candidate-B", paths.paths[1],
        "latency", "ms", "constraint:0:latency", 30
    ),
    observation(
        "candidate-B", paths.paths[1],
        "bandwidth", "Mbps", "constraint:1:bandwidth", 30
    ),
]

result_multi = evaluate_and_print(
    "TEST F: MULTIPLE CANDIDATES",
    candidates,
    observations_multi,
)

assert result_multi.status.value == "SATISFIED"

statuses = {
    item.candidate_id: item.status.value
    for item in result_multi.candidates
}

assert statuses["candidate-A"] == "VIOLATED"
assert statuses["candidate-B"] == "SATISFIED"


# ============================================================
# 9. FINAL SUMMARY
# ============================================================

print("\n==========================================")
print("MANUAL PHASE 3C TEST SUMMARY")
print("==========================================")

tests = {
    "A - Both constraints satisfied": result_a.status.value == "SATISFIED",
    "B - Constraint violation": result_b.status.value == "VIOLATED",
    "C - Missing observation": result_c.status.value == "UNKNOWN",
    "D - Failed measurement": result_d.status.value == "UNKNOWN",
    "E - Violation + UNKNOWN": result_e.status.value == "VIOLATED",
    "F - Multiple candidates": (
        result_multi.status.value == "SATISFIED"
        and statuses["candidate-A"] == "VIOLATED"
        and statuses["candidate-B"] == "SATISFIED"
    ),
}

for name, passed in tests.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")

print(f"\nTotal: {sum(tests.values())}/{len(tests)} passed")


# ============================================================
# 10. OBSERVATION INTEGRITY TESTS
# ============================================================

print("\n==========================================")
print("TEST 7: OBSERVATION INTEGRITY")
print("==========================================")

candidate_a = candidates[0]
candidate_b = candidates[1]

path_a = paths.paths[0]
path_b = paths.paths[1]


def check_requirement(result, requirement_id):
    for candidate in result.candidates:
        for requirement in candidate.requirements:
            if requirement.target.requirement_id == requirement_id:
                return requirement.status.value
    return "NOT_FOUND"


def run_integrity_test(name, selected_candidates, observations):
    print(f"\n--- {name} ---")

    result = evaluate_hard_constraints(
        plan,
        selected_candidates,
        observations,
        evaluated_at=now,
        freshness_policy=freshness,
    )

    for candidate in result.candidates:
        print("Candidate:", candidate.candidate_id)
        for requirement in candidate.requirements:
            print(
                requirement.target.requirement_id,
                "=>",
                requirement.status.value,
                "|",
                requirement.reason,
            )

    print("Plan:", result.status.value)
    return result


integrity_results = {}


# Test 7A: Stale observation
stale_obs = observation(
    "candidate-A",
    path_a,
    "latency",
    "ms",
    "constraint:0:latency",
    30,
    collected_at=now - timedelta(minutes=2),
)

result = run_integrity_test(
    "7A: STALE OBSERVATION",
    [candidate_a],
    [stale_obs],
)

integrity_results["stale"] = (
    check_requirement(result, "constraint:0:latency") == "UNKNOWN"
)


# Test 7B: Future observation
future_obs = observation(
    "candidate-A",
    path_a,
    "latency",
    "ms",
    "constraint:0:latency",
    30,
    collected_at=now + timedelta(minutes=1),
)

result = run_integrity_test(
    "7B: FUTURE OBSERVATION",
    [candidate_a],
    [future_obs],
)

integrity_results["future"] = (
    check_requirement(result, "constraint:0:latency") == "UNKNOWN"
)


# Test 7C: Duplicate observations for the same target
duplicate_obs = observation(
    "candidate-A",
    path_a,
    "latency",
    "ms",
    "constraint:0:latency",
    30,
)

result = run_integrity_test(
    "7C: DUPLICATE OBSERVATIONS",
    [candidate_a],
    [duplicate_obs, duplicate_obs],
)

integrity_results["duplicate"] = (
    check_requirement(result, "constraint:0:latency") == "UNKNOWN"
)


# Helper for constructing observations with deliberately incorrect identity.
def custom_observation(
    candidate_id,
    request_fingerprint,
    path_fingerprint,
    metric="latency",
    unit="ms",
    value=30,
):
    target = EvaluationTarget(
        candidate_id=candidate_id,
        request_fingerprint=request_fingerprint,
        path_fingerprint=path_fingerprint,
        requirement_id="constraint:0:latency",
    )

    return MetricObservation(
        target=target,
        metric=metric,
        unit=unit,
        value=value,
        status=ObservationStatus.VALID,
        collected_at=now,
        source="manual-integrity-test",
    )


def expect_rejection(name, selected_candidates, observations):
    print(f"\n--- {name} ---")

    try:
        result = evaluate_hard_constraints(
            plan,
            selected_candidates,
            observations,
            evaluated_at=now,
            freshness_policy=freshness,
        )
        print("UNEXPECTED ACCEPTANCE:", result.status.value)
        return False

    except Exception as exc:
        print("Correctly rejected:", type(exc).__name__)
        print("Reason:", str(exc).splitlines()[0])
        return True


# Test 7D: Wrong request fingerprint
wrong_request_obs = custom_observation(
    "candidate-A",
    "f" * 64,
    physical_path_fingerprint(path_a),
)

integrity_results["wrong_request"] = expect_rejection(
    "7D: WRONG REQUEST FINGERPRINT",
    [candidate_a],
    [wrong_request_obs],
)


# Test 7E: Wrong physical path fingerprint
wrong_path_obs = custom_observation(
    "candidate-A",
    request_fp,
    "e" * 64,
)

integrity_results["wrong_path"] = expect_rejection(
    "7E: WRONG PATH FINGERPRINT",
    [candidate_a],
    [wrong_path_obs],
)


# Test 7F: Reuse Candidate A's observation for Candidate B
candidate_a_obs = observation(
    "candidate-A",
    path_a,
    "latency",
    "ms",
    "constraint:0:latency",
    30,
)

integrity_results["cross_candidate"] = expect_rejection(
    "7F: CROSS-CANDIDATE OBSERVATION REUSE",
    [candidate_b],
    [candidate_a_obs],
)


# ============================================================
# TEST 7 SUMMARY
# ============================================================

print("\n==========================================")
print("OBSERVATION INTEGRITY SUMMARY")
print("==========================================")

for name, passed in integrity_results.items():
    print(f"{'PASS' if passed else 'FAIL'}: {name}")

print(
    f"\nTotal: {sum(integrity_results.values())}"
    f"/{len(integrity_results)} passed"
)

assert all(integrity_results.values()), (
    "One or more observation integrity checks failed."
)
