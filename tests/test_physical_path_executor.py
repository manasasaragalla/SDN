import pytest
from pydantic import ValidationError

from backend.deployment import physical_path_executor as executor
from backend.models.deployment import (
    PhysicalCleanupState,
    PhysicalDeploymentResult,
    PhysicalDeploymentState,
)
from backend.models.flow import MAX_COOKIE, FlowRule


def _rules():
    return [
        FlowRule(
            dpid=11,
            priority=100,
            match={
                "in_port": 1,
                "eth_type": 0x0800,
                "ipv4_src": "10.0.0.1",
                "ipv4_dst": "10.0.0.2",
            },
            actions=[{"type": "OUTPUT", "port": 2}],
            label="forward",
        ),
        FlowRule(
            dpid=11,
            priority=100,
            match={
                "in_port": 2,
                "eth_type": 0x0800,
                "ipv4_src": "10.0.0.2",
                "ipv4_dst": "10.0.0.1",
            },
            actions=[{"type": "OUTPUT", "port": 1}],
            label="reverse",
        ),
    ]


def _installed_flow(payload, **overrides):
    match = {
        {"eth_type": "dl_type", "ipv4_src": "nw_src", "ipv4_dst": "nw_dst"}.get(
            key, key
        ): value
        for key, value in payload["match"].items()
    }
    return {
        "cookie": payload["cookie"],
        "priority": payload["priority"],
        "match": match,
        "actions": [
            f"OUTPUT:{action['port']}" for action in payload["actions"]
        ],
        **overrides,
    }


def _install_fake_io(monkeypatch, *, existing=None, on_add=None, on_delete=None):
    executor._OWNED_OPERATIONS.clear()
    flows = {11: list(existing or [])}
    posts = []

    def post(url, payload):
        posts.append((url, payload))
        if url.endswith("/add") and on_add:
            return on_add(payload, flows)
        if url.endswith("/add"):
            flows[payload["dpid"]].append(_installed_flow(payload))
            return 200, "ok"
        if url.endswith("/delete") and on_delete:
            return on_delete(payload, flows)
        if url.endswith("/delete"):
            flows[payload["dpid"]] = [
                flow
                for flow in flows[payload["dpid"]]
                if flow.get("cookie") != payload["cookie"]
            ]
            return 200, "ok"
        raise AssertionError(url)

    def read(dpid, _base_url):
        return 200, flows.get(dpid, []), ""

    monkeypatch.setattr(executor, "_post_flow", post)
    monkeypatch.setattr(executor, "_read_flows", read)
    monkeypatch.setattr(executor.secrets, "randbits", lambda _bits: 0x1234)
    return flows, posts


def test_cookie_is_allocated_and_owned_by_every_installed_rule(monkeypatch):
    flows, posts = _install_fake_io(monkeypatch)

    result = executor.deploy_physical_path_rules(_rules())

    assert result.success
    assert result.operation_cookie == 0x1234
    assert result.dpids == (11,)
    assert result.accepted_count == 2
    assert result.verified_count == 2
    add_payloads = [payload for url, payload in posts if url.endswith("/add")]
    assert [payload["cookie"] for payload in add_payloads] == [0x1234, 0x1234]
    assert [flow["cookie"] for flow in flows[11]] == [0x1234, 0x1234]


def test_legacy_flow_rule_payload_omits_unassigned_cookie():
    assert "cookie" not in _rules()[0].to_ofctl_payload()


def test_cookie_model_rejects_booleans_and_out_of_range_values():
    for cookie in (True, False, -1, MAX_COOKIE + 1):
        with pytest.raises(ValidationError):
            FlowRule(
                dpid=1,
                match={},
                actions=[],
                cookie=cookie,
            )


def test_wrong_cookie_or_wrong_rule_readback_is_not_verified(monkeypatch):
    for mismatch in (
        {"cookie": 0x9999},
        {"priority": 99},
        {"match": {"dl_type": 0x0800}},
        {"actions": ["OUTPUT:99"]},
    ):
        flows, _ = _install_fake_io(
            monkeypatch,
            on_add=lambda payload, state, mismatch=mismatch: (
                state[payload["dpid"]].append(
                    _installed_flow(payload, **mismatch)
                )
                or (200, "ok")
            ),
        )

        result = executor.deploy_physical_path_rules(_rules())

        assert result.state == PhysicalDeploymentState.FAILED
        assert result.verified_count == 0
        flows[11].clear()


def test_partial_installation_is_reported(monkeypatch):
    calls = {"count": 0}

    def install_only_first(payload, flows):
        calls["count"] += 1
        if calls["count"] == 1:
            flows[payload["dpid"]].append(_installed_flow(payload))
        return 200, "ok"

    _install_fake_io(monkeypatch, on_add=install_only_first)
    result = executor.deploy_physical_path_rules(_rules())

    assert result.state == PhysicalDeploymentState.PARTIAL
    assert result.verified_count == 1
    assert not result.success


def test_ambiguous_timeout_is_reconciled_without_reposting(monkeypatch):
    def accepted_but_timed_out(payload, flows):
        flows[payload["dpid"]].append(_installed_flow(payload))
        return 0, "transport timeout"

    _, posts = _install_fake_io(monkeypatch, on_add=accepted_but_timed_out)
    result = executor.deploy_physical_path_rules(_rules())

    assert result.state == PhysicalDeploymentState.SUCCEEDED
    assert result.reconciled_count == 2
    assert result.verified_count == 2
    assert len([url for url, _ in posts if url.endswith("/add")]) == 2


def test_ambiguous_timeout_without_readback_remains_uncertain(monkeypatch):
    _, posts = _install_fake_io(
        monkeypatch, on_add=lambda _payload, _flows: (0, "transport timeout")
    )
    result = executor.deploy_physical_path_rules(_rules())

    assert result.state == PhysicalDeploymentState.UNCERTAIN
    assert result.verified_count == 0
    assert len([url for url, _ in posts if url.endswith("/add")]) == 2


def test_existing_cookie_collision_is_skipped(monkeypatch):
    flows, _ = _install_fake_io(
        monkeypatch,
        existing=[{"cookie": 0x1234}],
    )
    candidates = iter((0x1234, 0x5678))
    monkeypatch.setattr(executor.secrets, "randbits", lambda _bits: next(candidates))

    result = executor.deploy_physical_path_rules(_rules())

    assert result.success
    assert result.operation_cookie == 0x5678
    assert flows[11][0]["cookie"] == 0x1234


def test_cleanup_deletes_only_operation_cookie_and_verifies_absence(monkeypatch):
    foreign = {
        "cookie": 0x9999,
        "priority": 1,
        "match": {},
        "actions": [],
    }
    flows, _ = _install_fake_io(monkeypatch, existing=[foreign])
    deployment = executor.deploy_physical_path_rules(_rules())

    cleanup = executor.cleanup_physical_path_deployment(deployment)

    assert cleanup.success
    assert cleanup.state == PhysicalCleanupState.SUCCEEDED
    assert cleanup.accepted_delete_count == 1
    assert cleanup.remaining_flow_count == 0
    assert flows[11] == [foreign]


def test_cleanup_failure_is_reported_and_foreign_flows_survive(monkeypatch):
    foreign = {
        "cookie": 0x9999,
        "priority": 1,
        "match": {},
        "actions": [],
    }
    flows, _ = _install_fake_io(monkeypatch, existing=[foreign])
    deployment = executor.deploy_physical_path_rules(_rules())
    target_cookie = deployment.operation_cookie

    def failed_delete(_payload, _flows):
        return 500, "delete rejected"

    monkeypatch.setattr(
        executor,
        "_post_flow",
        lambda url, payload: (
            failed_delete(payload, flows)
            if url.endswith("/delete")
            else (200, "ok")
        ),
    )
    cleanup = executor.cleanup_physical_path_deployment(deployment)

    assert cleanup.state == PhysicalCleanupState.FAILED
    assert cleanup.remaining_flow_count == 2
    assert {flow["cookie"] for flow in flows[11]} == {foreign["cookie"], target_cookie}


def test_cookie_scoped_delete_payload_uses_full_mask_and_recorded_dpids(monkeypatch):
    _, posts = _install_fake_io(monkeypatch)
    deployment = executor.deploy_physical_path_rules(_rules())
    posts.clear()

    executor.cleanup_physical_path_deployment(deployment)

    delete_url, payload = posts[0]
    assert delete_url.endswith("/flowentry/delete")
    assert payload == {
        "dpid": 11,
        "cookie": deployment.operation_cookie,
        "cookie_mask": MAX_COOKIE,
        "table_id": "ALL",
    }


def test_failed_flow_readback_is_reported_as_uncertain(monkeypatch):
    _install_fake_io(monkeypatch)
    reads = {"count": 0}

    def fail_verification(dpid, _base_url):
        reads["count"] += 1
        if reads["count"] == 2:
            return 0, [], "timeout"
        return 200, [], ""

    monkeypatch.setattr(executor, "_read_flows", fail_verification)
    result = executor.deploy_physical_path_rules(_rules())

    assert result.state == PhysicalDeploymentState.UNCERTAIN
    assert result.verified_count == 0
    assert result.errors


def test_preflight_read_failure_allocates_no_owned_cookie_or_writes(monkeypatch):
    _, posts = _install_fake_io(monkeypatch)
    monkeypatch.setattr(
        executor,
        "_read_flows",
        lambda _dpid, _base_url: (0, [], "timeout"),
    )

    result = executor.deploy_physical_path_rules(_rules())

    assert result.state == PhysicalDeploymentState.FAILED
    assert result.operation_cookie is None
    assert result.accepted_count == 0
    assert posts == []
    with pytest.raises(ValueError, match="active operation"):
        executor.cleanup_physical_path_deployment(result)


def test_cleanup_rejects_unregistered_foreign_cookie(monkeypatch):
    _install_fake_io(monkeypatch)
    forged = PhysicalDeploymentResult(
        operation_cookie=0x9999,
        dpids=(11,),
        requested_count=1,
        accepted_count=1,
        verified_count=1,
        state=PhysicalDeploymentState.SUCCEEDED,
    )

    with pytest.raises(ValueError, match="active operation"):
        executor.cleanup_physical_path_deployment(forged)
