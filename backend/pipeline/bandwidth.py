"""Shared MIN_BANDWIDTH pipeline.

Final validate -> deploy -> measure, followed only in CLOSED_LOOP mode
by the bounded correction loop:
diagnose -> reconfigure -> validate -> deploy -> re-measure.

The CLI and evaluation harness both use this implementation.
"""

from __future__ import annotations

import time
from typing import Callable

from backend.compiler.reroute import compile_delete_flows, compile_reroute
from backend.deployment.ofctl_client import delete_flow, deploy_rules
from backend.measurement.throughput import measure_throughput

from backend.models.deployment import DeploymentResult
from backend.models.evaluation import BandwidthPipelineResult, Mode
from backend.models.feedback import (
    MAX_CORRECTION_ITERATIONS,
    MIN_BACKGROUND_RATE_MBPS,
    next_background_rate_mbps,
)
from backend.models.measurement import ThroughputResult
from backend.models.validation import ValidationResult

from backend.validator.path_validator import (
    validate_flow_rules,
    validate_path_for_bandwidth,
)


SetupBackgroundTraffic = Callable[[float], None]


def make_candidate_deploy_and_measure(
    net,
    graph,
    target_mbps: float,
    base_url: str,
    setup_background_traffic: SetupBackgroundTraffic,
    background_rate_mbps: float,
    port: int = 5201,
    verbose: bool = True,
) -> Callable[[list[str]], ThroughputResult]:
    """Build the candidate path deployment and measurement closure."""

    all_switches = list(graph.switches)

    def deploy_and_measure(path: list[str]) -> ThroughputResult:
        src_ip = graph.hosts[path[0]].ip
        dst_ip = graph.hosts[path[-1]].ip

        # Remove stale flows before installing candidate rules.
        for switch in all_switches:
            stale = compile_delete_flows(
                graph,
                [path[0], switch, path[-1]],
                src_ip,
                dst_ip,
            )

            for rule in stale:
                if not delete_flow(rule, base_url=base_url):
                    reason = (
                        f"Failed to delete stale flow on switch {switch} "
                        f"for candidate {' -> '.join(path)}"
                    )

                    if verbose:
                        print(f"  Candidate: CLEANUP FAILED ({reason})")

                    return ThroughputResult(
                        succeeded=False,
                        error=reason,
                        raw_output="",
                    )

        # Validate the candidate path.
        validation = validate_path_for_bandwidth(
            graph,
            path,
            src_ip,
            dst_ip,
            target_mbps,
        )

        if not validation.valid:
            reason = "; ".join(validation.reasons)

            if verbose:
                print(
                    f"  Candidate {' -> '.join(path)}: "
                    f"VALIDATION FAILED ({reason})"
                )

            return ThroughputResult(
                succeeded=False,
                error=reason,
                raw_output="",
            )

        # Compile and validate OpenFlow rules.
        rules = compile_reroute(graph, path, src_ip, dst_ip)
        rule_validation = validate_flow_rules(graph, rules)

        if not rule_validation.valid:
            reason = "; ".join(rule_validation.reasons)

            if verbose:
                print(
                    f"  Candidate {' -> '.join(path)}: "
                    f"COMPILED RULES INVALID ({reason})"
                )

            return ThroughputResult(
                succeeded=False,
                error=reason,
                raw_output="",
            )

        # Deploy and verify the rules.
        deployment = deploy_rules(rules, base_url=base_url)

        if not deployment.success:
            reason = "; ".join(deployment.errors)

            if verbose:
                print(
                    f"  Candidate {' -> '.join(path)}: "
                    f"DEPLOYMENT FAILED ({reason})"
                )

            return ThroughputResult(
                succeeded=False,
                error=reason,
                raw_output="",
            )

        # Start background traffic only after successful deployment.
        setup_background_traffic(background_rate_mbps)
        time.sleep(0.3)

        throughput = measure_throughput(
            net.get(path[0]),
            net.get(path[-1]),
            dst_ip,
            duration_s=5,
            port=port,
        )

        if verbose:
            achieved = throughput.achieved_mbps

            print(
                f"  Candidate {' -> '.join(path)}: "
                f"deployed OK, measured achieved throughput = "
                f"{achieved if achieved is not None else 'unreachable'} Mbps "
                f"(target {target_mbps} Mbps)"
            )

        return throughput

    return deploy_and_measure


def run_bandwidth_pipeline(
    net,
    graph,
    source: str,
    destination: str,
    target_mbps: float,
    base_url: str,
    selected_path: list[str],
    setup_background_traffic: SetupBackgroundTraffic,
    initial_background_rate_mbps: float,
    mode: Mode = "CLOSED_LOOP",
    port: int = 5201,
    verbose: bool = True,
):
    """Validate, deploy and measure a selected bandwidth configuration.

    Failed validation, stale-flow cleanup, deployment or measurement
    stops execution without claiming that the target was achieved.
    """

    t_start = time.monotonic()

    src_ip = graph.hosts[source].ip
    dst_ip = graph.hosts[destination].ip
    all_switches = list(graph.switches)

    def _log(message: str) -> None:
        if verbose:
            print(message)

    def _failed_measurement(reason: str) -> ThroughputResult:
        return ThroughputResult(
            succeeded=False,
            error=reason,
            raw_output="",
        )

    def _failed_deployment(reason: str) -> DeploymentResult:
        return DeploymentResult(
            requested_count=0,
            accepted_count=0,
            verified_count=0,
            errors=[reason],
        )

    def _remove_stale_flows() -> list[str]:
        """Remove old path-specific flows and return deletion errors."""

        errors: list[str] = []

        for switch in all_switches:
            stale = compile_delete_flows(
                graph,
                [selected_path[0], switch, selected_path[-1]],
                src_ip,
                dst_ip,
            )

            for rule in stale:
                if not delete_flow(rule, base_url=base_url):
                    errors.append(
                        f"Failed to delete stale flow on switch {switch}: "
                        f"{rule.label or rule.match}"
                    )

        return errors

    def _early_failure(
        reason: str,
        path_validation: ValidationResult,
        rule_validation: ValidationResult,
        deployment: DeploymentResult,
    ):
        """Build a consistent result when execution stops before measuring."""

        _log(f"  PIPELINE STOPPED: {reason}")

        measurement = _failed_measurement(reason)

        result = BandwidthPipelineResult(
            mode=mode,
            target_mbps=target_mbps,
            selected_path=selected_path,
            initial_throughput_mbps=None,
            initial_satisfied=False,
            correction_iterations=0,
            correction_history=[],
            background_rate_changes_mbps=[],
            final_throughput_mbps=None,
            final_satisfied=False,
            final_validation_valid=path_validation.valid
            and rule_validation.valid,
            final_deployment_success=deployment.success,
            execution_time_s=time.monotonic() - t_start,
            failure_reason=reason,
        )

        return (
            result,
            path_validation,
            rule_validation,
            deployment,
            measurement,
        )

    # ---------------------------------------------------------
    # 1. Validate the selected path
    # ---------------------------------------------------------

    final_validation = validate_path_for_bandwidth(
        graph,
        selected_path,
        src_ip,
        dst_ip,
        target_mbps,
    )

    if not final_validation.valid:
        reason = (
            "Path validation failed: "
            + "; ".join(final_validation.reasons)
        )

        return _early_failure(
            reason,
            final_validation,
            ValidationResult.fail(
                "Rule validation skipped because path validation failed."
            ),
            _failed_deployment(
                "Deployment skipped because path validation failed."
            ),
        )

    # ---------------------------------------------------------
    # 2. Compile and validate OpenFlow rules
    # ---------------------------------------------------------

    final_rules = compile_reroute(
        graph,
        selected_path,
        src_ip,
        dst_ip,
    )

    final_rule_validation = validate_flow_rules(
        graph,
        final_rules,
    )

    if not final_rule_validation.valid:
        reason = (
            "Flow-rule validation failed: "
            + "; ".join(final_rule_validation.reasons)
        )

        return _early_failure(
            reason,
            final_validation,
            final_rule_validation,
            _failed_deployment(
                "Deployment skipped because compiled rules failed validation."
            ),
        )

    # ---------------------------------------------------------
    # 3. Remove stale flows and deploy the selected path
    # ---------------------------------------------------------

    cleanup_errors = _remove_stale_flows()

    if cleanup_errors:
        reason = (
            "Initial stale-flow cleanup failed: "
            + "; ".join(cleanup_errors)
        )

        return _early_failure(
            reason,
            final_validation,
            final_rule_validation,
            _failed_deployment(
                "Deployment skipped because stale-flow cleanup failed."
            ),
        )

    final_deployment = deploy_rules(
        final_rules,
        base_url=base_url,
    )

    if not final_deployment.success:
        reason = (
            "Initial deployment failed: "
            + "; ".join(final_deployment.errors)
        )

        return _early_failure(
            reason,
            final_validation,
            final_rule_validation,
            final_deployment,
        )

    # ---------------------------------------------------------
    # 4. Start background traffic and take initial measurement
    # ---------------------------------------------------------

    setup_background_traffic(initial_background_rate_mbps)
    time.sleep(0.3)

    measurement = measure_throughput(
        net.get(source),
        net.get(destination),
        dst_ip,
        duration_s=5,
        port=port,
    )

    achieved = measurement.achieved_mbps
    initial_throughput_mbps = achieved

    initial_satisfied = (
        measurement.succeeded
        and achieved is not None
        and achieved >= target_mbps
    )

    satisfied = initial_satisfied

    if not measurement.succeeded or achieved is None:
        failure_reason = (
            f"Initial iperf3 measurement failed: {measurement.error}"
        )
        satisfied = False

    elif satisfied:
        failure_reason = None

    else:
        failure_reason = (
            f"Measured {achieved} Mbps < target {target_mbps} Mbps"
        )

    _log(
        f"  [{mode}] initial measured throughput = "
        f"{achieved if achieved is not None else 'unreachable'} Mbps "
        f"(target {target_mbps} Mbps) -> "
        f"{'SATISFIED' if satisfied else 'NOT SATISFIED'}"
    )

    current_background_rate = initial_background_rate_mbps
    background_rate_changes = [initial_background_rate_mbps]

    correction_iterations = 0
    correction_history: list[dict] = []

    # ---------------------------------------------------------
    # 5. Bounded CLOSED_LOOP correction
    # ---------------------------------------------------------

    if (
        mode == "CLOSED_LOOP"
        and measurement.succeeded
        and achieved is not None
    ):

        while (
            not satisfied
            and correction_iterations < MAX_CORRECTION_ITERATIONS
        ):

            if current_background_rate <= MIN_BACKGROUND_RATE_MBPS:
                correction_history.append({
                    "iteration": correction_iterations + 1,
                    "diagnosis": (
                        "Background traffic is already at its minimum rate."
                    ),
                    "action_taken": None,
                })
                break

            new_rate = next_background_rate_mbps(
                current_background_rate,
                target_mbps,
                achieved,
            )

            if new_rate >= current_background_rate - 1e-9:
                break

            correction_iterations += 1

            rate_before = current_background_rate
            measured_before = achieved

            _log(
                f"  [{mode}] correction "
                f"{correction_iterations}/{MAX_CORRECTION_ITERATIONS}: "
                f"background {rate_before:.2f} -> "
                f"{new_rate:.2f} Mbps"
            )

            # Revalidate the selected path.
            revalidation = validate_path_for_bandwidth(
                graph,
                selected_path,
                src_ip,
                dst_ip,
                target_mbps,
            )

            if not revalidation.valid:
                final_validation = revalidation

                failure_reason = (
                    "Correction stopped: path revalidation failed: "
                    + "; ".join(revalidation.reasons)
                )

                satisfied = False
                achieved = None
                measurement = _failed_measurement(failure_reason)

                correction_history.append({
                    "iteration": correction_iterations,
                    "background_rate_before_mbps": rate_before,
                    "background_rate_after_mbps": new_rate,
                    "measured_mbps_before": measured_before,
                    "measured_mbps_after": None,
                    "revalidation_valid": False,
                    "redeployment_success": False,
                    "satisfied_after": False,
                    "failure_reason": failure_reason,
                })

                _log(f"    {failure_reason}")
                break

            # Recompile and validate rules before redeployment.
            corrected_rules = compile_reroute(
                graph,
                selected_path,
                src_ip,
                dst_ip,
            )

            corrected_rule_validation = validate_flow_rules(
                graph,
                corrected_rules,
            )

            final_rule_validation = corrected_rule_validation

            if not corrected_rule_validation.valid:
                failure_reason = (
                    "Correction stopped: compiled rule validation failed: "
                    + "; ".join(corrected_rule_validation.reasons)
                )

                satisfied = False
                achieved = None
                measurement = _failed_measurement(failure_reason)

                correction_history.append({
                    "iteration": correction_iterations,
                    "background_rate_before_mbps": rate_before,
                    "background_rate_after_mbps": new_rate,
                    "measured_mbps_before": measured_before,
                    "measured_mbps_after": None,
                    "revalidation_valid": True,
                    "rule_validation_valid": False,
                    "redeployment_success": False,
                    "satisfied_after": False,
                    "failure_reason": failure_reason,
                })

                _log(f"    {failure_reason}")
                break

            # Remove stale flows before redeployment.
            cleanup_errors = _remove_stale_flows()

            if cleanup_errors:
                failure_reason = (
                    "Correction stopped: stale-flow cleanup failed: "
                    + "; ".join(cleanup_errors)
                )

                satisfied = False
                achieved = None
                measurement = _failed_measurement(failure_reason)

                correction_history.append({
                    "iteration": correction_iterations,
                    "background_rate_before_mbps": rate_before,
                    "background_rate_after_mbps": new_rate,
                    "measured_mbps_before": measured_before,
                    "measured_mbps_after": None,
                    "revalidation_valid": True,
                    "rule_validation_valid": True,
                    "redeployment_success": False,
                    "satisfied_after": False,
                    "failure_reason": failure_reason,
                })

                _log(f"    {failure_reason}")
                break

            # Redeploy and verify the corrected rules.
            redeployment = deploy_rules(
                corrected_rules,
                base_url=base_url,
            )

            final_deployment = redeployment
            final_validation = revalidation

            if not redeployment.success:
                failure_reason = (
                    "Correction stopped: redeployment failed: "
                    + "; ".join(redeployment.errors)
                )

                satisfied = False
                achieved = None
                measurement = _failed_measurement(failure_reason)

                correction_history.append({
                    "iteration": correction_iterations,
                    "background_rate_before_mbps": rate_before,
                    "background_rate_after_mbps": new_rate,
                    "measured_mbps_before": measured_before,
                    "measured_mbps_after": None,
                    "revalidation_valid": True,
                    "rule_validation_valid": True,
                    "redeployment_success": False,
                    "satisfied_after": False,
                    "failure_reason": failure_reason,
                })

                _log(f"    {failure_reason}")
                break

            # Change background traffic only after successful redeployment.
            current_background_rate = new_rate
            background_rate_changes.append(current_background_rate)

            setup_background_traffic(current_background_rate)
            time.sleep(0.3)

            # Measure the corrected configuration.
            measurement = measure_throughput(
                net.get(source),
                net.get(destination),
                dst_ip,
                duration_s=5,
                port=port,
            )

            achieved = measurement.achieved_mbps

            satisfied = (
                measurement.succeeded
                and achieved is not None
                and achieved >= target_mbps
            )

            if not measurement.succeeded or achieved is None:
                failure_reason = (
                    f"Correction measurement failed: {measurement.error}"
                )

            elif satisfied:
                failure_reason = None

            else:
                failure_reason = (
                    f"Measured {achieved} Mbps < target "
                    f"{target_mbps} Mbps after correction"
                )

            correction_history.append({
                "iteration": correction_iterations,
                "background_rate_before_mbps": rate_before,
                "background_rate_after_mbps": current_background_rate,
                "measured_mbps_before": measured_before,
                "measured_mbps_after": achieved,
                "revalidation_valid": True,
                "rule_validation_valid": True,
                "redeployment_success": True,
                "satisfied_after": satisfied,
            })

            _log(
                f"    re-measured = "
                f"{achieved if achieved is not None else 'unreachable'} Mbps -> "
                f"{'SATISFIED' if satisfied else 'NOT SATISFIED'}"
            )

            # Failed measurements cannot drive another correction.
            if not measurement.succeeded or achieved is None:
                break

    # ---------------------------------------------------------
    # 6. Produce the final result
    # ---------------------------------------------------------

    result = BandwidthPipelineResult(
        mode=mode,
        target_mbps=target_mbps,
        selected_path=selected_path,
        initial_throughput_mbps=initial_throughput_mbps,
        initial_satisfied=initial_satisfied,
        correction_iterations=correction_iterations,
        correction_history=correction_history,
        background_rate_changes_mbps=background_rate_changes,
        final_throughput_mbps=achieved,
        final_satisfied=satisfied,
        final_validation_valid=(
            final_validation.valid
            and final_rule_validation.valid
        ),
        final_deployment_success=final_deployment.success,
        execution_time_s=time.monotonic() - t_start,
        failure_reason=failure_reason,
    )

    return (
        result,
        final_validation,
        final_rule_validation,
        final_deployment,
        measurement,
    )