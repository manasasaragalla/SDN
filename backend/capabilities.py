"""Pure metric, action, and topology capability resolution.

This module describes implemented capabilities; it does not deploy flows,
measure traffic, or choose an execution strategy.
"""

from __future__ import annotations

import ipaddress
import math
from enum import Enum
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.models.canonical_intent import (
    CanonicalIntent,
    Comparison,
    MetricConstraint,
    OptimizationDirection,
    OptimizationObjective,
    RequestedAction,
)
from backend.models.intent_normalization import (
    LegacyExecutionHint,
    NormalizedIntent,
)
from backend.models.fingerprints import model_fingerprint
from backend.models.metric_definitions import (
    MetricDefinition,
    get_metric_definition,
)
from backend.models.network import TopologyGraph
from backend.validator.path_validator import validate_rate_limit


class CapabilityStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONDITIONAL = "CONDITIONAL"


class EligibilityStatus(str, Enum):
    CAPABILITY_READY = "CAPABILITY_READY"
    CONDITIONAL = "CONDITIONAL"
    INELIGIBLE = "INELIGIBLE"


class ExecutionStatus(str, Enum):
    NOT_DISPATCHED = "NOT_DISPATCHED"


class DeploymentStatus(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class SatisfactionStatus(str, Enum):
    NOT_VERIFIED = "NOT_VERIFIED"


class ExecutionMode(str, Enum):
    LEGACY = "LEGACY"
    GENERALIZED = "GENERALIZED"


class CapabilityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CapabilityStatus
    reasons: tuple[str, ...] = ()
    missing_conditions: tuple[str, ...] = ()


class MetricCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    measurable: CapabilityCheck
    plannable: CapabilityCheck
    executable: CapabilityCheck


class RequirementResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    kind: Literal["constraint", "optimization", "action"]
    metric: str | None = None
    action: str | None = None
    recognized: CapabilityCheck
    validated: CapabilityCheck
    measurable: CapabilityCheck | None = None
    plannable: CapabilityCheck
    executable: CapabilityCheck
    generalized_objective_ranking: CapabilityCheck | None = None


class CapabilityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_fingerprint: str
    topology_fingerprint: str
    request: CapabilityCheck
    scope: CapabilityCheck
    topology: CapabilityCheck
    legacy_metadata: CapabilityCheck
    constraints: list[RequirementResolution] = Field(default_factory=list)
    optimization: RequirementResolution | None = None
    actions: list[RequirementResolution] = Field(default_factory=list)
    eligibility: EligibilityStatus
    execution_status: ExecutionStatus = ExecutionStatus.NOT_DISPATCHED
    deployment_status: DeploymentStatus = DeploymentStatus.NOT_ATTEMPTED
    satisfaction_status: SatisfactionStatus = SatisfactionStatus.NOT_VERIFIED
    reasons: list[str] = Field(default_factory=list)
    legacy_execution_hint: LegacyExecutionHint | None = None
    execution_mode: ExecutionMode | None = None

    @property
    def capability_ready(self) -> bool:
        """True when requirements pass capability checks, not when executed."""

        return self.eligibility == EligibilityStatus.CAPABILITY_READY


_SUPPORTED = CapabilityStatus.SUPPORTED
_UNSUPPORTED = CapabilityStatus.UNSUPPORTED
_CONDITIONAL = CapabilityStatus.CONDITIONAL


def _check(
    status: CapabilityStatus,
    reason: str | None = None,
    missing: str | None = None,
) -> CapabilityCheck:
    return CapabilityCheck(
        status=status,
        reasons=(reason,) if reason else (),
        missing_conditions=(missing,) if missing else (),
    )


_METRIC_CAPABILITIES = MappingProxyType({
    "latency": MetricCapability(
        measurable=_check(_SUPPORTED, "Measured using ping RTT."),
        plannable=_check(
            _CONDITIONAL,
            "Path selection exists only for the legacy MINIMIZE_LATENCY objective.",
            "A matching legacy execution hint and topology are required.",
        ),
        executable=_check(
            _CONDITIONAL,
            "The existing legacy latency pipeline deploys and measures candidate paths.",
            "Generalized constraint/optimization orchestration is not implemented.",
        ),
    ),
    "bandwidth": MetricCapability(
        measurable=_check(_SUPPORTED, "Measured using iperf3 receiver throughput."),
        plannable=_check(
            _CONDITIONAL,
            "Target-based path selection exists only for the legacy MIN_BANDWIDTH objective.",
            "A matching legacy execution hint and topology are required.",
        ),
        executable=_check(
            _CONDITIONAL,
            "The existing legacy bandwidth pipeline deploys, measures, and has bounded QoS correction.",
            "Generalized constraint/optimization orchestration is not implemented.",
        ),
    ),
    "packet_loss": MetricCapability(
        measurable=_check(
            _SUPPORTED,
            "ping exposes packet-loss percentage as a measurement field.",
        ),
        plannable=_check(
            _UNSUPPORTED,
            "No packet-loss constraint planner or evaluator is implemented.",
        ),
        executable=_check(
            _UNSUPPORTED,
            "No packet-loss enforcement strategy is implemented.",
        ),
    ),
    "jitter": MetricCapability(
        measurable=_check(
            _UNSUPPORTED,
            "No explicit jitter measurement is implemented; ping mdev is not treated as jitter.",
        ),
        plannable=_check(_UNSUPPORTED, "No jitter planner is implemented."),
        executable=_check(_UNSUPPORTED, "No jitter enforcement strategy is implemented."),
    ),
    "availability": MetricCapability(
        measurable=_check(_UNSUPPORTED, "No availability measurement is implemented."),
        plannable=_check(_UNSUPPORTED, "No availability planner is implemented."),
        executable=_check(_UNSUPPORTED, "No availability enforcement strategy is implemented."),
    ),
})


_ACTION_NAMES = {"reroute", "rate_limit", "prioritize", "allow", "block"}


def _is_legacy_pipeline_shape(
    normalized: NormalizedIntent,
) -> bool:
    intent = normalized.canonical
    if intent.requested_actions:
        return False
    if normalized.legacy_execution_hint == LegacyExecutionHint.MINIMIZE_LATENCY:
        return (
            not intent.constraints
            and intent.optimization is not None
            and intent.optimization.metric == "latency"
            and intent.optimization.direction == OptimizationDirection.MINIMIZE
            and intent.optimization.unit == "ms"
        )
    if normalized.legacy_execution_hint == LegacyExecutionHint.MIN_BANDWIDTH:
        return (
            intent.optimization is None
            and len(intent.constraints) == 1
            and intent.constraints[0].metric == "bandwidth"
            and intent.constraints[0].comparison == Comparison.GTE
            and intent.constraints[0].unit == "Mbps"
        )
    return False


def _domain_error(
    definition: MetricDefinition,
    constraint: MetricConstraint,
) -> str | None:
    values = (
        (constraint.lower_bound, constraint.upper_bound)
        if constraint.comparison == Comparison.BETWEEN
        else (constraint.value,)
    )
    for value in values:
        if value is None:
            continue
        problem = definition.validate_value(value)
        if problem:
            return f"{constraint.metric} value {value:g} {problem}"

    lower = definition.minimum
    upper = definition.maximum
    comparison = constraint.comparison
    value = constraint.value
    if comparison == Comparison.BETWEEN:
        if (
            upper is not None and constraint.lower_bound > upper
        ) or (
            lower is not None and constraint.upper_bound < lower
        ):
            return f"{constraint.metric} range does not intersect its valid value domain"
    elif comparison in (Comparison.GT, Comparison.GTE):
        if upper is not None and (
            value > upper or (value == upper and comparison == Comparison.GT)
        ):
            return f"{constraint.metric} lower threshold cannot be satisfied"
    elif comparison in (Comparison.LT, Comparison.LTE):
        if lower is not None and (
            value < lower or (value == lower and comparison == Comparison.LT)
        ):
            return f"{constraint.metric} upper threshold cannot be satisfied"
    return None


def _metric_resolution(
    requirement_id: str,
    kind: Literal["constraint", "optimization"],
    metric: str,
    unit: str,
    definition: MetricDefinition | None,
    *,
    constraint: MetricConstraint | None = None,
    legacy_supported: bool = False,
    generalized_constraint_execution: bool = False,
    generalized_objective_execution: bool = False,
) -> RequirementResolution:
    objective_ranking = None
    if kind == "optimization":
        if metric in {"latency", "bandwidth", "packet_loss"} and not legacy_supported:
            objective_ranking = _check(
                _SUPPORTED,
                "Generalized objective ranking is supported by candidate-bound, "
                "freshness-validated metric observations.",
            )
        else:
            objective_ranking = _check(
                _UNSUPPORTED,
                "Generalized objective ranking is not enabled for this metric and intent mode.",
            )
    if definition is None:
        reason = f"Metric {metric!r} has no registered definition or unit semantics."
        return RequirementResolution(
            requirement_id=requirement_id,
            kind=kind,
            metric=metric,
            recognized=_check(_UNSUPPORTED, reason),
            validated=_check(_UNSUPPORTED, reason),
            measurable=_check(_UNSUPPORTED, reason),
            plannable=_check(_UNSUPPORTED, reason),
            executable=_check(_UNSUPPORTED, reason),
            generalized_objective_ranking=objective_ranking,
        )

    recognized = _check(_SUPPORTED, f"Metric {metric!r} is registered.")
    if unit != definition.canonical_unit:
        unit_reason = (
            f"Metric {metric!r} requires canonical unit "
            f"{definition.canonical_unit!r}; unit conversion is not supported."
        )
        validated = _check(_UNSUPPORTED, unit_reason)
    else:
        domain_error = (
            _domain_error(definition, constraint)
            if constraint is not None
            else None
        )
        if (
            constraint is not None
            and constraint.tolerance is not None
            and constraint.comparison != Comparison.EQ
        ):
            domain_error = (
                "Tolerance is supported only for EQ comparisons."
            )
        validated = (
            _check(_UNSUPPORTED, domain_error)
            if domain_error
            else _check(_SUPPORTED, "Metric, unit, and value domain are valid.")
        )

    capability = _METRIC_CAPABILITIES.get(metric)
    if capability is None:
        no_implementation = "No capability record is registered for this metric."
        return RequirementResolution(
            requirement_id=requirement_id,
            kind=kind,
            metric=metric,
            recognized=recognized,
            validated=validated,
            measurable=_check(_UNSUPPORTED, no_implementation),
            plannable=_check(_UNSUPPORTED, no_implementation),
            executable=_check(_UNSUPPORTED, no_implementation),
            generalized_objective_ranking=objective_ranking,
        )

    measurable = capability.measurable
    plannable = capability.plannable
    executable = capability.executable

    if kind == "constraint" and generalized_constraint_execution:
        if (
            measurable.status == _SUPPORTED
            and validated.status == _SUPPORTED
            and metric in {"latency", "bandwidth", "packet_loss"}
        ):
            plannable = _check(
                _SUPPORTED,
                "Generalized hard-constraint evaluation supports this measured metric.",
            )
            executable = _check(
                _SUPPORTED,
                "Generalized candidate probing collects this metric and evaluates it through the hard-constraint planner.",
            )
        else:
            plannable = _check(
                _UNSUPPORTED,
                "No generalized hard-constraint measurement strategy is available for this metric.",
            )
            executable = _check(
                _UNSUPPORTED,
                "No generalized hard-constraint execution strategy is available for this metric.",
            )
    elif metric == "latency" and kind == "constraint":
        plannable = _check(
            _UNSUPPORTED,
            "Generalized latency hard-constraint planning is not implemented.",
        )
        executable = _check(
            _UNSUPPORTED,
            "The legacy latency pipeline does not execute generalized hard constraints.",
        )
    elif (
        kind == "optimization"
        and not legacy_supported
        and (
            metric in {"bandwidth", "packet_loss"}
            or generalized_objective_execution
        )
    ):
        plannable = (
            _check(
                _SUPPORTED,
                f"Deterministic generalized ranking supports {metric} objectives.",
            )
            if objective_ranking is not None
            and objective_ranking.status == _SUPPORTED
            else _check(
                _UNSUPPORTED,
                f"{metric.capitalize()} optimization is not implemented for this intent mode.",
            )
        )
        executable = (
            _check(
                _SUPPORTED,
                "Generalized candidate measurement and deployment orchestration supports this objective.",
            )
            if generalized_objective_execution
            else _check(
                _UNSUPPORTED,
                "No generalized bandwidth-objective execution strategy is implemented.",
            )
        )
    elif legacy_supported:
        plannable = _check(
            _SUPPORTED,
            f"Supported by the matching legacy {metric} decision policy.",
        )
        executable = _check(
            _SUPPORTED,
            f"Supported by the matching legacy {metric} execution pipeline.",
        )
    elif (
        kind == "optimization"
        and objective_ranking is not None
        and objective_ranking.status == _SUPPORTED
    ):
        plannable = _check(
            _SUPPORTED,
            f"Deterministic generalized ranking supports {metric} objectives.",
        )

    return RequirementResolution(
        requirement_id=requirement_id,
        kind=kind,
        metric=metric,
        recognized=recognized,
        validated=validated,
        measurable=measurable,
        plannable=plannable,
        executable=executable,
        generalized_objective_ranking=objective_ranking,
    )


def _action_resolution(
    action: RequestedAction,
    graph: TopologyGraph | None,
    paths: list[list[str]],
) -> RequirementResolution:
    name = action.name
    if name not in _ACTION_NAMES:
        reason = f"Action {name!r} has no registered capability handler."
        return RequirementResolution(
            requirement_id=f"action:{name}",
            kind="action",
            action=name,
            recognized=_check(_UNSUPPORTED, reason),
            validated=_check(_UNSUPPORTED, reason),
            plannable=_check(_UNSUPPORTED, reason),
            executable=_check(_UNSUPPORTED, reason),
        )

    recognized = _check(_SUPPORTED, f"Action {name!r} is recognized.")
    if name == "reroute":
        if action.parameters:
            validated = _check(
                _UNSUPPORTED,
                "REROUTE does not accept parameters in the implemented compiler.",
            )
        else:
            validated = _check(_SUPPORTED, "REROUTE parameters are valid.")
        return RequirementResolution(
            requirement_id="action:reroute",
            kind="action",
            action=name,
            recognized=recognized,
            validated=validated,
            plannable=_check(
                _CONDITIONAL,
                "Path compiler and deployment primitives exist, but generalized action planning is not wired.",
                "A validated topology and generalized orchestration are required.",
            ),
            executable=_check(
                _CONDITIONAL,
                "REROUTE compiler/deployment support is limited to current host-pair IPv4/ARP flows.",
                "Generalized action dispatch and deployment orchestration are not implemented.",
            ),
        )

    if name == "rate_limit":
        extra_parameters = set(action.parameters) - {"rate_mbps"}
        rate = action.parameters.get("rate_mbps")
        if extra_parameters:
            validated = _check(
                _UNSUPPORTED,
                "Unsupported RATE_LIMIT parameter(s): "
                + ", ".join(sorted(extra_parameters)),
            )
        elif (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        ):
            validated = _check(
                _CONDITIONAL,
                "A positive finite rate_mbps parameter is required.",
                "Supply a positive rate_mbps value.",
            )
        else:
            validated = _check(_SUPPORTED, "rate_mbps is positive and finite.")
        condition = (
            "The existing specialized background-flow QoS workflow must provide its required context; "
            "canonical RATE_LIMIT requests are not dispatched to it."
        )
        topology_check: CapabilityCheck
        if graph is None:
            topology_check = _check(
                _CONDITIONAL,
                "RATE_LIMIT topology requirements have not been checked.",
                "A topology graph with a switch-to-switch egress interface is required.",
            )
        else:
            suitable_paths = [
                path for path in paths
                if len(path) >= 4 and path[2] in graph.switches
            ]
            interface_paths: list[tuple[list[str], Link]] = []
            for path in suitable_paths:
                for link in graph.links:
                    if {link.node_a, link.node_b} != {path[1], path[2]}:
                        continue
                    try:
                        interface = link.intf_facing(path[1])
                    except ValueError:
                        continue
                    if interface:
                        interface_paths.append((path, link))
            if interface_paths:
                if validated.status == _SUPPORTED:
                    requested_rate = rate
                    feasible_paths = []
                    unknown_capacity = False
                    for _, link in interface_paths:
                        egress_capacity = link.bw_mbps
                        if egress_capacity is None:
                            unknown_capacity = True
                            continue
                        if (
                            not math.isfinite(egress_capacity)
                            or egress_capacity < 0
                        ):
                            unknown_capacity = True
                            continue
                        validation = validate_rate_limit(
                            requested_rate,
                            egress_capacity,
                        )
                        if validation.valid:
                            feasible_paths.append(link)
                    if feasible_paths:
                        topology_check = _check(
                            _SUPPORTED,
                            "At least one candidate QoS egress has known capacity sufficient for rate_mbps.",
                        )
                    elif unknown_capacity:
                        topology_check = _check(
                            _CONDITIONAL,
                            "No known QoS egress proves the requested rate feasible or infeasible.",
                            "QoS egress capacity metadata is required.",
                        )
                    else:
                        topology_check = _check(
                            _UNSUPPORTED,
                            "The requested rate exceeds the known QoS egress capacity on every candidate path.",
                        )
                    if topology_check.status == _UNSUPPORTED:
                        validated = topology_check
                    elif topology_check.status == _CONDITIONAL:
                        validated = topology_check
                else:
                    topology_check = _check(
                        _CONDITIONAL,
                        "QoS egress capacity was not checked because rate_mbps is invalid or missing.",
                        "Supply a positive finite rate_mbps value.",
                    )
            elif suitable_paths:
                topology_check = _check(
                    _CONDITIONAL,
                    "Candidate switch links lack recorded interface names required by the QoS compiler.",
                    "Live topology interface metadata is required.",
                )
            else:
                topology_check = _check(
                    _UNSUPPORTED,
                    "The current QoS compiler requires a candidate path with a switch-to-switch next hop.",
                )
            if not interface_paths and validated.status == _SUPPORTED:
                validated = topology_check
        return RequirementResolution(
            requirement_id="action:rate_limit",
            kind="action",
            action=name,
            recognized=recognized,
            validated=validated,
            plannable=(
                topology_check
                if topology_check.status == _UNSUPPORTED
                else _check(_CONDITIONAL, condition, condition)
            ),
            executable=(
                topology_check
                if topology_check.status == _UNSUPPORTED
                else _check(
                    _CONDITIONAL,
                    condition,
                    topology_check.missing_conditions[0]
                    if topology_check.missing_conditions
                    else condition,
                )
            ),
        )

    reason = f"No {name.upper()} planner or execution handler is implemented."
    return RequirementResolution(
        requirement_id=f"action:{name}",
        kind="action",
        action=name,
        recognized=recognized,
        validated=_check(
            _SUPPORTED if not action.parameters else _CONDITIONAL,
            "Action name is valid; parameters are declarative only."
            if action.parameters
            else "No action parameters require validation.",
            "An action-specific parameter schema is not registered."
            if action.parameters
            else None,
        ),
        plannable=_check(_UNSUPPORTED, reason),
        executable=_check(_UNSUPPORTED, reason),
    )


def _scope_and_topology(
    intent: CanonicalIntent,
    graph: TopologyGraph | None,
) -> tuple[CapabilityCheck, CapabilityCheck, list[list[str]]]:
    selector = intent.scope.selector
    if selector is not None:
        reason = (
            "The current OpenFlow compilers do not compile protocol or transport-port selectors."
        )
        return (
            _check(_UNSUPPORTED, reason),
            _check(_UNSUPPORTED, reason),
            [],
        )
    if graph is None:
        missing = "A topology graph is required to validate hosts and paths."
        return (
            _check(_CONDITIONAL, "Host endpoints have not been checked against topology.", missing),
            _check(_CONDITIONAL, "Topology feasibility is unknown.", missing),
            [],
        )
    missing_hosts = [
        host for host in (intent.scope.source, intent.scope.destination)
        if host not in graph.hosts
    ]
    if missing_hosts:
        reason = f"Unknown topology host(s): {', '.join(missing_hosts)}."
        return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []

    for host_name in (intent.scope.source, intent.scope.destination):
        host = graph.hosts[host_name]
        try:
            address = ipaddress.ip_address(host.ip)
        except ValueError:
            reason = f"Host {host_name!r} has an invalid IP address in topology metadata."
            return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []
        if address.version != 4:
            reason = f"Host {host_name!r} does not have an IPv4 address supported by current compilers."
            return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []
        if host_name == intent.scope.source:
            source_address = address
        else:
            destination_address = address
        if host.switch not in graph.switches or host.switch_port <= 0:
            reason = f"Host {host_name!r} has invalid switch attachment metadata."
            return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []

    if source_address == destination_address:
        reason = "Source and destination hosts resolve to the same IPv4 address."
        return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []

    try:
        paths = graph.all_simple_paths(
            intent.scope.source,
            intent.scope.destination,
        )
    except ValueError as exc:
        reason = f"Topology path check failed: {exc}"
        return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []
    if not paths:
        reason = "No path exists between the requested hosts in the supplied topology."
        return _check(_SUPPORTED), _check(_UNSUPPORTED, reason), []
    valid_paths: list[list[str]] = []
    for path in paths:
        if graph.validate_path(path) is not None:
            continue
        try:
            for switch in path[1:-1]:
                if switch not in graph.switches:
                    raise ValueError(f"unknown switch {switch!r}")
                for neighbor in graph.neighbors(switch):
                    if neighbor in path and neighbor in graph.switches:
                        if graph.port_between(switch, neighbor) <= 0:
                            raise ValueError("switch link has a non-positive port")
            if any(graph.hosts[host].switch_port <= 0 for host in (path[0], path[-1])):
                raise ValueError("host attachment has a non-positive port")
        except (KeyError, ValueError):
            continue
        valid_paths.append(path)
    if not valid_paths:
        reason = "No candidate path has the topology metadata required by current compilers."
        return _check(_UNSUPPORTED, reason), _check(_UNSUPPORTED, reason), []
    return (
        _check(_SUPPORTED, "Both hosts and the unselected traffic scope are supported."),
        _check(_SUPPORTED, f"Topology contains {len(valid_paths)} compiler-valid candidate path(s)."),
        valid_paths,
    )


def _check_topology_capacity(
    resolution: RequirementResolution,
    constraint: MetricConstraint,
    graph: TopologyGraph | None,
    paths: list[list[str]],
) -> None:
    if graph is None or not paths or constraint.metric != "bandwidth":
        return
    if constraint.comparison in (Comparison.GT, Comparison.GTE):
        target = constraint.value
        strict = constraint.comparison == Comparison.GT
    elif constraint.comparison == Comparison.BETWEEN:
        target = constraint.lower_bound
        strict = False
    elif constraint.comparison == Comparison.EQ:
        target = constraint.value
        strict = False
    else:
        return
    if target is None:
        return
    # This is an existential upper-bound check over physical parallel-link
    # choices, not a capacity assigned to every node-only candidate.
    capacities = [
        graph.maximum_possible_path_capacity_mbps(path)
        for path in paths
    ]
    unknown_capacity = any(
        capacity is None
        or not math.isfinite(capacity)
        or capacity < 0
        for capacity in capacities
    )
    valid_capacities = [
        capacity
        for capacity in capacities
        if capacity is not None
        and math.isfinite(capacity)
        and capacity >= 0
    ]
    if any(
        capacity > target if strict else capacity >= target
        for capacity in valid_capacities
    ):
        return
    if not unknown_capacity and len(valid_capacities) == len(capacities):
        resolution.plannable = _check(
            _UNSUPPORTED,
            f"No physical realization of the known topology paths can meet the {target:g} Mbps lower bound.",
        )
        return
    resolution.plannable = _check(
        _CONDITIONAL,
        "No known path capacity proves this bandwidth target feasible or infeasible.",
        "Complete bandwidth metadata is required for every candidate path.",
    )


def _overall_eligibility(
    request: CapabilityCheck,
    scope: CapabilityCheck,
    topology: CapabilityCheck,
    requirements: list[RequirementResolution],
) -> tuple[EligibilityStatus, list[str]]:
    checks = [request, scope, topology]
    for requirement in requirements:
        checks.extend(
            [
                requirement.recognized,
                requirement.validated,
                requirement.plannable,
                requirement.executable,
            ]
        )
        if requirement.measurable is not None:
            checks.append(requirement.measurable)

    reasons = [
        reason
        for check in checks
        if check.status != _SUPPORTED
        for reason in check.reasons + check.missing_conditions
    ]
    if any(check.status == _UNSUPPORTED for check in checks):
        return EligibilityStatus.INELIGIBLE, reasons
    if any(check.status == _CONDITIONAL for check in checks):
        return EligibilityStatus.CONDITIONAL, reasons
    return EligibilityStatus.CAPABILITY_READY, []


def resolve_capabilities(
    intent: CanonicalIntent | NormalizedIntent,
    graph: TopologyGraph | None = None,
    execution_mode: ExecutionMode | str | None = None,
) -> CapabilityResolution:
    """Assess every requirement without causing network or measurement effects.

    A normalized legacy hint can qualify only its exact existing pipeline
    shape. This function reports that compatibility but never dispatches it.
    """

    if execution_mode is not None and not isinstance(execution_mode, ExecutionMode):
        execution_mode = ExecutionMode(execution_mode)

    normalized = intent if isinstance(intent, NormalizedIntent) else None
    canonical = normalized.canonical if normalized else intent
    hint = normalized.legacy_execution_hint if normalized else None
    allow_legacy = execution_mode != ExecutionMode.GENERALIZED
    legacy_shape = bool(
        normalized
        and allow_legacy
        and _is_legacy_pipeline_shape(normalized)
    )

    scope, topology, paths = _scope_and_topology(canonical, graph)
    if (
        not canonical.constraints
        and canonical.optimization is None
        and not canonical.requested_actions
    ):
        request = _check(
            _UNSUPPORTED,
            "Intent contains no constraints, optimization objective, or requested action.",
        )
    else:
        request = _check(_SUPPORTED, "Intent contains at least one requirement.")

    if canonical.legacy_metadata is not None and canonical.legacy_metadata.loss_tolerance:
        legacy_metadata = _check(
            _CONDITIONAL,
            "Legacy loss tolerance is preserved as metadata but is not converted into a packet-loss threshold.",
            "A packet-loss semantic and enforcement policy would be required to enforce this category.",
        )
    else:
        legacy_metadata = _check(_SUPPORTED, "No unresolved legacy metadata is present.")

    unit_conflicts: set[str] = set()
    units_by_metric: dict[str, str] = {}
    for constraint in canonical.constraints:
        units_by_metric.setdefault(constraint.metric, constraint.unit)
    if canonical.optimization is not None:
        metric = canonical.optimization.metric
        existing_unit = units_by_metric.get(metric)
        if existing_unit is not None and existing_unit != canonical.optimization.unit:
            unit_conflicts.add(metric)

    constraints: list[RequirementResolution] = []
    for index, constraint in enumerate(canonical.constraints):
        is_legacy_bandwidth = bool(
            legacy_shape
            and hint == LegacyExecutionHint.MIN_BANDWIDTH
        )
        result = _metric_resolution(
            f"constraint:{index}:{constraint.metric}",
            "constraint",
            constraint.metric,
            constraint.unit,
            get_metric_definition(constraint.metric),
            constraint=constraint,
            legacy_supported=is_legacy_bandwidth,
            generalized_constraint_execution=(
                execution_mode == ExecutionMode.GENERALIZED
            ),
        )
        if constraint.metric in unit_conflicts:
            conflict = (
                f"Optimization and constraints for metric {constraint.metric!r} "
                "use different units; conversion is unsupported."
            )
            result.validated = _check(_UNSUPPORTED, conflict)
        _check_topology_capacity(result, constraint, graph, paths)
        constraints.append(result)

    optimization = None
    if canonical.optimization is not None:
        objective: OptimizationObjective = canonical.optimization
        is_legacy_latency = bool(
            legacy_shape
            and hint == LegacyExecutionHint.MINIMIZE_LATENCY
        )
        optimization = _metric_resolution(
            f"optimization:{objective.metric}",
            "optimization",
            objective.metric,
            objective.unit,
            get_metric_definition(objective.metric),
            legacy_supported=is_legacy_latency,
            generalized_objective_execution=(
                execution_mode == ExecutionMode.GENERALIZED
                and not (
                    normalized is not None
                    and hint == LegacyExecutionHint.MINIMIZE_LATENCY
                )
            ),
        )
        if objective.metric in unit_conflicts:
            conflict = (
                f"Optimization and constraints for metric {objective.metric!r} "
                "use different units; conversion is unsupported."
            )
            optimization.validated = _check(_UNSUPPORTED, conflict)

    actions = [
        _action_resolution(action, graph, paths)
        for action in canonical.requested_actions
    ]
    all_requirements = constraints + ([optimization] if optimization else []) + actions
    eligibility, reasons = _overall_eligibility(
        request,
        scope,
        topology,
        all_requirements,
    )
    return CapabilityResolution(
        intent_fingerprint=model_fingerprint(canonical),
        topology_fingerprint=model_fingerprint(graph),
        request=request,
        scope=scope,
        topology=topology,
        legacy_metadata=legacy_metadata,
        constraints=constraints,
        optimization=optimization,
        actions=actions,
        eligibility=eligibility,
        reasons=reasons,
        legacy_execution_hint=hint,
        execution_mode=execution_mode,
    )
