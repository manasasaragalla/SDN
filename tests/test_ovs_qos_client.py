"""Regression tests for project-scoped OVS QoS cleanup."""

from backend.deployment import ovs_qos_client
from backend.models.qos import QueueConfig


PROJECT_OWNER = ovs_qos_client.PROJECT_OWNER
QOS_UUID = "11111111-1111-1111-1111-111111111111"
QUEUE_UUID = "22222222-2222-2222-2222-222222222222"


def test_clear_queue_only_removes_owned_rows_for_the_target_port(monkeypatch):
    results = iter(
        [
            (0, QOS_UUID, ""),
            (0, PROJECT_OWNER, ""),
            (0, f"{{0={QUEUE_UUID}}}", ""),
            (0, PROJECT_OWNER, ""),
            (0, "", ""),
        ]
    )
    calls = []

    def fake_run(args):
        calls.append(args)
        return next(results)

    monkeypatch.setattr(ovs_qos_client, "_run", fake_run)
    queue = QueueConfig(
        switch="s2",
        intf="s2-eth2",
        queue_id=0,
        max_rate_bps=8_000_000,
    )

    assert ovs_qos_client.clear_queue(queue)
    assert calls == [
        ["get", "port", "s2-eth2", "qos"],
        ["get", "qos", QOS_UUID, "external_ids:owner"],
        ["get", "qos", QOS_UUID, "queues"],
        ["get", "queue", QUEUE_UUID, "external_ids:owner"],
        [
            "clear", "port", "s2-eth2", "qos",
            "--",
            "destroy", "qos", QOS_UUID,
            "--",
            "destroy", "queue", QUEUE_UUID,
        ],
    ]
    assert not any("--all" in args for args in calls)


def test_clear_queue_preserves_unowned_qos_and_queues(monkeypatch):
    calls = []
    results = iter(
        [
            (0, QOS_UUID, ""),
            (0, "another-owner", ""),
        ]
    )

    def fake_run(args):
        calls.append(args)
        return next(results)

    monkeypatch.setattr(ovs_qos_client, "_run", fake_run)
    queue = QueueConfig(
        switch="s2",
        intf="s2-eth2",
        queue_id=0,
        max_rate_bps=8_000_000,
    )

    assert not ovs_qos_client.clear_queue(queue)
    assert calls == [
        ["get", "port", "s2-eth2", "qos"],
        ["get", "qos", QOS_UUID, "external_ids:owner"],
    ]


def test_clear_queue_refuses_project_qos_referencing_unowned_queue(monkeypatch):
    results = iter(
        [
            (0, QOS_UUID, ""),
            (0, PROJECT_OWNER, ""),
            (0, f"{{0={QUEUE_UUID}}}", ""),
            (0, "another-owner", ""),
        ]
    )
    calls = []

    def fake_run(args):
        calls.append(args)
        return next(results)

    monkeypatch.setattr(ovs_qos_client, "_run", fake_run)
    queue = QueueConfig(
        switch="s2",
        intf="s2-eth2",
        queue_id=0,
        max_rate_bps=8_000_000,
    )

    assert not ovs_qos_client.clear_queue(queue)
    assert not any("destroy" in args for args in calls)
    assert not any("clear" in args for args in calls)


def test_deploy_queue_marks_created_resources_as_project_owned(monkeypatch):
    monkeypatch.setattr(ovs_qos_client, "clear_queue", lambda queue: True)
    calls = []
    results = iter(
        [
            (0, "", ""),
            (0, QOS_UUID, ""),
        ]
    )

    def fake_run(args):
        calls.append(args)
        return next(results)

    monkeypatch.setattr(ovs_qos_client, "_run", fake_run)
    queue = QueueConfig(
        switch="s2",
        intf="s2-eth2",
        queue_id=0,
        max_rate_bps=8_000_000,
    )

    assert ovs_qos_client.deploy_queue(queue)
    create_args = calls[0]
    assert create_args.count(f"external_ids:owner={PROJECT_OWNER}") == 2


def test_deploy_queue_does_not_replace_unowned_qos(monkeypatch):
    run = lambda _args: (_ for _ in ()).throw(AssertionError("must not run"))
    monkeypatch.setattr(ovs_qos_client, "clear_queue", lambda queue: False)
    monkeypatch.setattr(ovs_qos_client, "_run", run)
    queue = QueueConfig(
        switch="s2",
        intf="s2-eth2",
        queue_id=0,
        max_rate_bps=8_000_000,
    )

    assert not ovs_qos_client.deploy_queue(queue)
