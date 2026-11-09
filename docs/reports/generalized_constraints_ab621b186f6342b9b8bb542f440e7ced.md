# Generalized routing execution ab621b186f6342b9b8bb542f440e7ced

- **Status:** `FAILED`
- **Started:** 2026-11-05T13:06:23.111397+00:00
- **Completed:** 2026-11-05T13:06:23.142061+00:00
- **Duration:** 0.031s
- **Topology fingerprint:** `5e19496272fa82bd6cb1671f41804fcfb6d22b887326e0b1078c38f98413a900`
- **Objective:** none
- **Hard constraints:** latency LTE, bandwidth GTE

## Candidate measurements

| Candidate | Path | RTT (ms) | Packets received/sent | Valid | Eligible | Selected | Probe cookie | Cleanup |
|---|---|---:|---:|---|---|---|---:|---|
| `physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736` | `h1 → s1 → s2 → s4 → h4` | not recorded | not recorded | None | not recorded | False | None | NOT_REACHED |
| `physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed` | `h1 → s1 → s3 → s5 → s4 → h4` | not recorded | not recorded | None | not recorded | False | None | NOT_REACHED |

## Candidate evidence

### physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736

- **Path:** `h1 → s1 → s2 → s4 → h4`
- **Path fingerprint:** `673d7a7e5ee66bef0c6c554fee0d56968cb6448c7d6394e08440cc4a7986b869`
- **Measurement run ID:** `not created`
- **Probe operation ID:** `not created`
- **Preflight:** `FAILED`
- **Deployment:** `NOT_REACHED`; cookie `None`; DPIDs `None`; readback None/None
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `NOT_REACHED`; remaining flows `None`
- **Probe snapshot:** `COMPLETE` at 2026-11-05T13:06:23.134327+00:00; connected DPIDs `[1, 2, 3, 4, 5]`; operational data ports 14/14
- **Failure reason:** Candidate probe failed: Probe candidate is not known-feasible: PROVEN_INFEASIBLE
- **Stage timestamps:** candidate_discovered_at=2026-11-05T13:06:23.121936+00:00; preflight_started_at=2026-11-05T13:06:23.121952+00:00; probe_completed_at=2026-11-05T13:06:23.142000+00:00

### physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed

- **Path:** `h1 → s1 → s3 → s5 → s4 → h4`
- **Path fingerprint:** `not recorded`
- **Measurement run ID:** `not created`
- **Probe operation ID:** `not created`
- **Preflight:** `NOT_REACHED`
- **Deployment:** `NOT_REACHED`; cookie `None`; DPIDs `None`; readback None/None
- **Observation:** `NOT_CREATED` (not created)
- **Cleanup:** `NOT_REACHED`; remaining flows `None`
- **Failure reason:** Candidate probe failed: Probe candidate is not known-feasible: PROVEN_INFEASIBLE

## Selection and final execution

- **Selection status:** `NOT_REACHED`
- **Selected candidate:** `none`
- **Selected path:** `not selected`
- **Selection method:** `not reached`

| Candidate | constraints value (metric unit) | Feasibility | Eligible |
|---|---:|---|---|
| `physical-bb31d129e051329210a7bfd23e835ee5277ef3fe1c1f142b4cf037ea16268736` | not recorded | not recorded | not recorded |
| `physical-3ab5beb186596e2c659f010ebf40cff47a9e05c1908ff8114fc5dcca98ae27ed` | not recorded | not recorded | not recorded |

Selection reasoning:
- Candidate probe failed: Probe candidate is not known-feasible: PROVEN_INFEASIBLE
- **Final preflight:** `NOT_REACHED`
- **Final topology fingerprints:** planned `not recorded`, fresh `not recorded`
- **Connected DPIDs:** `not recorded`
- **Operational data ports:** not recorded
- **Final deployment operation ID:** `not created`
- **Final selected path:** `not selected`
- **Final deployment:** `NOT_REACHED` (cookie `None`, DPIDs `None`)
- **Verified rules:** None / None (executor reported exact readback status)
- **Connectivity:** `NOT_REACHED`
- **Final packets:** not recorded/not recorded received; loss not recorded%
- **Final RTT:** not recorded ms

## Failure or limitation

Candidate probe failed: Probe candidate is not known-feasible: PROVEN_INFEASIBLE

## Evidence availability

The JSON companion contains stage outcomes, exact physical connections, deployment results, packet evidence, and explicit not-reached markers. Fields marked `NOT_REACHED` or `NOT_RECORDED` are not treated as success.
