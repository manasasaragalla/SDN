"""End-to-end demo entry point for both objectives implemented so far:

  MINIMIZE_LATENCY: natural language -> LLM -> StructuredIntent
      -> candidate paths over the real topology, each compiled/validated/
         deployed/measured with real `ping`
      -> lowest-measured-latency path selected, re-deployed as final state,
         re-measured, intent-satisfaction checked against alternatives

  MIN_BANDWIDTH: natural language -> LLM -> StructuredIntent
      -> real background/competing traffic (h2->h3) installed and rate-
         limited via OVS QoS (see docs/adr-004-bandwidth-mechanism.md)
      -> candidate paths, each compiled/validated (incl. static capacity
         feasibility)/deployed/measured with real `iperf3`, under that
         real contention
      -> highest-measured-throughput path selected, re-deployed as final
         state, re-measured, intent-satisfaction checked against the
         numeric target (never assuming configured == achieved)

Must be run with root privileges (Mininet needs to create network
namespaces/veth pairs) using the system python3 that has both `mininet`
and this project's dependencies installed (see requirements.txt /
docs/adr-001) -- NOT the .venv-ryu virtualenv, which is for the Ryu
controller process only.

Usage:
    sudo sudo PYTHONPATH=. python3 -m backend.cli "Give h1 to h4 the lowest-latency path."
    sudo sudo PYTHONPATH=. python3 -m backend.cli "Provide at least 20 Mbps between h1 and h4."

This script manages the whole lifecycle itself (starts its own Ryu
controller subprocess, cleans up stale Mininet state, builds the
topology, tears everything down at the end) so it is a single genuinely
runnable command, not a multi-terminal manual procedure.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RYU_MANAGER = PROJECT_ROOT / ".venv-ryu" / "bin" / "ryu-manager"
OFP_PORT = 6653
WSAPI_PORT = 8080
RYU_BASE_URL = f"http://127.0.0.1:{WSAPI_PORT}"
RYU_STARTUP_TIMEOUT_S = 60.0

# This demo's fixed background-traffic scenario (Phase 11): h2->h3, capped
# below Path A's 10 Mbps link so it genuinely eats into Path A's headroom
# without starving it completely. A CLI-script-level constant, not a
# hardcoding of the decision/compiler/validator layers -- those remain
# generic over any source/destination/path/rate (see docs/adr-004).
BACKGROUND_SRC = "h2"
BACKGROUND_DST = "h3"
BACKGROUND_RATE_MBPS = 8.0
BACKGROUND_IPERF_PORT = 5202
PRIMARY_IPERF_PORT = 5201


def _wait_for_port(port: int, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _start_ryu() -> subprocess.Popen:
    proc = subprocess.Popen(
        [str(RYU_MANAGER), "ryu.app.ofctl_rest", "--ofp-tcp-listen-port", str(OFP_PORT),
         "--wsapi-port", str(WSAPI_PORT)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if not _wait_for_port(WSAPI_PORT, timeout_s=RYU_STARTUP_TIMEOUT_S):
        if proc.poll() is None:
            proc.kill()
        output, _ = proc.communicate(timeout=5)
        details = output.strip() if output else ""
        message = (
            "ryu-manager did not start listening on the REST API port "
            f"within {RYU_STARTUP_TIMEOUT_S:g} seconds"
        )
        if details:
            message += f"\nRyu output:\n{details[-4000:]}"
        raise RuntimeError(message)
    return proc


def _write_experiment_log(payload: dict) -> Path:
    from backend.orchestration.latency_evidence import (
        JSON_OUTPUT_DIR,
        persist_evidence_file,
    )

    timestamp = int(time.time())
    while True:
        out_path = JSON_OUTPUT_DIR / f"run_{timestamp}.json"
        if not out_path.exists() and not out_path.is_symlink():
            return persist_evidence_file(
                out_path,
                json.dumps(payload, indent=2, allow_nan=False) + "\n",
            )
        timestamp += 1


def run_intent(raw_intent: str, llm_provider_name: str | None = None) -> int:
    """Parses the intent and dispatches to the objective-specific pipeline.
    Shared across both objectives: LLM parsing/printing, Ryu startup,
    topology build/teardown, experiment logging."""
    from mininet.log import setLogLevel

    from backend.decision.topology_graph import build_from_mininet
    from backend.llm.base import LLMParseError
    from backend.llm.factory import get_llm_provider
    from backend.models.decision import DecisionError
    from backend.models.intent import Objective
    from testbed.topology.diamond import build_diamond_topology, start as start_topology

    setLogLevel("warning")

    print(f"Intent:\n  {raw_intent}\n")

    llm = get_llm_provider(llm_provider_name)
    llm_call_count = 1

    try:
        llm = get_llm_provider(llm_provider_name)
        intent = llm.parse_intent(raw_intent)

    except LLMParseError as exc:
        print(f"LLM could not parse this intent: {exc}")
        return 1

    except (ValueError, RuntimeError) as exc:
        print(f"Could not initialize the requested LLM provider: {exc}")
        return 1

    print("Structured intent:")

    objective_label = (
        intent.objective.value
        if intent.objective is not None
        else "GENERALIZED_CONSTRAINTS"
    )

    print(f"  objective   = {objective_label}")
    print(f"  source      = {intent.source}")
    print(f"  destination = {intent.destination}")

    if intent.target:
        print(
            f"  target      = "
            f"{intent.target.model_dump(exclude_none=True)}"
        )

    if intent.traffic_selector:
        print(
            f"  traffic     = "
            f"{intent.traffic_selector.model_dump(exclude_none=True)}"
        )

    if intent.constraints:

        if intent.constraints.loss_tolerance is not None:
            print(
                f"  loss tolerance = "
                f"{intent.constraints.loss_tolerance.value}"
            )

        for metric_constraint in intent.constraints.metrics:

            details = {
                "metric": metric_constraint.metric.value,
                "unit": metric_constraint.unit.value,
                "min_value": metric_constraint.min_value,
                "max_value": metric_constraint.max_value,
                "optimization": (
                    metric_constraint.optimization.value
                    if metric_constraint.optimization is not None
                    else None
                ),
            }

            print(f"  constraint  = {details}")

    print()

    if intent.traffic_selector is not None:
        print(
            "Traffic selectors are not supported by the current flow "
            "compiler; refusing to deploy a broader host-pair rule."
        )
        return 2

    # Generalized intents are understood but do not yet have
    # a complete execution pipeline.

    if intent.objective is None:

        print(
            "Intent understood, but generalized constraint "
            "execution is not implemented yet."
        )

        print(
            "The policy engine and generalized execution planner "
            "are the next implementation milestone."
        )

        return 2

    # Preserve the existing legacy execution pipelines.

    if intent.objective not in (
        Objective.MINIMIZE_LATENCY,
        Objective.MIN_BANDWIDTH,
    ):

        print(
            f"This demo entry point does not yet drive "
            f"{intent.objective.value} end to end."
        )

        return 2

    print("Starting Ryu controller (ofctl_rest)...")
    ryu_proc = _start_ryu()
    net = None
    log_error = None
    result_summary: dict = {}
    exit_code = 1

    try:
        print("Building testbed topology...")
        net = build_diamond_topology(controller_port=OFP_PORT)
        start_topology(net)
        time.sleep(2)  # let switches complete the OpenFlow handshake
        graph = build_from_mininet(net)

        if intent.source not in graph.hosts or intent.destination not in graph.hosts:
            print(f"Unknown host(s): source={intent.source!r} destination={intent.destination!r} "
                  f"are not in this topology (known hosts: {sorted(graph.hosts)}).")
            return 1

        if intent.objective == Objective.MINIMIZE_LATENCY:
            exit_code, result_summary = _run_latency(raw_intent, intent, llm, llm_call_count, net, graph)
        else:
            exit_code, result_summary = _run_bandwidth(raw_intent, intent, llm, llm_call_count, net, graph)

    except DecisionError as exc:
        log_error = str(exc)
        print(f"\nDecision layer could not select a path: {exc}")
        exit_code = 1
    finally:
        if net is not None:
            net.stop()
        ryu_proc.kill()
        ryu_proc.wait(timeout=5)

        if result_summary or log_error:
            payload = result_summary or {"raw_intent": raw_intent, "error": log_error}
            out_path = _write_experiment_log(payload)
            print(f"\nExperiment log written to {out_path.relative_to(PROJECT_ROOT)}")

    return exit_code


def _run_latency(raw_intent, intent, llm, llm_call_count, net, graph) -> tuple[int, dict]:
    from backend.compiler.reroute import compile_delete_flows, compile_reroute
    from backend.decision.latency_decision import select_latency_path
    from backend.deployment.ofctl_client import deploy_rules, delete_rules
    from backend.measurement.latency import measure_latency
    from backend.models.experiment_log import ExperimentLog
    from backend.models.measurement import LatencyResult
    from backend.validator.path_validator import validate_flow_rules, validate_path_for_reroute

    src_ip = graph.hosts[intent.source].ip
    dst_ip = graph.hosts[intent.destination].ip
    all_switches = list(graph.switches)

    def deploy_and_measure(path):
        for switch in all_switches:
            stale = compile_delete_flows(graph, [path[0], switch, path[-1]], src_ip, dst_ip)
            delete_rules(stale, base_url=RYU_BASE_URL)

        validation = validate_path_for_reroute(graph, "REROUTE", path, src_ip, dst_ip)
        if not validation.valid:
            print(f"  Candidate {' -> '.join(path)}: VALIDATION FAILED ({'; '.join(validation.reasons)})")
            return LatencyResult(packets_sent=0, packets_received=0, packet_loss_pct=100.0, raw_output="")

        rules = compile_reroute(graph, path, src_ip, dst_ip)
        rule_validation = validate_flow_rules(graph, rules)
        if not rule_validation.valid:
            print(f"  Candidate {' -> '.join(path)}: COMPILED RULES INVALID ({'; '.join(rule_validation.reasons)})")
            return LatencyResult(packets_sent=0, packets_received=0, packet_loss_pct=100.0, raw_output="")

        deployment = deploy_rules(rules, base_url=RYU_BASE_URL)
        if not deployment.success:
            print(f"  Candidate {' -> '.join(path)}: DEPLOYMENT FAILED ({'; '.join(deployment.errors)})")
            return LatencyResult(packets_sent=0, packets_received=0, packet_loss_pct=100.0, raw_output="")

        time.sleep(0.3)
        host = net.get(intent.source)
        latency = measure_latency(host, dst_ip, count=10)
        print(f"  Candidate {' -> '.join(path)}: deployed OK, measured avg RTT = "
              f"{latency.rtt_avg_ms if latency.rtt_avg_ms is not None else 'unreachable'} ms "
              f"({latency.packet_loss_pct}% loss)")
        return latency

    print("\nEvaluating candidate paths (each is deployed for real and measured, not estimated):")
    decision = select_latency_path(graph, intent.source, intent.destination, deploy_and_measure)

    print(f"\nSelected path:\n  {' -> '.join(decision.selected_path)}")

    for switch in all_switches:
        stale = compile_delete_flows(graph, [decision.selected_path[0], switch, decision.selected_path[-1]], src_ip, dst_ip)
        delete_rules(stale, base_url=RYU_BASE_URL)
    final_rules = compile_reroute(graph, decision.selected_path, src_ip, dst_ip)
    final_validation = validate_path_for_reroute(graph, "REROUTE", decision.selected_path, src_ip, dst_ip)
    final_rule_validation = validate_flow_rules(graph, final_rules)
    final_deployment = deploy_rules(final_rules, base_url=RYU_BASE_URL)
    time.sleep(0.3)
    final_measurement = measure_latency(net.get(intent.source), dst_ip, count=10)

    print("\nValidation:")
    print(f"  {'PASS' if final_validation.valid and final_rule_validation.valid else 'FAIL'}")
    print("\nDeployment:")
    print(f"  {'SUCCESS' if final_deployment.success else 'FAILED: ' + '; '.join(final_deployment.errors)}")
    print("\nMeasured latency (final, on selected path):")
    if final_measurement.reachable:
        print(f"  avg = {final_measurement.rtt_avg_ms} ms, loss = {final_measurement.packet_loss_pct}%")
    else:
        print("  unreachable")

    alternatives = [
        c for c in decision.candidates
        if c.path != decision.selected_path and c.latency.reachable
    ]
    alternative_rtts = [c.latency.rtt_avg_ms for c in alternatives]
    satisfied = _latency_satisfied(
        final_measurement.rtt_avg_ms,
        alternative_rtts,
    )
    if not final_measurement.reachable:
        reason = "path is unreachable after deployment"
    elif final_measurement.rtt_avg_ms is None:
        reason = "final latency measurement is unavailable"
    elif alternatives:
        beaten = sum(
            1
            for rtt in alternative_rtts
            if rtt is not None and rtt > final_measurement.rtt_avg_ms
        )
        reason = (
            f"selected path ({final_measurement.rtt_avg_ms} ms) beats "
            f"{beaten}/{len(alternatives)} measured alternative(s)"
            if satisfied
            else "selected path did not beat every measured alternative"
        )
    else:
        reason = "only one viable candidate path existed; reachable"

    print(f"\nIntent:\n  {'SATISFIED' if satisfied else 'NOT SATISFIED'} ({reason})")

    result_summary = ExperimentLog(
        raw_intent=raw_intent,
        llm_provider=llm.name,
        structured_intent=intent.model_dump(mode="json"),
        candidates=[c.model_dump(mode="json") for c in decision.candidates],
        selected_path=decision.selected_path,
        selected_action=decision.action.value,
        validation_result={"valid": final_validation.valid and final_rule_validation.valid,
                            "reasons": final_validation.reasons + final_rule_validation.reasons},
        deployment_result=final_deployment.model_dump(mode="json"),
        final_measurement=final_measurement.model_dump(mode="json"),
        intent_satisfied=satisfied,
        satisfaction_reason=reason,
        llm_call_count=llm_call_count,
    ).model_dump(mode="json")

    return (0 if satisfied else 2), result_summary


def _latency_satisfied(
    selected_rtt_ms: float | None,
    alternative_rtts_ms: list[float | None],
) -> bool:
    """A minimum-latency result requires a measured RTT that beats all
    reachable alternatives; an unmeasured alternative is not a pass."""
    return (
        selected_rtt_ms is not None
        and all(
            rtt is not None and selected_rtt_ms < rtt
            for rtt in alternative_rtts_ms
        )
    )


def _setup_background_traffic(net, graph, all_switches, rate_mbps: float = BACKGROUND_RATE_MBPS) -> tuple[list, object]:
    """(Re)installs the fixed background flow (BACKGROUND_SRC ->
    BACKGROUND_DST), rate-limited via OVS QoS to `rate_mbps`, and starts a
    real iperf3 client against it in the background (non-blocking) so it
    is actually producing contention while the primary flow is measured.
    Returns the deployed rules and QueueConfig purely for logging.

    Callable repeatedly with a different `rate_mbps` -- this is exactly
    the "reconfigure" step the Phase 12 closed correction loop in
    `_run_bandwidth` uses: each correction iteration calls this again with
    a lower rate_mbps (from `next_background_rate_mbps`), which redeploys
    the OVS QoS queue for real (not a simulated adjustment) and restarts
    the real background iperf3 client at the new cap."""
    from backend.compiler.rate_limit import compile_rate_limit
    from backend.compiler.reroute import compile_delete_flows
    from backend.deployment.ofctl_client import deploy_rules, delete_rules
    from backend.deployment.ovs_qos_client import deploy_queue
    from backend.validator.path_validator import validate_rate_limit

    bg_src_ip = graph.hosts[BACKGROUND_SRC].ip
    bg_dst_ip = graph.hosts[BACKGROUND_DST].ip
    bg_paths = graph.all_simple_paths(BACKGROUND_SRC, BACKGROUND_DST)
    bg_path = min(bg_paths, key=len)  # the direct s2-s4 hop, not the long way round via s1/s3/s5

    for switch in all_switches:
        stale = compile_delete_flows(graph, [bg_path[0], switch, bg_path[-1]], bg_src_ip, bg_dst_ip)
        delete_rules(stale, base_url=RYU_BASE_URL)

    path_capacity = graph.path_capacity_mbps(bg_path)
    rate_validation = validate_rate_limit(rate_mbps, path_capacity)
    if not rate_validation.valid:
        raise RuntimeError(f"background rate-limit config is invalid: {'; '.join(rate_validation.reasons)}")

    rules, queue = compile_rate_limit(graph, bg_path, bg_src_ip, bg_dst_ip, rate_mbps)

    if not deploy_queue(queue):
        raise RuntimeError(f"failed to deploy/verify OVS QoS queue on {queue.intf}")
    deployment = deploy_rules(rules, base_url=RYU_BASE_URL)
    if not deployment.success:
        raise RuntimeError(f"failed to deploy background-traffic flow rules: {'; '.join(deployment.errors)}")

    h2 = net.get(BACKGROUND_SRC)
    h3 = net.get(BACKGROUND_DST)
    h2.cmd(f"pkill -f 'iperf3 -c {bg_dst_ip} -p {BACKGROUND_IPERF_PORT}'")
    h3.cmd(f"pkill -f 'iperf3 -s -1 -p {BACKGROUND_IPERF_PORT}'")
    h3.cmd(f"iperf3 -s -1 -p {BACKGROUND_IPERF_PORT} > /tmp/iperf3_bg_server.log 2>&1 &")
    time.sleep(0.5)
    # Backgrounded (trailing &): runs concurrently with whatever the
    # caller measures next, for long enough to outlast that measurement.
    h2.cmd(f"timeout 15 iperf3 -c {bg_dst_ip} -p {BACKGROUND_IPERF_PORT} -t 12 "
           f"> /tmp/iperf3_bg_client.log 2>&1 &")
    time.sleep(0.5)

    return rules, queue


def _run_bandwidth(raw_intent, intent, llm, llm_call_count, net, graph) -> tuple[int, dict]:
    from backend.decision.bandwidth_decision import select_bandwidth_path
    from backend.models.experiment_log import ExperimentLog
    from backend.models.feedback import MAX_CORRECTION_ITERATIONS, BandwidthFeedback
    from backend.pipeline.bandwidth import make_candidate_deploy_and_measure, run_bandwidth_pipeline

    target_mbps = intent.target.bandwidth_mbps
    all_switches = list(graph.switches)

    print(f"Installing background/competing traffic ({BACKGROUND_SRC} -> {BACKGROUND_DST}, "
          f"rate-limited to {BACKGROUND_RATE_MBPS} Mbps via OVS QoS)...")

    deploy_and_measure = make_candidate_deploy_and_measure(
        net, graph, target_mbps, RYU_BASE_URL,
        lambda rate: _setup_background_traffic(net, graph, all_switches, rate_mbps=rate),
        BACKGROUND_RATE_MBPS, port=PRIMARY_IPERF_PORT, verbose=True,
    )

    print("\nEvaluating candidate paths under real background contention "
          "(each is deployed for real and measured with iperf3, not estimated):")
    decision = select_bandwidth_path(graph, intent.source, intent.destination, target_mbps, deploy_and_measure)

    print(f"\nSelected path:\n  {' -> '.join(decision.selected_path)}")

    def setup_bg(rate_mbps: float) -> None:
        _setup_background_traffic(net, graph, all_switches, rate_mbps=rate_mbps)

    # --- Final deploy/measure, then (Phase 12) the real closed-loop
    # correction, only if it's initially not satisfied ---
    #
    # Shared with the Phase 13 evaluation harness (backend/pipeline/
    # bandwidth.py) so the demo and the evaluation drive one real
    # implementation, not two. The lever the loop corrects is explained in
    # backend/models/feedback.py's module docstring: a MIN_BANDWIDTH intent
    # is a floor, so the primary flow is never itself throttled -- what a
    # real closed loop CAN deterministically do is throttle the competing
    # background flow down, in bounded/capped steps, freeing real capacity,
    # then take a real new iperf3 measurement and see whether that actually
    # helped. No LLM call happens anywhere in this loop.
    pipeline_result, final_validation, final_rule_validation, final_deployment, final_measurement = (
        run_bandwidth_pipeline(
            net, graph, intent.source, intent.destination, target_mbps, RYU_BASE_URL,
            decision.selected_path, setup_bg, BACKGROUND_RATE_MBPS,
            mode="CLOSED_LOOP", port=PRIMARY_IPERF_PORT, verbose=False,
        )
    )
    achieved = pipeline_result.final_throughput_mbps
    satisfied = pipeline_result.final_satisfied
    reason = pipeline_result.failure_reason or f"measured {achieved} Mbps >= target {target_mbps} Mbps"
    correction_iterations = pipeline_result.correction_iterations
    correction_history = pipeline_result.correction_history
    current_background_rate = pipeline_result.background_rate_changes_mbps[-1]

    print(f"\nValidation:")
    print(f"  {'PASS' if final_validation.valid and final_rule_validation.valid else 'FAIL'}"
          + ("" if final_validation.valid else f" ({'; '.join(final_validation.reasons)})"))
    print("\nDeployment:")
    print(f"  {'SUCCESS' if final_deployment.success else 'FAILED: ' + '; '.join(final_deployment.errors)}")
    print("\nMeasured throughput (final, on selected path, under real background contention):")
    if pipeline_result.initial_throughput_mbps is not None:
        print(f"  initial achieved = {pipeline_result.initial_throughput_mbps} Mbps "
              f"(target {target_mbps} Mbps) -> {'SATISFIED' if pipeline_result.initial_satisfied else 'NOT SATISFIED'}")

    if correction_iterations > 0:
        for entry in correction_history:
            if entry.get("action_taken") is None and "background_rate_before_mbps" not in entry:
                print(f"\nCorrection: {entry['diagnosis']} -- stopping.")
                continue
            print(f"\nCorrection iteration {entry['iteration']}/{MAX_CORRECTION_ITERATIONS}: "
                  f"reconfiguring background traffic {entry['background_rate_before_mbps']} -> "
                  f"{round(entry['background_rate_after_mbps'], 2)} Mbps (real OVS QoS redeploy, not simulated)...")
            print(f"  Re-measured achieved throughput = "
                  f"{entry['measured_mbps_after'] if entry['measured_mbps_after'] is not None else 'unreachable'} Mbps "
                  f"(target {target_mbps} Mbps) -> "
                  f"{'SATISFIED' if entry['satisfied_after'] else 'still NOT SATISFIED'}")
        print(f"\nAfter {correction_iterations} correction iteration(s): "
              f"{'SATISFIED' if satisfied else 'still NOT SATISFIED'} ({reason})")
    elif achieved is not None:
        print(f"  achieved = {achieved} Mbps (sent={final_measurement.sent_mbps}, "
              f"received={final_measurement.received_mbps}, target={target_mbps} Mbps)")
    else:
        print(f"  measurement failed: {final_measurement.error}")

    print(f"\nIntent:\n  {'SATISFIED' if satisfied else 'NOT SATISFIED'} ({reason})")

    if not satisfied:
        feedback = BandwidthFeedback(
            target_mbps=target_mbps,
            measured_mbps=achieved,
            current_path=decision.selected_path,
            candidate_paths=[c.path for c in decision.candidates],
            network_state={
                "candidates": [
                    {"path": c.path, "achieved_mbps": c.throughput.achieved_mbps,
                     "static_capacity_mbps": c.static_capacity_mbps}
                    for c in decision.candidates
                ],
                "background_traffic": {"src": BACKGROUND_SRC, "dst": BACKGROUND_DST,
                                        "rate_limit_mbps": current_background_rate},
                "correction_iterations_used": correction_iterations,
            },
            status="NOT_SATISFIED",
        )
        print("\nFinal feedback object (bounded correction exhausted or not applicable):")
        print(f"  {feedback.model_dump(mode='json')}")

    result_summary = ExperimentLog(
        raw_intent=raw_intent,
        llm_provider=llm.name,
        structured_intent=intent.model_dump(mode="json"),
        candidates=[c.model_dump(mode="json") for c in decision.candidates],
        selected_path=decision.selected_path,
        selected_action=decision.action.value,
        validation_result={"valid": final_validation.valid and final_rule_validation.valid,
                            "reasons": final_validation.reasons + final_rule_validation.reasons},
        deployment_result=final_deployment.model_dump(mode="json"),
        final_measurement=final_measurement.model_dump(mode="json"),
        intent_satisfied=satisfied,
        satisfaction_reason=reason,
        llm_call_count=llm_call_count,
        correction_iterations=correction_iterations,
        background_traffic={"src": BACKGROUND_SRC, "dst": BACKGROUND_DST,
                             "rate_limit_mbps": current_background_rate},
        target_mbps=target_mbps,
        measured_mbps=achieved,
        correction_history=correction_history or None,
    ).model_dump(mode="json")

    return (0 if satisfied else 2), result_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("intent", help='Natural-language network objective, e.g. '
                                        '"Give h1 to h4 the lowest-latency path." or '
                                        '"Provide at least 20 Mbps between h1 and h4."')
    parser.add_argument(
        "--llm-provider",
        default=None,
        help="Override LLM_PROVIDER env var (mock/openai/anthropic/gemini/groq)",
    )
    args = parser.parse_args()
    return run_intent(args.intent, args.llm_provider)


if __name__ == "__main__":
    sys.exit(main())
