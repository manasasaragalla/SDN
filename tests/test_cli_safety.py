"""Safety checks that must run before the CLI starts network deployment."""

from unittest.mock import Mock

import pytest

from backend import cli
from backend.models.intent import StructuredIntent, TrafficSelector


class _FakeProcess:
    def __init__(self, output=""):
        self.output = output
        self.killed = False

    def poll(self):
        return -9 if self.killed else None

    def kill(self):
        self.killed = True

    def communicate(self, timeout=None):
        assert timeout == 5
        return self.output, None


class _Provider:
    name = "test"

    def __init__(self, intent):
        self.intent = intent

    def parse_intent(self, _raw):
        return self.intent


def test_traffic_selector_is_rejected_before_starting_ryu(monkeypatch):
    intent = StructuredIntent(
        source="h1",
        destination="h4",
        traffic_selector=TrafficSelector(protocol="tcp", dst_port=443),
        constraints={
            "metrics": [
                {
                    "metric": "BANDWIDTH",
                    "unit": "Mbps",
                    "min_value": 10,
                }
            ]
        },
    )
    provider = _Provider(intent)
    start_ryu = Mock()
    monkeypatch.setattr(cli, "_start_ryu", start_ryu)
    monkeypatch.setattr("backend.llm.factory.get_llm_provider", lambda *_: provider)

    assert cli.run_intent("test intent") == 2
    start_ryu.assert_not_called()


def test_start_ryu_waits_long_enough_for_slow_controller_imports(monkeypatch):
    process = _FakeProcess()
    monkeypatch.setattr(cli.subprocess, "Popen", Mock(return_value=process))
    wait_for_port = Mock(return_value=True)
    monkeypatch.setattr(cli, "_wait_for_port", wait_for_port)

    assert cli._start_ryu() is process
    wait_for_port.assert_called_once_with(
        cli.WSAPI_PORT,
        timeout_s=60.0,
    )


def test_start_ryu_includes_controller_output_when_readiness_times_out(monkeypatch):
    process = _FakeProcess("ImportError: simulated Ryu startup failure")
    monkeypatch.setattr(cli.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(cli, "_wait_for_port", Mock(return_value=False))

    with pytest.raises(RuntimeError, match="within 60 seconds") as exc_info:
        cli._start_ryu()

    assert process.killed
    assert "simulated Ryu startup failure" in str(exc_info.value)
