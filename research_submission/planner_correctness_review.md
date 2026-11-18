# IntentFlow Planner Metric Correctness Review

**Review scope:** `backend/planner/topology_planning.py`, related host/link metric models, planner path enumeration, candidate ranking, and constraint evaluation tests.

**Audit status:** A correctness issue was confirmed and corrected.

## Executive result

The deterministic planner could calculate a bandwidth, delay, or packet-loss aggregate as complete when a host-switch attachment metric was missing or invalid. The missing attachment value was silently omitted.

This could mark a hard constraint as satisfied and an incomplete candidate as eligible. The defect has now been corrected in `_path_facts()` by making each metric fail closed unless every relevant switch link and both path endpoint attachments have a complete, finite, and valid value.

No path-ranking algorithm or objective tie-breaking rule was changed.

## 1. Complete physical-path calculation

For an enumerated path, `backend/planner/topology_planning.py` obtains:

- all switch-to-switch `Link` records;
- the source host attachment;
- the destination host attachment.

The implemented mathematical aggregates are:

### Bandwidth

\[
B(p)=\min_{e\in p} b_e
\]

The implementation takes:

- every switch-link `bw_mbps`;
- source and destination `attachment_capacity_mbps`;
- the minimum of all values.

### Delay

\[
D(p)=\sum_{e\in p} d_e
\]

The implementation adds:

- every switch-link `delay_ms`;
- source `attachment_delay_ms`;
- destination `attachment_delay_ms`.

### Packet loss

\[
L(p)=100\left(1-\prod_e(1-l_e/100)\right)
\]

The implementation applies this survival-product formula across:

- every switch-link `packet_loss_percent`;
- source `attachment_packet_loss_percent`;
- destination `attachment_packet_loss_percent`.

## 2. Confirmed attachment defect

Before the correction, `_path_facts()` used separate behavior for each metric:

### Bandwidth

```python
link_capacities = [
    link.bw_mbps for link in path_links if link.bw_mbps is not None
] + [
    host.attachment_capacity_mbps
    for host in path_hosts
    if host.attachment_capacity_mbps is not None
]

capacity = (
    min(link_capacities)
    if link_capacities and all(link.bw_mbps is not None for link in path_links)
    else None
)
```

A missing host attachment capacity was removed by the `is not None` filter. Complete switch-link capacities could then make the candidate look complete, even though one endpoint did not have a known attachment capacity.

### Delay

Missing endpoint attachment delay was removed by the `is not None` filter before the sum.

Example:

- switch-link delays: 2 ms;
- source attachment: 1 ms;
- destination attachment: missing.

The old implementation returned `3 ms` rather than `UNKNOWN`.

### Packet loss

Missing endpoint attachment loss was removed by the `is not None` filter before the survival-product calculation.

The old implementation therefore excluded an incomplete attachment from the loss aggregate.

## 3. Consequence for candidate eligibility

If a hard constraint was evaluated against the falsely numeric aggregate:

- an insufficient bandwidth candidate could become `SATISFIED`;
- an excessive delay candidate could become `SATISFIED`;
- an excessive loss candidate could become `SATISFIED`;
- the candidate could enter the eligible set;
- objective ranking could proceed on incomplete data;
- a candidate could be selected as `SELECTED`.

This was possible specifically for missing or invalid attachment metrics. It did not require an invalid switch-link path.

The audit result is now:

- missing required metric: `UNKNOWN`;
- candidate status: `UNKNOWN`;
- constraint status: `UNKNOWN`;
- no candidate is selected.

## 4. Invalid and non-finite values

The existing DESIGN topology validator rejects invalid host and link values when a topology is loaded through `TopologyDefinitionInput`.

Relevant existing checks include:

- capacity greater than zero;
- delay at least zero;
- packet loss in `[0, 100]`;
- finite values.

However, `TopologyGraph` and `_path_facts()` are also usable as direct, in-memory models. The old planner did not independently validate `_path_facts()` inputs and could include:

- negative capacity;
- negative delay;
- packet loss below zero or above 100;
- positive or negative infinity;
- NaN.

The correction now independently checks all switch-link and endpoint attachment values before aggregate calculation.

Invalid values include:

- capacity: missing, non-numeric, boolean, non-finite, zero, or negative;
- delay: missing, non-numeric, boolean, non-finite, or negative;
- packet loss: missing, non-numeric, boolean, non-finite, or outside `[0, 100]`.

## 5. Smallest safe correction

The smallest correction was made inside `_path_facts()`:

1. retain a switch-link completeness flag;
2. include host attachment values explicitly rather than filtering missing values;
3. validate every capacity, delay, and loss value;
4. return `None` for an aggregate if any required value is missing or invalid;
5. preserve the existing minimum/sum/survival-product equations;
6. leave candidate enumeration, constraint operators, objective ranking, and fingerprint tie-breaking unchanged.

No topology model or ranking API was modified.

## 6. Existing behavior for complete valid topologies

Complete valid topologies preserve the old equations:

- bandwidth remains the path bottleneck minimum;
- delay remains the sum of link and attachment delays;
- loss remains the independent-loss survival product;
- valid complete single-switch paths preserve same-switch host attachment aggregation.

## 7. Regression tests

A focused test module was added:

- `tests/test_topology_planning_metrics.py`

Coverage includes:

- missing source/destination bandwidth;
- missing source/destination delay;
- missing source/destination packet loss;
- complete attachment aggregation;
- invalid negative, zero, infinite, and NaN attachment metrics;
- invalid switch-link capacity, delay, and packet loss.

The tests verify that missing or invalid values produce `None` aggregates and cannot produce a selected eligible candidate.

## 8. Test commands and outcomes

### Regression test before correction

```powershell
pytest -q tests/test_topology_planning_metrics.py
```

Actual result: failed. The attachment and invalid-value cases demonstrated that incomplete aggregates were still numeric.

### Focused planner suite after correction

```powershell
pytest -q tests/test_topology_planning_metrics.py tests/test_candidate_selection.py tests/test_constraint_evaluation.py tests/test_path_enumeration.py tests/test_planner_contract.py
```

Actual result: `266 passed in 18.99s`.

### Pylance diagnostics

- `backend/planner/topology_planning.py`: one existing Pylance informational diagnostic for an unused `physical_path_capacity_mbps` import.
- `tests/test_topology_planning_metrics.py`: no diagnostics.

Pylance did not report syntax or type errors in the new test module.

## 9. Proposed-audit formulation comparison

The corrected implementation now matches the fail-closed interpretation of the proposed complete-path formulation:

- bandwidth: complete minimum;
- delay: complete sum;
- packet loss: complete independent-link survival product;
- missing or invalid values: unknown.

The implementation is still bounded by the configured candidate limit and does not claim global optimality.

## Files changed

- `backend/planner/topology_planning.py`
- `tests/test_topology_planning_metrics.py`
- `research_submission/planner_correctness_review.md`
