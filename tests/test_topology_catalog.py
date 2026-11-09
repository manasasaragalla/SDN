from __future__ import annotations

from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.api.main import create_app
from backend.api.services.topology_catalog import TopologyCatalog
from backend.api.services.worker_client import WorkerUnavailableError
from backend.llm.mock import MockLLM
from backend.models.network import Host, Link, TopologyGraph
from backend.models.topology_definition import TopologyDefinitionInput

API_TOKEN = "topology-catalog-api-test-token-1234567890"


def _diamond_topology():
    return TopologyDefinitionInput(
        name="Planning diamond",
        graph=TopologyGraph(
            switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4, "s5": 5},
            hosts={
                "h1": Host(
                    name="h1",
                    ip="10.0.0.1",
                    mac="00:00:00:00:00:01",
                    switch="s1",
                    switch_port=1,
                ),
                "h4": Host(
                    name="h4",
                    ip="10.0.0.4",
                    mac="00:00:00:00:00:04",
                    switch="s4",
                    switch_port=1,
                ),
            },
            links=[
                Link(
                    node_a="s1",
                    port_a=2,
                    node_b="s2",
                    port_b=1,
                    bw_mbps=10,
                    delay_ms=2,
                    packet_loss_percent=0,
                    admin_up=True,
                ),
                Link(
                    node_a="s2",
                    port_a=2,
                    node_b="s4",
                    port_b=2,
                    bw_mbps=10,
                    delay_ms=2,
                    packet_loss_percent=0,
                    admin_up=True,
                ),
                Link(
                    node_a="s1",
                    port_a=3,
                    node_b="s3",
                    port_b=1,
                    bw_mbps=50,
                    delay_ms=8,
                    packet_loss_percent=0.1,
                    admin_up=True,
                ),
                Link(
                    node_a="s3",
                    port_a=2,
                    node_b="s5",
                    port_b=1,
                    bw_mbps=50,
                    delay_ms=8,
                    packet_loss_percent=0.1,
                    admin_up=True,
                ),
                Link(
                    node_a="s5",
                    port_a=2,
                    node_b="s4",
                    port_b=3,
                    bw_mbps=50,
                    delay_ms=8,
                    packet_loss_percent=0.1,
                    admin_up=True,
                ),
            ],
        ),
    )


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.api.main.get_llm_provider", lambda: MockLLM())
    catalog = TopologyCatalog(tmp_path / "topologies.sqlite3")

    def worker(operation: str, **_kwargs):
        if operation == "topology":
            raise WorkerUnavailableError("worker unavailable in catalog test")
        raise AssertionError(f"Unexpected worker operation: {operation}")

    app = create_app(
        worker_call_fn=worker,
        enforce_unprivileged=False,
        api_token=API_TOKEN,
        topology_catalog=catalog,
    )
    with TestClient(app, headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        yield client, catalog


def _create_active(client, topology_input=None):
    body = (topology_input or _diamond_topology()).model_dump(mode="json")
    response = client.post("/api/v1/topologies", json=body)
    assert response.status_code == 201, response.text
    topology = response.json()
    activated = client.post(
        f"/api/v1/topologies/{topology['id']}/activate",
        json={},
    )
    assert activated.status_code == 200, activated.text
    return topology


def test_catalog_versions_active_switching_duplicate_rename_and_delete(api_client):
    client, catalog = api_client
    first = catalog.create(_diamond_topology())
    second_input = TopologyDefinitionInput(
        name="Revised planning diamond",
        graph=first.graph,
        positions=first.positions,
    )
    revised = catalog.update(first.id, 1, second_input)

    assert revised.version == 2
    assert [item.version for item in catalog.versions(first.id)] == [2, 1]

    active = catalog.activate(first.id, version=1)
    assert active.version == 1
    renamed = catalog.rename(first.id, 2, "Renamed topology")
    assert renamed.version == 3
    assert catalog.active().version == 3

    duplicate = catalog.duplicate(first.id, "Copy")
    assert duplicate.id != first.id
    assert duplicate.version == 1
    catalog.activate(duplicate.id)
    assert catalog.active().id == duplicate.id

    response = client.delete(f"/api/v1/topologies/{duplicate.id}")
    assert response.status_code == 204
    assert catalog.active() is None


def test_catalog_rejects_stale_version_update(api_client):
    _, catalog = api_client
    topology = catalog.create(_diamond_topology())
    catalog.update(topology.id, 1, _diamond_topology())

    from backend.api.services.topology_catalog import TopologyVersionConflictError

    with pytest.raises(TopologyVersionConflictError, match="current version is 2"):
        catalog.update(topology.id, 1, _diamond_topology())


@pytest.mark.parametrize(
    ("text", "expected_path"),
    [
        ("Find the highest bandwidth path between h1 and h4.", ["h1", "s1", "s3", "s5", "s4", "h4"]),
        ("Minimize latency between h1 and h4.", ["h1", "s1", "s2", "s4", "h4"]),
        (
            "Minimize latency between h1 and h4 while maintaining bandwidth above 20 Mbps.",
            ["h1", "s1", "s3", "s5", "s4", "h4"],
        ),
    ],
)
def test_active_design_topology_drives_candidate_planning(
    api_client,
    text,
    expected_path,
):
    client, _ = api_client
    topology = _create_active(client)
    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": text,
            "source": "h1",
            "destination": "h4",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    result = body["planning_result"]
    assert body["topology_identity"]["id"] == topology["id"]
    assert body["topology_identity"]["version"] == 1
    assert body["topology_identity"]["mode"] == "DESIGN"
    assert result["topology_identity"] == body["topology_identity"]
    assert body["execution_eligible"] is False
    assert result["status"] == "SELECTED"
    selected = next(
        candidate
        for candidate in result["candidates"]
        if candidate["candidate_id"] == result["selected_candidate_id"]
    )
    assert selected["path"] == expected_path
    assert "not achieved throughput" in result["provenance"]


def test_arbitrary_active_topology_supports_path_ranking_and_constraints(api_client):
    client, _ = api_client
    topology = TopologyDefinitionInput(
        name="Campus test graph",
        graph=TopologyGraph(
            switches={"edge_l": 11, "core_fast": 12, "core_wide": 13, "edge_r": 14},
            hosts={
                "client": Host(
                    name="client",
                    ip="198.51.100.10",
                    mac="02:00:00:00:10:01",
                    switch="edge_l",
                    switch_port=1,
                ),
                "server": Host(
                    name="server",
                    ip="198.51.100.20",
                    mac="02:00:00:00:20:01",
                    switch="edge_r",
                    switch_port=1,
                ),
            },
            links=[
                Link(node_a="edge_l", port_a=2, node_b="core_fast", port_b=1, bw_mbps=10, delay_ms=2, admin_up=True),
                Link(node_a="core_fast", port_a=2, node_b="edge_r", port_b=2, bw_mbps=10, delay_ms=2, admin_up=True),
                Link(node_a="edge_l", port_a=3, node_b="core_wide", port_b=1, bw_mbps=50, delay_ms=8, admin_up=True),
                Link(node_a="core_wide", port_a=2, node_b="edge_r", port_b=3, bw_mbps=50, delay_ms=8, admin_up=True),
            ],
        ),
    )
    saved = _create_active(client, topology)
    requests = [
        ("Find the highest bandwidth path.", "client", "server", "core_wide"),
        ("Find the lowest-latency path.", "client", "server", "core_fast"),
        (
            "Minimize latency while maintaining bandwidth above 20 Mbps.",
            "client",
            "server",
            "core_wide",
        ),
    ]

    for prompt, source, destination, selected_switch in requests:
        response = client.post(
            "/api/v1/intents/preview",
            json={
                "natural_language": prompt,
                "source": source,
                "destination": destination,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        plan = body["planning_result"]
        selected = next(
            candidate
            for candidate in plan["candidates"]
            if candidate["selection"] == "SELECTED"
        )
        assert body["topology_identity"]["id"] == saved["id"]
        assert selected_switch in selected["path"]
        if "maintaining bandwidth" in prompt:
            faster = next(
                candidate
                for candidate in plan["candidates"]
                if "core_fast" in candidate["path"]
            )
            assert faster["status"] == "REJECTED"
            assert faster["constraints"][0]["status"] == "VIOLATED"


def test_active_design_planning_evaluates_multiple_hard_constraints(api_client):
    client, _ = api_client
    _create_active(client)
    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": (
                "Find a path between h1 and h4 with bandwidth above 20 Mbps "
                "and latency below 30 ms."
            ),
            "source": "h1",
            "destination": "h4",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["planning_result"]
    assert result["status"] == "SELECTED"
    direct, alternate = result["candidates"]
    assert direct["status"] == "REJECTED"
    assert [item["status"] for item in direct["constraints"]] == [
        "VIOLATED",
        "SATISFIED",
    ]
    assert alternate["status"] == "ELIGIBLE"
    assert alternate["selection"] == "SELECTED"
    assert [item["status"] for item in alternate["constraints"]] == [
        "SATISFIED",
        "SATISFIED",
    ]


def test_missing_link_capacity_is_unknown_not_a_passing_bandwidth_constraint(api_client):
    client, _ = api_client
    topology = _diamond_topology()
    graph = topology.graph.model_copy(deep=True)
    graph.links[0].bw_mbps = None
    _create_active(
        client,
        TopologyDefinitionInput(
            name=topology.name,
            graph=graph,
            positions=topology.positions,
        ),
    )

    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": (
                "Find a path between h1 and h4 with bandwidth above 5 Mbps."
            ),
            "source": "h1",
            "destination": "h4",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["planning_result"]
    direct, alternate = result["candidates"]
    assert direct["configured_metrics"]["bandwidth_mbps"] is None
    assert direct["status"] == "UNKNOWN"
    assert direct["constraints"][0]["status"] == "UNKNOWN"
    assert alternate["status"] == "ELIGIBLE"
    assert alternate["selection"] == "SELECTED"


def test_topology_activation_changes_following_preview_graph(api_client):
    client, catalog = api_client
    first = _create_active(client)
    second_graph = TopologyGraph(
        switches={"x1": 11, "x2": 12},
        hosts={
            "ha": Host(
                name="ha",
                ip="192.0.2.1",
                mac="02:00:00:00:00:01",
                switch="x1",
                switch_port=1,
            ),
            "hb": Host(
                name="hb",
                ip="192.0.2.2",
                mac="02:00:00:00:00:02",
                switch="x2",
                switch_port=1,
            ),
        },
        links=[
            Link(
                node_a="x1",
                port_a=2,
                node_b="x2",
                port_b=2,
                bw_mbps=90,
                delay_ms=1,
                admin_up=True,
            )
        ],
    )
    second = catalog.create(
        TopologyDefinitionInput(name="Second topology", graph=second_graph)
    )
    catalog.activate(second.id)

    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": "Find a path with bandwidth greater than 20 Mbps.",
            "source": "ha",
            "destination": "hb",
        },
    )

    assert response.status_code == 200
    assert response.json()["topology_identity"]["id"] == str(second.id)
    assert response.json()["planning_result"]["candidate_count"] == 1
    assert response.json()["topology_identity"]["id"] != first["id"]


def test_unknown_hosts_are_rejected_against_active_topology(api_client):
    client, _ = api_client
    _create_active(client)

    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": "Find the highest bandwidth path from hx to h4.",
            "source": "hx",
            "destination": "h4",
        },
    )

    assert response.status_code == 422
    assert "not present in the active DESIGN topology" in response.json()["detail"]


def test_no_active_topology_returns_actionable_preview(api_client):
    client, _ = api_client
    active = client.get("/api/v1/topologies/active")
    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": "Find the highest bandwidth path from h1 to h4.",
            "source": "h1",
            "destination": "h4",
        },
    )

    assert active.status_code == 200
    assert active.json() == {"topology": None, "active": False}
    assert response.status_code == 200
    body = response.json()
    assert body["topology_identity"] is None
    assert body["planning_result"] is None
    assert any("Create or import a DESIGN topology" in item for item in body["explanation"])


def test_import_export_round_trip_and_parallel_ports(api_client):
    client, _ = api_client
    body = _diamond_topology().model_dump(mode="json")
    body["graph"]["links"].append(
        {
            "node_a": "s1",
            "port_a": 4,
            "node_b": "s2",
            "port_b": 3,
            "bw_mbps": 25,
            "delay_ms": 3,
            "packet_loss_percent": 0,
            "admin_up": True,
            "intf_a": None,
            "intf_b": None,
        }
    )
    imported = client.post(
        "/api/v1/topologies/import",
        json={"format": "intentflow-topology-v1", "topology": body},
    )
    assert imported.status_code == 201, imported.text
    topology = imported.json()

    exported = client.get(f"/api/v1/topologies/{topology['id']}/export")
    assert exported.status_code == 200
    assert exported.json()["topology"]["graph"] == topology["graph"]
    assert len(topology["graph"]["links"]) == 6

    activated = client.post(
        f"/api/v1/topologies/{topology['id']}/activate",
        json={},
    )
    assert activated.status_code == 200
    preview = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": "Maximize bandwidth from h1 to h4.",
            "source": "h1",
            "destination": "h4",
        },
    )
    assert preview.status_code == 200
    paths = preview.json()["planning_result"]["candidates"]
    assert any(
        {"s1", 2, "s2", 1}
        == {
            link["node_a"],
            link["port_a"],
            link["node_b"],
            link["port_b"],
        }
        for path in paths
        for link in path["physical_links"]
    )


def test_administratively_down_link_is_not_enumerated(api_client):
    client, _ = api_client
    input_topology = _diamond_topology()
    input_topology.graph.links[0].admin_up = False
    _create_active(client, input_topology)

    response = client.post(
        "/api/v1/intents/preview",
        json={
            "natural_language": "Find the highest bandwidth path from h1 to h4.",
            "source": "h1",
            "destination": "h4",
        },
    )

    assert response.status_code == 200
    paths = response.json()["planning_result"]["candidates"]
    assert all("s2" not in candidate["path"] for candidate in paths)


def test_design_topology_invalid_ports_and_dpids_are_rejected():
    base = _diamond_topology().model_dump(mode="python")
    base["graph"]["switches"]["s2"] = base["graph"]["switches"]["s1"]
    with pytest.raises(ValidationError, match="DPIDs must be unique"):
        TopologyDefinitionInput.model_validate(base)

    base = _diamond_topology().model_dump(mode="python")
    base["graph"]["links"][2]["port_a"] = 2
    with pytest.raises(ValidationError, match="assigned more than once"):
        TopologyDefinitionInput.model_validate(base)


def test_design_topology_rejects_duplicate_host_addresses():
    base = _diamond_topology().model_dump(mode="python")
    base["graph"]["hosts"]["h4"]["ip"] = base["graph"]["hosts"]["h1"]["ip"]
    with pytest.raises(ValidationError, match="duplicate IP address"):
        TopologyDefinitionInput.model_validate(base)

    base = _diamond_topology().model_dump(mode="python")
    base["graph"]["hosts"]["h4"]["mac"] = base["graph"]["hosts"]["h1"]["mac"]
    with pytest.raises(ValidationError, match="duplicate MAC address"):
        TopologyDefinitionInput.model_validate(base)
