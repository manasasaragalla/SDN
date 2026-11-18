# Host Attachment Metric Semantics Review

**Scope:** model defaults, topology validation, frontend generation/editor behavior, saved or constructed topology fixtures, and the 10 post-fix WSL failures.

**No production code, tests, or experimental data are changed by this report.**

## 1. Executive conclusion

The 10 failures are primarily outdated or incomplete test fixtures, not evidence that the planner fix is wrong.

The fixtures represent complete planning topologies: their switch links contain bandwidth, delay, and/or loss values and their tests assert selected paths and hard-constraint results. They leave host attachment metrics at the model default of `None`, although the expected path results treat the topology as having enough information for end-to-end planning.

The recommended decision is:

1. **Keep the fail-closed implementation.**
2. **Update complete planning fixtures** in `tests/test_topology_catalog.py` to give h1/h4 or client/server attachments valid zero or sufficiently high metrics.
3. **Do not weaken `_path_facts()`** to treat missing endpoint facts as zero or to ignore them.
4. **Add or define a separate switch-core metric path** if IntentFlow wants switch-link-only planning for LIVE or manually incomplete topologies.

The fix is consistent with end-to-end path metrics. It exposes, rather than creates, an incomplete-metric representation issue in existing fixtures and in live Mininet discovery.

## 2. Host and Link model semantics

`backend/models/network.py` defines:

- `attachment_capacity_mbps: Optional[float] = None`
- `attachment_delay_ms: Optional[float] = None`
- `attachment_packet_loss_percent: Optional[float] = None`
- `attachment_admin_up: bool | None = None`

The host attachment values are therefore optional facts. The default `None` is a valid in-memory representation of unknown or unavailable information.

The corresponding switch-link fields are also optional:

- `bw_mbps`
- `delay_ms`
- `packet_loss_percent`
- `admin_up`

Thus the core topology model deliberately supports incomplete facts. `None` means unknown/unconfigured, not automatically zero.

## 3. TopologyDefinition validation semantics

`backend/models/topology_definition.py` `_validate_design_graph()` rejects invalid non-`None` values:

- host attachment capacity must be finite and greater than zero;
- host attachment delay must be finite and at least zero;
- host attachment packet loss must be finite and within `[0, 100]`.

It does not require these fields to be present. The model checks only supplied values. Therefore:

- a DESIGN topology with `None` attachment metrics is valid;
- `None` is a supported topology state;
- a topology is not required to declare complete attachment metrics before activation.

The switch-link validator applies the same optional-but-valid-when-present semantics to link capacity, delay, and loss.

## 4. End-to-end versus switch-core path semantics

IntentFlow currently defines `_path_facts()` as an end-to-end physical path calculation:

- bandwidth: minimum across switch links and source/destination host attachments;
- delay: sum across switch links and source/destination host attachments;
- packet loss: survival product across switch links and source/destination host attachments.

This implementation is visible in `backend/planner/topology_planning.py`.

The README also calls this a complete physical path and separately describes host attachment connections. The frontend topology link table presents host attachment and switch-switch rows together.

There is also a narrower switch-link helper:

- `physical_path_capacity_mbps()` in `backend/planner/path_enumeration.py`
- docstring explicitly: `Host attachments do not contribute a switch-link capacity`

That helper is a switch-core capacity function, not a general end-to-end path-metric function.

The current product has two related but distinct concepts:

1. exact switch-link capacity;
2. end-to-end bandwidth/delay/loss that include endpoint attachments.

The API `_path_facts()` currently exposes the second concept.

## 5. Frontend topology generator

`frontend/src/lib/topology-generator.ts` always assigns complete host attachment metrics:

- `attachment_capacity_mbps`
- `attachment_delay_ms`
- `attachment_packet_loss_percent`
- `attachment_admin_up`

For seeded/generated topologies, the attachment values are sampled inside the configured ranges. The frontend generator test suite verifies connected graphs and seed repeatability, and no test defines missing attachment metrics as a generated state.

Therefore, generated complete topologies are consistent with fail-closed end-to-end semantics.

## 6. Frontend topology editor

The topology editor can display and edit attachment metrics.

When a new host is added, `frontend/src/components/topology/topology-page.tsx` sets:

- attachment administrative state;
- IP, MAC, switch and switch port;

but does not set attachment capacity, delay or loss. Those fields remain `null/undefined`.

The editor explicitly permits blank attachment fields and serializes them as `null` through `frontend/src/components/topology/topology-page.tsx`.

Consequently, an editor-authored topology can intentionally or inadvertently contain unknown attachment metrics. This is legitimate under the current model because topology validation permits `None`.

The topology generator and editor therefore support two states:

- complete generated attachments;
- incomplete/manual attachments.

## 7. Live Mininet behavior

`backend/decision/topology_graph.py` constructs live `Host` records from Mininet and leaves:

- `attachment_capacity_mbps`
- `attachment_delay_ms`
- `attachment_packet_loss_percent`
- `attachment_admin_up`

at their defaults.

At least one switch-link property is populated for TCLink links, especially bandwidth. The live graph does not supply endpoint attachment metrics.

This creates a real semantic ambiguity:

- switch-link capacity is known;
- end-to-end capacity including host attachments is unknown;
- delay and loss may also be known or unknown according to the data source.

It is therefore legitimate for attachment metrics to be unavailable in live discovery. It does not justify treating those missing values as zero or omitted.

## 8. Existing saved/design topology examples

No persisted topology SQLite file or JSON saved-design corpus was found in the repository.

The generated frontend topology and `_diamond_topology()` test fixture are the two main design topology sources inspected. The random generator supplies complete attachment metrics; the test fixture omits them.

This means the failing test fixture is not matching the generated complete-topology representation.

## 9. Every relevant attachment fixture

### `_diamond_topology()` fixture

Location: `tests/test_topology_catalog.py`

It constructs h1 and h4 with no attachment capacity, delay or loss.

It is used with complete switch-link metrics for:

- highest bandwidth;
- lowest latency;
- combined bandwidth/loss/latency;
- no-eligible and 200-Mbps cases;
- equal-delay tie ranking;
- missing-link capacity;
- activation and preview tests.

Classification: **complete physical topology fixture with accidentally omitted attachment facts**.

The switch-link metrics and expected path results indicate that attachment metrics were intended to be known as neutral or complete values.

### Arbitrary campus fixture

Location: `tests/test_topology_catalog.py`

The `client` and `server` hosts omit attachment metrics.

The switch links have bandwidth and delay and the test expects highest-bandwidth, lowest-latency and constrained ranking.

Classification: **complete physical topology fixture with accidentally omitted attachment facts**.

### Activation/version fixture

Location: `tests/test_topology_catalog.py`, second topology at the bottom of the file

Hosts `ha` and `hb` omit attachment metrics.

This fixture appears in topology activation/version testing rather than in a path-metric assertion.

Classification: **topology activation fixture; attachment completeness is not its tested behavior**. It can remain omitted if no metric is requested, but adding neutral complete values would make it a physically complete fixture consistently.

### Live topology fixture

Location: `tests/test_api.py`

Hosts in `live_topology_payload` omit attachment metrics.

Classification: **legitimate incomplete attachment-metric topology** if representing live/discovered Mininet state.

This fixture should not automatically be changed unless its test specifically requests end-to-end attachment-aware planning. It demonstrates that live graphs can have missing attachments.

## 10. Exact failing test-fixture classification

All 10 WSL failures are in `tests/test_topology_catalog.py`.

The failures use:

- `_diamond_topology()` in 9 path-planning or result tests;
- the arbitrary `client/server` topology in 1 ranking test.

The `_diamond_topology()` host omissions explain:

- bandwidth no-longer-selected failures;
- latency no-longer-selected failures;
- combined constraint failures;
- tie-ranking failure;
- missing-link alternate candidate failure.

The arbitrary topology host omissions explain the campus ranking failure.

These fixtures are not intentionally testing missing attachment values. The dedicated missing-attachment tests are `tests/test_topology_planning_metrics.py`, added after the fix, and the file now directly distinguishes unknown attachment facts.

## 11. Should incomplete fixtures supply metrics?

Yes.

For complete fixtures that assert ranking or constraint satisfaction, add valid neutral attachment metrics:

### `_diamond_topology()`

For h1 and h4 add:

```python
attachment_capacity_mbps=1000,
attachment_delay_ms=0,
attachment_packet_loss_percent=0,
attachment_admin_up=True,
```

This preserves the existing switch-link bottlenecks and loss/delay expectations:

- bandwidth remains 10 or 50 Mbps;
- delay remains the sum of switch-link delays;
- loss remains the switch-link loss aggregate;
- low/high path ranking remains unchanged;
- the equal-delay test remains tied at 0 if switch-link delays are set to 0.

### Arbitrary campus fixture

For `client` and `server` add:

```python
attachment_capacity_mbps=100,
attachment_delay_ms=0,
attachment_packet_loss_percent=0,
attachment_admin_up=True,
```

This preserves:

- 10-Mbps versus 50-Mbps switch-link ranking;
- 2-ms versus 8-ms switch-hop delay ranking;
- constraint behavior.

### Activation-only fixture

For `ha` and `hb`, valid values are optional. If it is meant to represent a complete topology, add neutral or representative metrics consistently.

## 12. When missing attachment values should remain UNKNOWN

A candidate should remain `UNKNOWN` when a requested end-to-end aggregate depends on a missing attachment metric.

Examples:

- bandwidth hard constraint, when a source/destination attachment capacity is missing;
- delay hard constraint or minimize-delay objective, when an endpoint attachment delay is missing;
- packet-loss constraint or objective, when an endpoint attachment loss is missing.

This prevents a candidate from gaining a false pass or complete objective ranking.

## 13. Legitimate unavailable attachment cases

Legitimate cases exist:

- live Mininet discovery currently does not populate attachment metrics;
- manually edited/ imported DESIGN topologies may leave fields blank;
- partial catalog/import data may intentionally contain no attachment facts;
- a topology may know link metrics but not host NIC or host-link characteristics.

In these cases, attachment-aware end-to-end metrics must be `UNKNOWN`.

If the product instead wants switch-core planning, it should expose and test a separate switch-link-only metric rather than silently omitting missing attachment facts from an end-to-end calculation.

## 14. Does the fail-closed implementation match the API contract?

For an **end-to-end path metric**, yes:

- `_path_facts()` explicitly includes host attachments;
- the API reports configured path facts;
- missing facts must not become passing constraints;
- `UNKNOWN` is the correct result.

For a **switch-core metric**, no separate API semantics currently protect this case:

- `physical_path_capacity_mbps()` excludes host attachments;
- `_path_facts()` includes them;
- the live graph omits them;
- the API does not expose a separate switch-core bandwidth/delay/loss metric.

This is a semantic split, not a reason to remove fail-closing.

## 15. Answers

### A. Does IntentFlow define end-to-end path metrics as including host-switch attachment links?

Yes. `_path_facts()` includes source/destination attachment capacity, delay and packet loss in complete-path aggregates.

The separate `physical_path_capacity_mbps()` function only computes switch-link bottleneck capacity and explicitly excludes host attachments.

### B. If yes, should incomplete fixtures be updated to supply valid attachment metrics?

Yes, when the fixture represents a complete path or asserts ranking/constraint behavior.

### C. Should a candidate with missing attachment metrics be UNKNOWN rather than ELIGIBLE?

Yes for attachment-dependent end-to-end metrics. Missing data must not be interpreted as zero or as satisfied.

### D. Are there any legitimate cases where attachment metrics are unavailable but switch-link metrics should still support planning?

Yes:

- live Mininet discovery;
- incomplete manual/imported DESIGN topologies;
- intentionally unknown host attachment facts.

The correct response is a separate switch-core metric or an explicit per-metric semantics model, not omission from end-to-end aggregation.

### E. Does the current fail-closed implementation match the actual product and API contract?

For complete end-to-end `_path_facts()` semantics, yes.

The product also permits incomplete attachment facts, so it currently lacks a clear public separation between:

- end-to-end metrics;
- switch-core metrics.

This remaining semantic distinction should be documented and tested if switch-link-only planning is intended.

## 16. Recommended smallest test-only changes

No test changes are recommended yet because the requested stage is investigation only.

If approved later:

1. Update h1/h4 in `_diamond_topology()` to attach valid neutral metrics.
2. Update `client/server` in the arbitrary campus topology to attach valid neutral metrics.
3. Optionally update `ha/hb` activation fixtures for consistency.
4. Preserve dedicated missing-metric regressions in `tests/test_topology_planning_metrics.py`.
5. Keep the missing-link capacity test in `tests/test_topology_catalog.py` and verify only its intended direct candidate is unknown.

No ranking or application code should be changed for this test-only fixture repair.

## Final recommendation

**Keep the fix and update complete fixtures.**

The implementation is mathematically correct for complete end-to-end path facts and fail-closing is required. The 10 failures mostly use complete switch-link fixtures that omitted endpoint facts; those fixtures should supply valid attachment metrics if they intend to be complete.

Missing attachment facts remain legitimate in live/manual topologies. If those topologies need switch-link-only planning, implement and document a separate switch-core metric semantics path rather than weakening end-to-end fail-closing.
