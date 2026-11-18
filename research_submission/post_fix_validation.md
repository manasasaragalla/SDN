# IntentFlow Post-Fix Validation

**Validation date:** 2026-11-18

**Scope:** WSL Ubuntu, complete backend suite, focused planner suite, Python compile checks, Git diff/status, and valid-topology behavior.

**No source code or experimental data was changed during this validation.** The only file created as part of this validation is this report.

## Environment

WSL Ubuntu reported:

```text
Linux SasiRekhas 6.18.58.1-microsoft-standard-WSL2
Python 3.12.3
pytest 9.1.1
```

Repository path inside WSL:

```text
/mnt/e/SdnProject
```

## Exact commands executed

### Environment verification

```bash
wsl.exe -e bash -lc 'cd /mnt/e/SdnProject && uname -a && python3 --version && pytest --version'
```

### Complete backend suite

```bash
wsl.exe -e bash -lc 'cd /mnt/e/SdnProject && pytest -q'
```

### Focused planner suite

```bash
wsl.exe -e bash -lc 'cd /mnt/e/SdnProject && pytest -q tests/test_topology_planning_metrics.py tests/test_candidate_selection.py tests/test_constraint_evaluation.py tests/test_path_enumeration.py tests/test_planner_contract.py'
```

### Python compile checks

```bash
wsl.exe -e bash -lc 'cd /mnt/e/SdnProject && python3 -m py_compile backend/planner/topology_planning.py tests/test_topology_planning_metrics.py'
```

### Git diff/status checks

```powershell
git --no-pager status --porcelain=v1 --untracked-files=all
git --no-pager diff --stat
git --no-pager diff --check
git --no-pager diff --no-ext-diff -- backend/planner/topology_planning.py
git --no-pager diff --no-index -- /dev/null tests/test_topology_planning_metrics.py
git --no-pager diff --no-index -- /dev/null research_submission/planner_correctness_review.md
```

## Complete backend test result

Command:

```bash
pytest -q
```

Actual result:

```text
833 passed
10 failed
68.66 seconds
```

All 10 failures are in `tests/test_topology_catalog.py`.

### Failure list

1. `test_active_design_topology_drives_candidate_planning[...]` - bandwidth case
2. `test_active_design_topology_drives_candidate_planning[...]` - latency case
3. `test_active_design_topology_drives_candidate_planning[...]` - combined case
4. `test_design_plan_reports_no_eligible_candidate_as_ineligible`
5. `test_two_hundred_mbps_minimum_is_rejected_by_existing_design_topology`
6. `test_combined_design_preview_json_keeps_planning_and_execution_independent`
7. `test_equal_configured_objective_values_explain_deterministic_tie`
8. `test_arbitrary_active_topology_supports_path_ranking_and_constraints`
9. `test_active_design_planning_evaluates_multiple_hard_constraints`
10. `test_missing_link_capacity_is_unknown_not_a_passing_bandwidth_constraint`

## Exact failure causes

The existing `_diamond_topology()` fixture and several arbitrary topology fixtures leave host attachment fields at their model default of `None`. Before the fix, missing attachment fields were omitted and link-only metrics remained numeric.

The post-fix implementation now correctly treats missing host attachment fields as missing required metric values and returns `None` for the complete-path aggregate.

The 10 failures therefore demonstrate an existing-valid-fixture compatibility issue in the post-fix implementation:

- bandwidth previews become `INSUFFICIENT_CONFIGURED_DATA`;
- latency previews become `INSUFFICIENT_CONFIGURED_DATA`;
- `planning_eligible` becomes `None` instead of `True`;
- expected direct/alternate candidate statuses become `UNKNOWN`;
- expected objective-selected candidates are absent;
- the missing-link test's alternate candidate is now `UNKNOWN` instead of `ELIGIBLE`.

The failures are not unrelated API/auth failures. They are direct consequences of the post-fix `_path_facts()` policy applied to topologies that have complete switch-link metrics but missing host attachment metrics.

## Focused planner test result

Command:

```bash
pytest -q tests/test_topology_planning_metrics.py tests/test_candidate_selection.py tests/test_constraint_evaluation.py tests/test_path_enumeration.py tests/test_planner_contract.py
```

Actual result:

```text
266 passed
22.11 seconds
0 failed
```

The focused suite passed, but it did not replace or override the complete-suite failures.

## Python compile-check result

Command:

```bash
python3 -m py_compile backend/planner/topology_planning.py tests/test_topology_planning_metrics.py
```

Actual result: exit status 0. No syntax or compile errors.

## Git diff inspection

Tracked source diff:

```diff
backend/planner/topology_planning.py
```

The source diff changes `_path_facts()` metric assembly and adds finite/range validation helpers.

It does not change:

- candidate enumeration;
- `Comparison` operators;
- objective sorting;
- candidate-fingerprint tie-breaking;
- candidate-limit/truncation handling.

New untracked test diff:

```text
tests/test_topology_planning_metrics.py
```

New untracked report files:

```text
research_submission/planner_correctness_review.md
research_submission/post_fix_validation.md
```

Other existing audit reports remain under `research_submission/`:

```text
audit_report.md
experiment_inventory.md
paper_outline.md
reproducibility_inventory.md
```

`git diff --check` produced no whitespace errors.

## Repository status

Current status:

```text
 M backend/planner/topology_planning.py
?? research_submission/audit_report.md
?? research_submission/experiment_inventory.md
?? research_submission/paper_outline.md
?? research_submission/planner_correctness_review.md
?? research_submission/post_fix_validation.md
?? research_submission/reproducibility_inventory.md
?? tests/test_topology_planning_metrics.py
```

No experimental CSV, JSON, screenshot, or result file was modified.

No tracked generated files appeared. Python cache and pytest cache entries remain ignored by Git.

## Valid-topology planner verification

Valid complete topologies that provide every switch link and both endpoint attachment metric values preserve the mathematical operations:

- bandwidth: bottleneck minimum;
- delay: sum;
- packet loss: survival product.

However, the complete suite did **not** verify unchanged behavior for valid topologies that omit host attachment fields. It found 10 regressions in such existing fixtures and API expectations.

Therefore:

- ranking code was not changed;
- aggregate equation code was changed in order to fail closed;
- existing planner outputs are not fully unchanged for topologies with missing attachment fields;
- existing valid-topology API tests fail as a direct compatibility consequence.

## Remaining risks

1. The post-fix implementation is not complete-suite compatible.
2. The semantics for missing host attachment metrics require a repository-wide decision:
   - missing attachment metric means unknown; or
   - attachments are optional and link-only metrics remain valid unless an attachment explicitly declares a value.
3. The current fix can turn existing valid DESIGN fixtures with no attachment metrics into unknown candidates.
4. Complete suite must be green before the planner is frozen.
5. No live-network or experimental-result claim is made by this validation.

## Planner freeze recommendation

**Not ready to freeze for the research paper.**

The 266 focused planner tests pass and both modified Python files compile. The complete Ubuntu suite is not green: `833 passed, 10 failed`, all 10 in topology-catalog API planning behavior. The failures show that existing valid topologies with omitted attachment fields no longer preserve prior planner output.

No automatic fix was applied during this validation.
