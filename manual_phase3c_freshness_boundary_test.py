
from datetime import timedelta

from manual_phase3c_test import (
    candidates,
    freshness,
    now,
    observation,
    paths,
    plan,
)

from backend.planner.constraint_evaluation import (
    evaluate_hard_constraints,
    EvaluationStatus,
)


def get_latency_status(result, candidate_id):
    candidate_result = next(
        item for item in result.candidates
        if item.candidate_id == candidate_id
    )

    requirement_result = next(
        item for item in candidate_result.requirements
        if item.target.requirement_id == "constraint:0:latency"
    )

    return requirement_result.status


def run_test(name, collected_at, expected):
    obs = observation(
        "candidate-A",
        paths.paths[0],
        "latency",
        "ms",
        "constraint:0:latency",
        value=30,
        collected_at=collected_at,
    )

    result = evaluate_hard_constraints(
        plan,
        [candidates[0]],
        [obs],
        evaluated_at=now,
        freshness_policy=freshness,
    )

    actual = get_latency_status(result, "candidate-A")
    passed = actual == expected

    print(
        f"{'PASS' if passed else 'FAIL'}: {name}\n"
        f"  Expected: {expected.value}\n"
        f"  Actual:   {actual.value}\n"
    )

    return passed


# Retrieve the configured latency freshness limit.
latency_limit = next(
    item.max_age
    for item in freshness.limits
    if item.metric == "latency"
)

print("\n========== TEST 9: FRESHNESS BOUNDARIES ==========\n")

results = []

# Test 9A: Exactly at the maximum permitted age.
results.append(
    run_test(
        "Observation exactly at maximum age",
        now - latency_limit,
        EvaluationStatus.SATISFIED,
    )
)

# Test 9B: Just one microsecond older than the maximum age.
results.append(
    run_test(
        "Observation one microsecond older than maximum age",
        now - latency_limit - timedelta(microseconds=1),
        EvaluationStatus.UNKNOWN,
    )
)

print("==========================================")
print("FRESHNESS BOUNDARY SUMMARY")
print("==========================================")
print(f"Passed: {sum(results)}/{len(results)}")
print(f"Failed: {len(results) - sum(results)}/{len(results)}")

if not all(results):
    raise SystemExit(1)
