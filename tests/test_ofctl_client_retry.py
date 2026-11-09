"""Unit tests for backend/deployment/ofctl_client.py's bounded retry on
transient transport failures (found running the Phase 13 evaluation
harness -- see that module's docstring). These mock urllib.request.urlopen
directly, so no real Ryu server is needed here; the real integration is
exercised by the CLI demo and evaluation harness against the live
testbed."""
from unittest.mock import patch

from backend.deployment.ofctl_client import (
    MAX_TRANSPORT_RETRIES,
    _get_json,
    _post_json,
    _rule_is_present,
)
from backend.models.flow import FlowRule


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_post_json_succeeds_immediately_when_no_transport_error():
    with patch("urllib.request.urlopen", return_value=_FakeResponse(200, b'{"ok": true}')):
        status, body = _post_json("http://127.0.0.1:8080/x", {"a": 1})
    assert status == 200
    assert body == '{"ok": true}'


def test_post_json_retries_on_timeout_then_succeeds():
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("simulated transient stall")
        return _FakeResponse(200, b'{"ok": true}')

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):  # don't actually wait in the test
        status, body = _post_json("http://127.0.0.1:8080/x", {"a": 1})
    assert status == 200
    assert calls["n"] == 2


def test_post_json_gives_up_after_max_retries_and_reports_failure_not_raise():
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("simulated persistent stall")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        status, body = _post_json("http://127.0.0.1:8080/x", {"a": 1})
    assert status == 0
    assert "transport error" in body
    assert f"{MAX_TRANSPORT_RETRIES + 1} attempt" in body


def test_get_json_retries_on_connection_error_then_succeeds():
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("simulated reset")
        return _FakeResponse(200, b'{"1": []}')

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        status, data = _get_json("http://127.0.0.1:8080/stats/flow/1")
    assert status == 200
    assert data == {"1": []}
    assert calls["n"] == 2


def test_get_json_gives_up_after_max_retries_returns_empty_not_raise():
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("simulated persistent stall")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        status, data = _get_json("http://127.0.0.1:8080/stats/flow/1")
    assert status == 0
    assert data == {}


def test_rule_verification_requires_matching_priority_and_output():
    rule = FlowRule(
        dpid=1,
        priority=200,
        match={"eth_type": 0x0800, "ipv4_src": "10.0.0.1"},
        actions=[{"type": "OUTPUT", "port": 3}],
    )
    installed = {
        "priority": 200,
        "match": {"dl_type": 0x0800, "nw_src": "10.0.0.1"},
        "actions": ["OUTPUT:3"],
    }

    assert _rule_is_present(rule, [installed])
    assert not _rule_is_present(
        rule,
        [{**installed, "priority": 100}],
    )
    assert not _rule_is_present(
        rule,
        [{**installed, "actions": ["OUTPUT:4"]}],
    )
    assert not _rule_is_present(
        rule,
        [{**installed, "match": {**installed["match"], "tcp_dst": 443}}],
    )


def test_rule_verification_requires_matching_set_queue_action():
    rule = FlowRule(
        dpid=1,
        priority=100,
        match={"eth_type": 0x0800, "ipv4_src": "10.0.0.2"},
        actions=[
            {"type": "SET_QUEUE", "queue_id": 7},
            {"type": "OUTPUT", "port": 3},
        ],
    )
    installed = {
        "priority": 100,
        "match": {"dl_type": 0x0800, "nw_src": "10.0.0.2"},
        "actions": ["SET_QUEUE:7", "OUTPUT:3"],
    }

    assert _rule_is_present(rule, [installed])
    assert not _rule_is_present(
        rule,
        [{**installed, "actions": ["OUTPUT:3"]}],
    )
    assert not _rule_is_present(
        rule,
        [{**installed, "actions": ["SET_QUEUE:8", "OUTPUT:3"]}],
    )
    assert not _rule_is_present(
        rule,
        [{**installed, "actions": ["OUTPUT:3", "SET_QUEUE:7"]}],
    )
    assert not _rule_is_present(
        rule,
        [{**installed, "actions": ["SET_QUEUE:7", "OUTPUT:3", "GROUP:1"]}],
    )
