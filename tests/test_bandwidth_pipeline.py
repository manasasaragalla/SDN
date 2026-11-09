from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.models.deployment import DeploymentResult
from backend.models.measurement import ThroughputResult
from backend.models.validation import ValidationResult

from backend.pipeline import bandwidth


@pytest.fixture
def setup_pipeline(monkeypatch):
    """Create a mocked environment without Mininet or Ryu."""

    graph = SimpleNamespace(
        hosts={
            "h1": SimpleNamespace(ip="10.0.0.1"),
            "h4": SimpleNamespace(ip="10.0.0.4"),
        },
        switches={"s1": 1},
    )

    net = Mock()
    net.get.side_effect = lambda name: f"mock-{name}"

    path = ["h1", "s1", "h4"]

    # Mock compiled rules.
    rules = [SimpleNamespace(label="test-rule", match={})]

    monkeypatch.setattr(
        bandwidth,
        "compile_reroute",
        Mock(return_value=rules),
    )

    monkeypatch.setattr(
        bandwidth,
        "compile_delete_flows",
        Mock(return_value=rules),
    )

    monkeypatch.setattr(
        bandwidth,
        "delete_flow",
        Mock(return_value=True),
    )

    monkeypatch.setattr(
        bandwidth,
        "validate_path_for_bandwidth",
        Mock(return_value=ValidationResult.ok()),
    )

    monkeypatch.setattr(
        bandwidth,
        "validate_flow_rules",
        Mock(return_value=ValidationResult.ok()),
    )

    monkeypatch.setattr(
        bandwidth,
        "deploy_rules",
        Mock(
            return_value=DeploymentResult(
                requested_count=1,
                accepted_count=1,
                verified_count=1,
                errors=[],
            )
        ),
    )

    monkeypatch.setattr(bandwidth.time, "sleep", Mock())

    setup_traffic = Mock()

    measure = Mock(
        return_value=ThroughputResult(
            succeeded=True,
            received_mbps=8.0,
            raw_output="mock iperf output",
        )
    )

    monkeypatch.setattr(
        bandwidth,
        "measure_throughput",
        measure,
    )

    return SimpleNamespace(
        graph=graph,
        net=net,
        path=path,
        rules=rules,
        setup_traffic=setup_traffic,
        measure=measure,
    )


def run_pipeline(env, mode="CLOSED_LOOP", target=8.0, background_rate=4.0):
    return bandwidth.run_bandwidth_pipeline(
        net=env.net,
        graph=env.graph,
        source="h1",
        destination="h4",
        target_mbps=target,
        base_url="http://127.0.0.1:8080",
        selected_path=env.path,
        setup_background_traffic=env.setup_traffic,
        initial_background_rate_mbps=background_rate,
        mode=mode,
        verbose=False,
    )


def deployment_success():
    return DeploymentResult(
        requested_count=1,
        accepted_count=1,
        verified_count=1,
        errors=[],
    )


def deployment_failure():
    return DeploymentResult(
        requested_count=1,
        accepted_count=0,
        verified_count=0,
        errors=["Mock deployment failure"],
    )


# ---------------------------------------------------------
# 1. Path validation failure
# ---------------------------------------------------------

def test_invalid_path_stops_before_deployment(setup_pipeline):
    env = setup_pipeline

    bandwidth.validate_path_for_bandwidth.return_value = (
        ValidationResult.fail("Invalid path")
    )

    result, path_validation, _, deployment, measurement = run_pipeline(env)

    assert not result.final_satisfied
    assert not path_validation.valid
    assert not deployment.success
    assert not measurement.succeeded

    bandwidth.deploy_rules.assert_not_called()
    env.setup_traffic.assert_not_called()
    env.measure.assert_not_called()


# ---------------------------------------------------------
# 2. Compiled flow-rule validation failure
# ---------------------------------------------------------

def test_invalid_flow_rules_stop_before_deployment(setup_pipeline):
    env = setup_pipeline

    bandwidth.validate_flow_rules.return_value = (
        ValidationResult.fail("Invalid flow rules")
    )

    result, path_validation, rule_validation, deployment, measurement = (
        run_pipeline(env)
    )

    assert path_validation.valid
    assert not rule_validation.valid
    assert not result.final_satisfied
    assert not deployment.success
    assert not measurement.succeeded

    bandwidth.deploy_rules.assert_not_called()
    env.setup_traffic.assert_not_called()
    env.measure.assert_not_called()


# ---------------------------------------------------------
# 3. Initial deployment failure
# ---------------------------------------------------------

def test_initial_deployment_failure_stops_pipeline(setup_pipeline):
    env = setup_pipeline

    bandwidth.deploy_rules.return_value = deployment_failure()

    result, _, _, deployment, measurement = run_pipeline(env)

    assert not deployment.success
    assert not result.final_satisfied
    assert not result.final_deployment_success
    assert not measurement.succeeded

    env.setup_traffic.assert_not_called()
    env.measure.assert_not_called()


# ---------------------------------------------------------
# 4. Initial stale-flow cleanup failure
# ---------------------------------------------------------

def test_initial_cleanup_failure_stops_pipeline(setup_pipeline):
    env = setup_pipeline

    bandwidth.delete_flow.return_value = False

    result, _, _, deployment, measurement = run_pipeline(env)

    assert not result.final_satisfied
    assert not deployment.success
    assert not measurement.succeeded
    assert "cleanup failed" in result.failure_reason.lower()

    bandwidth.deploy_rules.assert_not_called()
    env.setup_traffic.assert_not_called()
    env.measure.assert_not_called()


# ---------------------------------------------------------
# 5. Correction path revalidation failure
# ---------------------------------------------------------

def test_correction_path_validation_failure_stops_loop(setup_pipeline):
    env = setup_pipeline

    bandwidth.validate_path_for_bandwidth.side_effect = [
        ValidationResult.ok(),
        ValidationResult.fail("Correction path invalid"),
    ]

    env.measure.side_effect = [
        ThroughputResult(
            succeeded=True,
            received_mbps=4.0,
            raw_output="initial measurement",
        ),
    ]

    result, path_validation, _, _, measurement = run_pipeline(env)

    assert not result.final_satisfied
    assert not path_validation.valid
    assert result.correction_iterations == 1
    assert not measurement.succeeded

    # Only the initial deployment should happen.
    assert bandwidth.deploy_rules.call_count == 1

    # No second measurement after failed revalidation.
    assert env.measure.call_count == 1


# ---------------------------------------------------------
# 6. Correction deployment failure
# ---------------------------------------------------------

def test_correction_deployment_failure_stops_remeasurement(
    setup_pipeline,
):
    env = setup_pipeline

    bandwidth.deploy_rules.side_effect = [
        deployment_success(),
        deployment_failure(),
    ]

    env.measure.return_value = ThroughputResult(
        succeeded=True,
        received_mbps=4.0,
        raw_output="initial measurement",
    )

    result, _, _, deployment, measurement = run_pipeline(env)

    assert not result.final_satisfied
    assert not deployment.success
    assert not measurement.succeeded
    assert result.correction_iterations == 1

    # Initial measurement only.
    assert env.measure.call_count == 1

    # Background traffic must not change after failed redeployment.
    assert env.setup_traffic.call_count == 1


# ---------------------------------------------------------
# 7. Successful ONE_SHOT execution
# ---------------------------------------------------------

def test_one_shot_success_does_not_run_correction(setup_pipeline):
    env = setup_pipeline

    env.measure.return_value = ThroughputResult(
        succeeded=True,
        received_mbps=9.0,
        raw_output="successful measurement",
    )

    result, path_validation, rule_validation, deployment, measurement = (
        run_pipeline(env, mode="ONE_SHOT")
    )

    assert path_validation.valid
    assert rule_validation.valid
    assert deployment.success
    assert measurement.succeeded

    assert result.initial_satisfied
    assert result.final_satisfied
    assert result.final_throughput_mbps == 9.0
    assert result.correction_iterations == 0

    assert bandwidth.deploy_rules.call_count == 1
    assert env.measure.call_count == 1
    assert env.setup_traffic.call_count == 1


# ---------------------------------------------------------
# 8. Successful CLOSED_LOOP correction
# ---------------------------------------------------------

def test_closed_loop_correction_can_satisfy_target(setup_pipeline):
    env = setup_pipeline

    env.measure.side_effect = [
        ThroughputResult(
            succeeded=True,
            received_mbps=4.0,
            raw_output="initial measurement",
        ),
        ThroughputResult(
            succeeded=True,
            received_mbps=8.0,
            raw_output="corrected measurement",
        ),
    ]

    result, path_validation, rule_validation, deployment, measurement = (
        run_pipeline(env, mode="CLOSED_LOOP")
    )

    assert path_validation.valid
    assert rule_validation.valid
    assert deployment.success
    assert measurement.succeeded

    assert not result.initial_satisfied
    assert result.final_satisfied
    assert result.final_throughput_mbps == 8.0

    assert result.correction_iterations == 1
    assert len(result.correction_history) == 1

    assert result.background_rate_changes_mbps == [4.0, 2.0]

    assert bandwidth.deploy_rules.call_count == 2
    assert env.measure.call_count == 2
    assert env.setup_traffic.call_count == 2