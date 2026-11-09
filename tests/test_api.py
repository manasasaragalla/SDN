from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import threading
import json
import stat
import subprocess
import sys
import time
import uuid

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.api.main import create_app
from backend.api.auth import APIAccessControl, SESSION_TTL_SECONDS
from backend.api.schemas import WorkerRequest, WorkerResponse
from backend.api.services.worker_client import (
    WorkerUnavailableError,
    call_worker,
)
from backend.api.worker import (
    _acquire_worker_lock,
    _loopback_listener_addresses,
    _remove_stale_socket,
    _ryu_command,
    _serve_connection,
    _unlink_owned_socket,
    serve,
)
from backend.api import worker as worker_module
from backend.orchestration import latency_evidence
from backend.api.services import evidence
from backend.execution.models import PortOperationalState, SnapshotStatus, TopologySnapshot
from backend.llm.mock import MockLLM
from backend.llm.gemini_provider import GeminiLLM
from backend.models.canonical_intent import CanonicalIntent, OptimizationDirection, OptimizationObjective, TrafficScope
from backend.models.network import Host, Link, TopologyGraph

TEST_API_TOKEN = "test-api-token-for-api-access-regression-tests-012345"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_TOKEN}"}


@pytest.fixture(autouse=True)
def prevent_external_llm_calls(monkeypatch):
    monkeypatch.setattr("backend.api.main.get_llm_provider", lambda: MockLLM())


@pytest.fixture(autouse=True)
def isolate_topology_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "INTENTFLOW_TOPOLOGY_DB",
        str(tmp_path / "topologies.sqlite3"),
    )


@pytest.fixture
def live_topology_payload() -> dict:
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": Host(name="h1", ip="10.0.0.1", mac="00:00:00:00:00:01", switch="s1", switch_port=1),
            "h4": Host(name="h4", ip="10.0.0.4", mac="00:00:00:00:00:04", switch="s2", switch_port=2),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1, bw_mbps=10.0),
        ],
    )
    ports = [
        PortOperationalState(dpid=1, port_no=1, present=True, admin_up=True, link_up=True),
        PortOperationalState(dpid=1, port_no=2, present=True, admin_up=True, link_up=True),
        PortOperationalState(dpid=2, port_no=1, present=True, admin_up=True, link_up=True),
        PortOperationalState(dpid=2, port_no=2, present=True, admin_up=True, link_up=True),
    ]
    snapshot = TopologySnapshot(
        configured_topology=graph,
        captured_at=datetime.now(timezone.utc),
        status=SnapshotStatus.COMPLETE,
        connected_switch_dpids=(1, 2),
        port_states=tuple(ports),
    )
    return {
        "graph": graph.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
        "topology_fingerprint": snapshot.topology_fingerprint,
    }


def _client(worker_fn, topology_payload) -> TestClient:
    def fake_worker(operation: str, **kwargs):
        if operation == "health":
            return {"ready": True, "operation_busy": False}
        if operation == "topology":
            return topology_payload
        if operation == "execute":
            return {
                "execution_id": kwargs["execution_id"],
                "execution_status": "SUCCEEDED",
            }
        return worker_fn(operation, **kwargs)

    return TestClient(
        create_app(
            worker_call_fn=fake_worker,
            enforce_unprivileged=False,
            api_token=TEST_API_TOKEN,
        ),
        headers=AUTH_HEADERS,
    )


def test_health_reports_unknown_mininet_without_starting_it(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mininet_status"] == "UNKNOWN"


def test_development_auth_bypass_allows_local_api_without_credentials(
    monkeypatch,
    live_topology_payload,
):
    monkeypatch.setenv("INTENTFLOW_AUTH_DISABLED", "true")
    monkeypatch.setenv("INTENTFLOW_ENVIRONMENT", "development")
    monkeypatch.setenv("INTENTFLOW_API_HOST", "127.0.0.1")

    def worker(operation: str, **kwargs):
        if operation == "health":
            return {"ready": True, "operation_busy": False}
        if operation == "topology":
            return live_topology_payload
        if operation == "execute":
            return {
                "execution_id": kwargs["execution_id"],
                "execution_status": "SUCCEEDED",
            }
        return {}

    with TestClient(create_app(
        worker_call_fn=worker,
        enforce_unprivileged=False,
    )) as client:
        health = client.get("/api/v1/health")
        topology = client.get("/api/v1/topology")
        preview = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
            },
        )
        history = client.get("/api/v1/executions")
        session = client.post("/api/v1/auth/session")
        accepted = client.post(
            "/api/v1/executions",
            json={"preview_id": preview.json()["preview_id"]},
        )
        execution_id = accepted.json()["execution_id"]
        status = client.get(
            f"/api/v1/executions/{execution_id}/status",
        )
        for _ in range(20):
            if status.json()["status"] != "RUNNING":
                break
            time.sleep(0.01)
            status = client.get(
                f"/api/v1/executions/{execution_id}/status",
            )

    assert health.status_code == 200
    assert topology.status_code == 200
    assert preview.status_code == 200
    assert history.status_code == 200
    assert session.status_code == 200
    assert session.json() == {"authenticated": False, "expires_in": 0}
    assert "intentflow_session=" not in session.headers.get("set-cookie", "")
    assert accepted.status_code == 202
    assert status.status_code == 200
    assert status.json()["execution_id"] == execution_id
    assert status.json()["status"] == "SUCCEEDED"
    assert status.json()["events"][-1]["event"] == "EXECUTION_SUCCEEDED"


def test_auth_bypass_requires_explicit_development_environment(monkeypatch):
    monkeypatch.setenv("INTENTFLOW_AUTH_DISABLED", "true")
    monkeypatch.setenv("INTENTFLOW_ENVIRONMENT", "production")
    monkeypatch.setenv("INTENTFLOW_API_HOST", "127.0.0.1")

    with pytest.raises(RuntimeError, match="only when INTENTFLOW_ENVIRONMENT=development"):
        create_app(enforce_unprivileged=False)


def test_auth_bypass_rejects_non_loopback_bind(monkeypatch):
    monkeypatch.setenv("INTENTFLOW_AUTH_DISABLED", "true")
    monkeypatch.setenv("INTENTFLOW_ENVIRONMENT", "development")
    monkeypatch.setenv("INTENTFLOW_API_HOST", "0.0.0.0")

    with pytest.raises(RuntimeError, match="requires INTENTFLOW_API_HOST"):
        create_app(enforce_unprivileged=False)


def test_invalid_auth_bypass_setting_fails_closed(monkeypatch):
    monkeypatch.setenv("INTENTFLOW_AUTH_DISABLED", "yes")
    monkeypatch.setenv("INTENTFLOW_ENVIRONMENT", "development")

    with pytest.raises(RuntimeError, match="must be true or false"):
        create_app(enforce_unprivileged=False)


def test_topology_uses_worker_inventory_and_port_snapshot(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.get("/api/v1/topology")
    assert response.status_code == 200
    body = response.json()
    assert [switch["name"] for switch in body["switches"]] == ["s1", "s2"]
    assert body["hosts"][0]["ip"] == "10.0.0.1"
    assert any(link["capacity_mbps"] == 10.0 for link in body["links"])
    assert all(link["status"] == "CONNECTED" for link in body["links"])


def test_preview_marks_mock_parser_and_reports_capability(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["parser_kind"] == "MOCK"
    assert body["canonical_intent"]["optimization"]["metric"] == "latency"
    assert any("mock parser" in message.lower() for message in body["explanation"])
    assert body["topology_status"] == "CONNECTED"


@pytest.mark.parametrize(
    ("natural_language", "expected_constraint", "expected_optimization"),
    [
        (
            "Find a path from h1 to h4 with bandwidth greater than 20 Mbps.",
            {"metric": "bandwidth", "comparison": "GT", "value": 20.0},
            None,
        ),
        (
            "Find the lowest-latency path from h1 to h4.",
            None,
            {"metric": "latency", "direction": "MINIMIZE"},
        ),
        (
            "Minimize latency between h1 and h4 while maintaining bandwidth above 20 Mbps.",
            {"metric": "bandwidth", "comparison": "GT", "value": 20.0},
            {"metric": "latency", "direction": "MINIMIZE"},
        ),
        (
            "Find a path from h1 to h4 with bandwidth above 1000 Mbps.",
            {"metric": "bandwidth", "comparison": "GT", "value": 1000.0},
            None,
        ),
    ],
)
def test_preview_preserves_end_to_end_acceptance_intents(
    live_topology_payload,
    natural_language,
    expected_constraint,
    expected_optimization,
):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": natural_language,
                "source": "h1",
                "destination": "h4",
            },
        )

    assert response.status_code == 200
    canonical = response.json()["canonical_intent"]
    assert canonical["scope"]["source"] == "h1"
    assert canonical["scope"]["destination"] == "h4"
    if expected_constraint is None:
        assert canonical["constraints"] == []
    else:
        assert len(canonical["constraints"]) == 1
        actual = canonical["constraints"][0]
        for field, value in expected_constraint.items():
            assert actual[field] == value
    if expected_optimization is None:
        assert canonical["optimization"] is None
    else:
        assert canonical["optimization"]["metric"] == expected_optimization["metric"]
        assert canonical["optimization"]["direction"] == expected_optimization["direction"]


def test_preview_rejects_mismatched_host_selectors(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h2",
                "destination": "h4",
            },
        )
    assert response.status_code == 422


def test_preview_uses_selected_host_scope_when_text_omits_hosts(
    live_topology_payload,
):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Ensure bandwidth is at least 20 Mbps.",
                "source": "h1",
                "destination": "h4",
            },
        )

    assert response.status_code == 200
    canonical = response.json()["canonical_intent"]
    assert canonical["scope"]["source"] == "h1"
    assert canonical["scope"]["destination"] == "h4"
    assert canonical["constraints"][0]["comparison"] == "GTE"
    assert canonical["constraints"][0]["value"] == 20


def test_preview_preserves_both_constraints_from_reported_request(
    live_topology_payload,
):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": (
                    "Find a path from h1 to h4 with bandwidth at least 20 Mbps "
                    "and latency below 50 ms."
                ),
                "source": "h1",
                "destination": "h4",
            },
        )

    assert response.status_code == 200
    canonical = response.json()["canonical_intent"]
    assert [
        (item["metric"], item["comparison"], item["value"])
        for item in canonical["constraints"]
    ] == [
        ("bandwidth", "GTE", 20),
        ("latency", "LT", 50),
    ]


def test_preview_reports_gemini_unavailable_as_service_error(
    monkeypatch,
    live_topology_payload,
):
    import io
    import json
    import urllib.error

    monkeypatch.setattr(
        "backend.api.main.get_llm_provider",
        lambda: GeminiLLM(api_key="test-key"),
    )
    error = urllib.error.HTTPError(
        "https://generativelanguage.googleapis.com/test",
        503,
        "Service Unavailable",
        hdrs=None,
        fp=io.BytesIO(
            json.dumps(
                {"error": {"message": "The model is overloaded."}}
            ).encode()
        ),
    )
    def raise_provider_error(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("urllib.request.urlopen", raise_provider_error)

    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Find a path from h1 to h4.",
                "source": "h1",
                "destination": "h4",
            },
        )

    assert response.status_code == 503
    assert "Gemini API returned HTTP 503" in response.json()["detail"]
    assert "model is overloaded" in response.json()["detail"]


def test_preview_rejects_unexpected_request_fields(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
                "command": "id",
            },
        )
    assert response.status_code == 422


def test_unauthorized_requests_cannot_reach_worker(live_topology_payload):
    worker_operations = []

    def worker(operation: str, **_kwargs):
        worker_operations.append(operation)
        return live_topology_payload

    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    with TestClient(
        create_app(
            worker_call_fn=worker,
            enforce_unprivileged=False,
            api_token=TEST_API_TOKEN,
        )
    ) as client:
        responses = [
            client.get("/api/v1/health"),
            client.get("/api/v1/topology"),
            client.post(
                "/api/v1/intents/preview",
                json={
                    "natural_language": "Minimize latency between h1 and h4.",
                    "source": "h1",
                    "destination": "h4",
                },
            ),
            client.post("/api/v1/auth/session"),
            client.post(
                "/api/v1/executions",
                json={"canonical_intent": intent.model_dump(mode="json")},
            ),
            client.get(
                "/api/v1/executions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/status"
            ),
            client.get("/api/v1/executions"),
        ]
    assert [response.status_code for response in responses] == [401] * 7
    assert worker_operations == []


def test_api_token_creates_cookie_session_and_rejects_bad_token():
    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN)
    ) as client:
        unauthorized = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer incorrect-token"},
        )
        login = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
        health = client.get("/api/v1/health")
    assert unauthorized.status_code == 401
    assert login.status_code == 200
    assert login.json()["authenticated"] is True
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "samesite=strict" in login.headers["set-cookie"].lower()
    assert health.status_code == 200


def test_secure_cookie_is_enabled_only_by_explicit_https_setting(monkeypatch):
    monkeypatch.setenv("INTENTFLOW_COOKIE_SECURE", "true")
    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN)
    ) as client:
        login = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
        set_cookie = login.headers["set-cookie"].lower()
    assert login.status_code == 200
    assert "secure" in set_cookie

    monkeypatch.setenv("INTENTFLOW_COOKIE_SECURE", "false")
    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN)
    ) as client:
        login = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
    assert "secure=" not in login.headers["set-cookie"].lower()


def test_session_expiration_and_revocation(monkeypatch):
    access_control = APIAccessControl(TEST_API_TOKEN)
    now = {"value": 100.0}
    monkeypatch.setattr("backend.api.auth.time.monotonic", lambda: now["value"])
    session_id = access_control.create_session()
    assert access_control.accepts_session(session_id) is True
    now["value"] += SESSION_TTL_SECONDS
    assert access_control.accepts_session(session_id) is False

    live_session = access_control.create_session()
    access_control.revoke_session(live_session)
    assert access_control.accepts_session(live_session) is False


def test_logout_revokes_cookie_session():
    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN)
    ) as client:
        login = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
        assert login.status_code == 200
        logout = client.delete(
            "/api/v1/auth/session",
            headers={"Origin": "http://localhost:3000"},
        )
        health = client.get("/api/v1/health")
    assert logout.status_code == 200
    assert logout.json() == {"authenticated": False}
    assert health.status_code == 401


def test_unauthorized_websocket_connection_is_closed():
    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN)
    ) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/v1/executions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/events",
                headers={"Origin": "http://localhost:3000"},
            ):
                pass
    assert exc_info.value.code == 4401


def test_cookie_authenticated_writes_require_allowed_origin():
    worker_operations = []

    def worker(operation: str, **_kwargs):
        worker_operations.append(operation)
        return {"ready": True, "operation_busy": False}

    with TestClient(
        create_app(
            worker_call_fn=worker,
            enforce_unprivileged=False,
            api_token=TEST_API_TOKEN,
        )
    ) as client:
        login = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
        )
        assert login.status_code == 200
        response = client.post(
            "/api/v1/intents/preview",
            headers={"Origin": "https://attacker.invalid"},
            json={
                "natural_language": "Minimize latency between h1 and h4.",
                "source": "h1",
                "destination": "h4",
            },
        )
    assert response.status_code == 403
    assert worker_operations == []


def test_api_refuses_to_start_without_a_strong_token():
    with pytest.raises(RuntimeError, match="INTENTFLOW_API_TOKEN"):
        with TestClient(
            create_app(enforce_unprivileged=False, api_token="short")
        ):
            pass


def test_cors_allows_credentials_only_for_configured_origins():
    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN)
    ) as client:
        response = client.options(
            "/api/v1/executions",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_execution_returns_stable_id_and_terminal_websocket_events(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        preview = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
            },
        )
        assert preview.status_code == 200
        accepted = client.post(
            "/api/v1/executions",
            json={"preview_id": preview.json()["preview_id"]},
        )
        assert accepted.status_code == 202
        assert client.post("/api/v1/auth/session").status_code == 200
        execution_id = accepted.json()["execution_id"]
        assert len(execution_id) == 32
        with client.websocket_connect(
            f"/api/v1/executions/{execution_id}/events",
            headers={"Origin": "http://localhost:3000"},
        ) as websocket:
            events = [websocket.receive_json() for _ in range(3)]
    assert all(event["execution_id"] == execution_id for event in events)
    assert [event["event"] for event in events] == [
        "EXECUTION_ACCEPTED",
        "EXECUTION_RUNNING",
        "EXECUTION_SUCCEEDED",
    ]


def test_execution_rejects_reuse_of_preview(live_topology_payload):
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        preview = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
            },
        ).json()
        payload = {"preview_id": preview["preview_id"]}
        assert client.post("/api/v1/executions", json=payload).status_code == 202
        response = client.post("/api/v1/executions", json=payload)
    assert response.status_code == 410


def test_execution_rejects_a_second_live_operation(live_topology_payload):
    started = threading.Event()
    release = threading.Event()

    def worker(operation: str, **kwargs):
        if operation == "health":
            return {"ready": True}
        if operation == "topology":
            return live_topology_payload
        if operation == "execute":
            started.set()
            release.wait(timeout=5)
            return {
                "execution_id": kwargs["execution_id"],
                "execution_status": "SUCCEEDED",
            }
        raise AssertionError(f"Unexpected worker operation: {operation}")

    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    with TestClient(
        create_app(
            worker_call_fn=worker,
            enforce_unprivileged=False,
            api_token=TEST_API_TOKEN,
        ),
        headers=AUTH_HEADERS,
    ) as client:
        first = client.post(
            "/api/v1/executions",
            json={"canonical_intent": intent.model_dump(mode="json")},
        )
        assert first.status_code == 202
        assert started.wait(timeout=2)
        second = client.post(
            "/api/v1/executions",
            json={"canonical_intent": intent.model_dump(mode="json")},
        )
        release.set()
    assert second.status_code == 409


def test_direct_canonical_execution_rejects_unsupported_intent(live_topology_payload):
    operations = []

    def worker(operation: str, **_kwargs):
        operations.append(operation)
        if operation == "topology":
            return live_topology_payload
        if operation == "health":
            return {"ready": True, "operation_busy": False}
        raise AssertionError("Unsupported intent reached worker execution.")

    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        optimization=OptimizationObjective(
            metric="unregistered_metric",
            direction=OptimizationDirection.MINIMIZE,
            unit="units",
        ),
    )
    with TestClient(
        create_app(
            worker_call_fn=worker,
            enforce_unprivileged=False,
            api_token=TEST_API_TOKEN,
        ),
        headers=AUTH_HEADERS,
    ) as client:
        response = client.post(
            "/api/v1/executions",
            json={"canonical_intent": intent.model_dump(mode="json")},
        )
    assert response.status_code == 422
    assert "not eligible" in response.json()["detail"]
    assert "execute" not in operations


def test_incomplete_topology_is_reported_as_unknown_and_blocks_preview(
    live_topology_payload,
):
    snapshot = TopologySnapshot.model_validate(live_topology_payload["snapshot"])
    incomplete = TopologySnapshot(
        configured_topology=snapshot.configured_topology,
        captured_at=snapshot.captured_at,
        status=SnapshotStatus.INCOMPLETE,
        connected_switch_dpids=snapshot.connected_switch_dpids,
        port_states=snapshot.port_states[:-1],
    )
    payload = {
        **live_topology_payload,
        "snapshot": incomplete.model_dump(mode="json"),
    }
    with _client(lambda *_args, **_kwargs: {}, payload) as client:
        topology_response = client.get("/api/v1/topology")
        preview = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
            },
        )
    assert topology_response.status_code == 200
    assert topology_response.json()["snapshot_status"] == "INCOMPLETE"
    assert preview.status_code == 200
    assert preview.json()["topology_status"] == "UNKNOWN"
    assert preview.json()["execution_eligible"] is False


def test_topology_rejects_inconsistent_snapshot_fingerprint(live_topology_payload):
    payload = {**live_topology_payload, "topology_fingerprint": "incorrect"}
    with _client(lambda *_args, **_kwargs: {}, payload) as client:
        response = client.get("/api/v1/topology")
    assert response.status_code == 502


def test_execution_list_contains_only_persisted_evidence(
    live_topology_payload,
    monkeypatch,
    tmp_path,
):
    results = tmp_path / "results"
    reports = tmp_path / "reports"
    results.mkdir()
    reports.mkdir()
    monkeypatch.setattr(evidence, "JSON_OUTPUT_DIR", results)
    monkeypatch.setattr(evidence, "MARKDOWN_OUTPUT_DIR", reports)
    with _client(lambda *_args, **_kwargs: {}, live_topology_payload) as client:
        preview = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": "Give h1 to h4 the lowest-latency path.",
                "source": "h1",
                "destination": "h4",
            },
        )
        accepted = client.post(
            "/api/v1/executions",
            json={"preview_id": preview.json()["preview_id"]},
        )
        history = client.get("/api/v1/executions")
    assert accepted.status_code == 202
    assert history.status_code == 200
    assert history.json() == []


def test_history_reads_only_allowlisted_persisted_evidence(monkeypatch, tmp_path):
    results = tmp_path / "results"
    reports = tmp_path / "reports"
    results.mkdir()
    reports.mkdir()
    monkeypatch.setattr(evidence, "JSON_OUTPUT_DIR", results)
    monkeypatch.setattr(evidence, "MARKDOWN_OUTPUT_DIR", reports)
    execution_id = "a" * 32
    data = {
        "execution_id": execution_id,
        "execution_status": "SUCCEEDED",
        "started_at": "2026-01-02T03:04:05+00:00",
        "completed_at": "2026-01-02T03:04:06+00:00",
        "request": {"source": "h1", "destination": "h4"},
        "final": {
            "selected_path": {"nodes": ["h1", "s1", "h4"]},
            "connectivity": {"measurement": {"rtt_avg_ms": 2.5}},
        },
    }
    (results / f"generalized_constraints_{execution_id}.json").write_text(
        json.dumps(data),
        encoding="utf-8",
    )
    (reports / f"generalized_constraints_{execution_id}.md").write_text(
        "evidence",
        encoding="utf-8",
    )

    summaries = evidence.list_executions()
    detail = evidence.get_execution(execution_id)
    assert summaries[0].status == "SUCCEEDED"
    assert summaries[0].selected_path == ["h1", "s1", "h4"]
    assert summaries[0].evidence_markdown == f"generalized_constraints_{execution_id}.md"
    assert detail.evidence == data


def test_worker_evidence_permissions_are_api_readable(monkeypatch, tmp_path):
    state_root = tmp_path / "var" / "lib" / "intentflow"
    stored_results = state_root / "results"
    stored_reports = state_root / "reports"
    stored_results.mkdir(parents=True)
    stored_reports.mkdir(parents=True)
    stored_results.chmod(0o2750)
    stored_reports.chmod(0o2750)
    monkeypatch.setattr(latency_evidence, "JSON_OUTPUT_DIR", stored_results)
    monkeypatch.setattr(latency_evidence, "MARKDOWN_OUTPUT_DIR", stored_reports)
    monkeypatch.setattr(evidence, "JSON_OUTPUT_DIR", stored_results)
    monkeypatch.setattr(evidence, "MARKDOWN_OUTPUT_DIR", stored_reports)
    monkeypatch.setenv("INTENTFLOW_EVIDENCE_GID", str(os.getegid()))
    link = os.link
    staged_modes = []

    def verify_before_publish(source, destination, **kwargs):
        info = Path(source).stat()
        assert stat.S_IMODE(info.st_mode) == 0o640
        assert info.st_uid == os.geteuid()
        assert info.st_gid == os.getegid()
        staged_modes.append(Path(destination).name)
        link(source, destination, **kwargs)

    monkeypatch.setattr(latency_evidence.os, "link", verify_before_publish)

    execution_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc)
    json_path, markdown_path = latency_evidence.persist_latency_execution(
        None,
        execution_id=execution_id,
        started_at=started_at,
        completed_at=started_at,
    )

    assert len(staged_modes) == 2
    for path in (json_path, markdown_path):
        info = path.stat()
        assert stat.S_IMODE(info.st_mode) == 0o640
        assert info.st_uid == os.geteuid()
        assert info.st_gid == os.getegid()
        assert info.st_mode & stat.S_IRGRP
        assert not info.st_mode & stat.S_IWGRP
    for directory in (stored_results, stored_reports):
        info = directory.stat()
        assert stat.S_IMODE(info.st_mode) == 0o2750
        assert info.st_mode & stat.S_IRGRP
        assert info.st_mode & stat.S_IXGRP
        assert not info.st_mode & stat.S_IWGRP

    with TestClient(
        create_app(enforce_unprivileged=False, api_token=TEST_API_TOKEN),
        headers=AUTH_HEADERS,
    ) as client:
        history = client.get("/api/v1/executions")
        detail = client.get(f"/api/v1/executions/{execution_id}")
    assert history.status_code == 200
    assert any(item["execution_id"] == execution_id for item in history.json())
    assert detail.status_code == 200
    assert detail.json()["evidence"]["execution_id"] == execution_id


def test_disconnected_worker_returns_explicit_api_error():
    def unavailable(*_args, **_kwargs):
        raise WorkerUnavailableError("worker socket is unavailable")

    app = create_app(
        worker_call_fn=unavailable,
        enforce_unprivileged=False,
        api_token=TEST_API_TOKEN,
    )
    with TestClient(app, headers=AUTH_HEADERS) as client:
        response = client.get("/api/v1/topology")
    assert response.status_code == 503
    assert "Live topology is unavailable" in response.json()["detail"]


def test_worker_request_rejects_arbitrary_command_payload():
    with pytest.raises(ValueError):
        WorkerRequest.model_validate(
            {
                "request_id": str(uuid.uuid4()),
                "operation": "execute",
                "execution_id": "a" * 32,
                "intent": {
                    "scope": {"source": "h1", "destination": "h4"},
                    "optimization": {
                        "metric": "latency",
                        "direction": "MINIMIZE",
                        "unit": "ms",
                    },
                },
                "command": "arbitrary",
            }
        )


def test_worker_rejects_caller_outside_configured_group():
    server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    denied_gid = os.getgid() + 1 if os.getgid() != 0 else 1
    thread = threading.Thread(
        target=_serve_connection,
        args=(server, denied_gid, threading.Lock()),
    )
    thread.start()
    response = WorkerResponse.model_validate_json(client.recv(4096).split(b"\n", 1)[0])
    client.close()
    thread.join(timeout=2)
    assert response.ok is False
    assert "configured API group" in response.error


def test_worker_rejects_unknown_operation_over_socket():
    server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    thread = threading.Thread(
        target=_serve_connection,
        args=(server, os.getgid(), threading.Lock()),
    )
    thread.start()
    request_id = uuid.uuid4()
    client.sendall(
        json.dumps(
            {"request_id": str(request_id), "operation": "shell", "command": "id"}
        ).encode()
        + b"\n"
    )
    response = WorkerResponse.model_validate_json(client.recv(4096).split(b"\n", 1)[0])
    client.close()
    thread.join(timeout=2)
    assert response.ok is False


def test_worker_client_reports_unavailable_and_timeout(tmp_path):
    with pytest.raises(WorkerUnavailableError):
        call_worker("health", socket_path=str(tmp_path / "missing.sock"), timeout_s=0.1)

    socket_path = str(tmp_path / "slow-worker.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)

    def delay_response():
        connection, _ = server.accept()
        with connection:
            connection.recv(4096)
            time.sleep(0.2)
        server.close()

    thread = threading.Thread(target=delay_response)
    thread.start()
    try:
        with pytest.raises(WorkerUnavailableError):
            call_worker("health", socket_path=socket_path, timeout_s=0.05)
    finally:
        thread.join(timeout=2)


def test_ryu_command_binds_both_listeners_to_loopback():
    command = _ryu_command(Path("/opt/ryu-manager"), 6653, 8080)
    assert command[command.index("--ofp-listen-host") + 1] == "127.0.0.1"
    assert command[command.index("--wsapi-host") + 1] == "127.0.0.1"


def test_ryu_listener_check_rejects_wildcard_bind():
    loopback_rows = (
        " sl local_address rem_address   st\n"
        " 0: 0100007F:1A09 00000000:0000 0A 00000000:00000000 "
        "00:00000000 00000000 1000 0 12345\n"
        " 1: 0100007F:1F90 00000000:0000 0A 00000000:00000000 "
        "00:00000000 00000000 1000 0 67890\n"
    )
    wildcard_rows = (
        " sl local_address rem_address   st\n"
        " 0: 00000000:1A09 00000000:0000 0A 00000000:00000000 "
        "00:00000000 00000000 1000 0 12345\n"
        " 1: 0100007F:1F90 00000000:0000 0A 00000000:00000000 "
        "00:00000000 00000000 1000 0 67890\n"
    )
    owned = {"12345", "67890"}
    assert _loopback_listener_addresses(loopback_rows, (6665, 8080), owned)
    assert not _loopback_listener_addresses(wildcard_rows, (6665, 8080), owned)
    assert not _loopback_listener_addresses(loopback_rows, (6665, 8080), {"12345"})


def test_worker_stale_socket_recovery_and_live_socket_protection(tmp_path):
    stale_path = tmp_path / "stale.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(stale_path))
    stale.close()
    _remove_stale_socket(stale_path)
    assert not stale_path.exists()

    live_path = tmp_path / "live.sock"
    live = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    live.bind(str(live_path))
    live.listen()
    try:
        with pytest.raises(RuntimeError, match="live worker"):
            _remove_stale_socket(live_path)
        assert live_path.exists()
    finally:
        live.close()
        live_path.unlink()


def test_worker_shutdown_removes_only_its_socket(tmp_path):
    socket_path = tmp_path / "owned.sock"
    owned = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    owned.bind(str(socket_path))
    identity = (socket_path.stat().st_dev, socket_path.stat().st_ino)
    owned.close()
    _unlink_owned_socket(socket_path, identity)
    assert not socket_path.exists()

    replacement_path = tmp_path / "replacement.sock"
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(replacement_path))
    original_identity = (-1, -1)
    try:
        _unlink_owned_socket(replacement_path, original_identity)
        assert replacement_path.exists()
    finally:
        replacement.close()
        replacement_path.unlink()


def test_worker_startup_is_single_instance_and_shutdown_releases_lock(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(worker_module, "_effective_root", lambda: True)
    monkeypatch.setattr(worker_module, "_trusted_worker_install", lambda: True)
    monkeypatch.setattr(
        worker_module,
        "_worker_socket_directory_is_trusted",
        lambda _path, _gid: True,
    )
    monkeypatch.setattr(worker_module.os, "chown", lambda *_args: None)
    socket_path = tmp_path / "worker.sock"
    lock_path = tmp_path / "worker.lock"
    monkeypatch.setattr(worker_module, "WORKER_LOCK_PATH", lock_path)
    stop_event = threading.Event()
    failures = []

    def run_worker():
        try:
            serve(str(socket_path), os.getegid(), stop_event=stop_event)
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=run_worker)
    thread.start()
    deadline = time.monotonic() + 2
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert socket_path.exists()

    alternate_socket = tmp_path / "alternate.sock"
    with pytest.raises(RuntimeError, match="already owns"):
        serve(str(alternate_socket), os.getegid(), stop_event=threading.Event())
    assert not alternate_socket.exists()

    stop_event.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert failures == []
    assert not socket_path.exists()
    lock_fd = _acquire_worker_lock(lock_path)
    os.close(lock_fd)


def test_worker_startup_failure_releases_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_module, "_effective_root", lambda: True)
    monkeypatch.setattr(worker_module, "_trusted_worker_install", lambda: True)
    monkeypatch.setattr(
        worker_module,
        "_worker_socket_directory_is_trusted",
        lambda _path, _gid: True,
    )
    lock_path = tmp_path / "worker.lock"
    monkeypatch.setattr(worker_module, "WORKER_LOCK_PATH", lock_path)

    class FailingServer:
        def bind(self, _path):
            raise OSError("simulated bind failure")

        def close(self):
            pass

    monkeypatch.setattr(worker_module.socket, "socket", lambda *_args: FailingServer())
    socket_path = tmp_path / "failed-start.sock"
    with pytest.raises(OSError, match="simulated bind failure"):
        serve(str(socket_path), os.getegid())
    lock_fd = _acquire_worker_lock(lock_path)
    os.close(lock_fd)


def test_worker_lock_is_released_after_owner_process_terminates(tmp_path):
    lock_path = tmp_path / "worker.lock"
    script = (
        "import sys, time; "
        "from backend.api.worker import _acquire_worker_lock; "
        "fd = _acquire_worker_lock(__import__('pathlib').Path(sys.argv[1])); "
        "print('locked', flush=True); time.sleep(30)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(RuntimeError, match="already owns"):
            _acquire_worker_lock(lock_path)
    finally:
        process.terminate()
        process.wait(timeout=5)

    lock_fd = _acquire_worker_lock(lock_path)
    os.close(lock_fd)


def test_worker_refuses_to_run_without_root(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.api.worker.os.geteuid", lambda: 1000)
    with pytest.raises(RuntimeError, match="must run as root"):
        serve(str(tmp_path / "worker.sock"), 1000)


def test_worker_refuses_an_untrusted_install(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.api.worker.os.geteuid", lambda: 0)
    monkeypatch.setattr("backend.api.worker._trusted_worker_install", lambda: False)
    with pytest.raises(RuntimeError, match="root-owned and non-writable"):
        serve(str(tmp_path / "worker.sock"), 1000)


def test_worker_socket_accepts_health_from_configured_group():
    server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    thread = threading.Thread(
        target=_serve_connection,
        args=(server, os.getgid(), threading.Lock()),
    )
    thread.start()
    request_id = uuid.uuid4()
    request = WorkerRequest(request_id=request_id, operation="health")
    client.sendall(request.model_dump_json().encode() + b"\n")
    response = WorkerResponse.model_validate_json(client.recv(4096).split(b"\n", 1)[0])
    client.close()
    thread.join(timeout=2)
    assert response.request_id == request_id
    assert response.ok is True
    assert response.result["ready"] is True
    assert response.result["operation_busy"] is False


def test_worker_execute_rejects_invalid_id():
    intent = CanonicalIntent(
        scope=TrafficScope(source="h1", destination="h4"),
        optimization=OptimizationObjective(
            metric="latency",
            direction=OptimizationDirection.MINIMIZE,
            unit="ms",
        ),
    )
    with pytest.raises(ValueError):
        WorkerRequest(
            request_id=uuid.uuid4(),
            operation="execute",
            execution_id="../unsafe",
            intent=intent,
        )
