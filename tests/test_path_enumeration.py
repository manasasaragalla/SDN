from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from backend.models.network import Host, Link, TopologyGraph
from backend.planner.path_enumeration import (
    ConnectionKind,
    EnumeratedPath,
    InvalidPathRequestError,
    InvalidTopologyError,
    PathConnection,
    enumerate_candidate_paths,
    physical_path_capacity_mbps,
)


def _host(name, switch, switch_port):
    suffix = "1" if name.endswith("1") else "4"
    return Host(
        name=name,
        ip=f"10.0.0.{suffix}",
        mac=f"00:00:00:00:00:{int(suffix):02x}",
        switch=switch,
        switch_port=switch_port,
    )


def _diamond_graph():
    return TopologyGraph(
        switches={"s1": 1, "s2": 2, "s3": 3, "s4": 4},
        hosts={
            "h1": _host("h1", "s1", 1),
            "h4": _host("h4", "s4", 1),
        },
        links=[
            Link(node_a="s1", port_a=2, node_b="s2", port_b=1),
            Link(node_a="s2", port_a=2, node_b="s4", port_b=2),
            Link(node_a="s1", port_a=3, node_b="s3", port_b=1),
            Link(node_a="s3", port_a=2, node_b="s4", port_b=3),
        ],
    )


def _parallel_link_graph():
    return TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": _host("h1", "s1", 1),
            "h4": _host("h4", "s2", 1),
        },
        links=[
            Link(
                node_a="s1",
                port_a=2,
                node_b="s2",
                port_b=2,
                bw_mbps=10,
                intf_a="s1-eth2",
                intf_b="s2-eth2",
            ),
            Link(
                node_a="s1",
                port_a=3,
                node_b="s2",
                port_b=3,
                bw_mbps=20,
                intf_a="s1-eth3",
                intf_b="s2-eth3",
            ),
        ],
    )


def _same_switch_graph():
    return TopologyGraph(
        switches={"s1": 1},
        hosts={
            "h1": _host("h1", "s1", 1),
            "h4": _host("h4", "s1", 2),
        },
        links=[],
    )


def test_enumerates_different_switch_paths_with_physical_connections():
    graph = _diamond_graph()
    result = enumerate_candidate_paths(graph, "h1", "h4", candidate_limit=10)

    assert [path.nodes for path in result.paths] == [
        ("h1", "s1", "s2", "s4", "h4"),
        ("h1", "s1", "s3", "s4", "h4"),
    ]
    assert result.truncated is False
    for path in result.paths:
        _assert_physically_valid(graph, path)


def test_same_switch_hosts_use_direct_host_attachment_path():
    graph = _same_switch_graph()
    result = enumerate_candidate_paths(graph, "h1", "h4", candidate_limit=1)

    assert len(result.paths) == 1
    path = result.paths[0]
    assert path.nodes == ("h1", "s1", "h4")
    assert [connection.kind for connection in path.connections] == [
        ConnectionKind.HOST_ATTACHMENT,
        ConnectionKind.HOST_ATTACHMENT,
    ]
    assert path.connections[0].to_port == 1
    assert path.connections[1].from_port == 2
    assert result.truncated is False
    _assert_physically_valid(graph, path)


def test_enumerated_path_rejects_switch_links_at_both_endpoints():
    switch_links = (
        PathConnection(
            kind=ConnectionKind.SWITCH_LINK,
            from_node="h1",
            to_node="s1",
            from_port=1,
            to_port=2,
            link_identity=(("h1", 1), ("s1", 2)),
        ),
        PathConnection(
            kind=ConnectionKind.SWITCH_LINK,
            from_node="s1",
            to_node="h4",
            from_port=2,
            to_port=1,
            link_identity=(("h4", 1), ("s1", 2)),
        ),
    )

    with pytest.raises(
        ValidationError, match="first and last path connections"
    ):
        EnumeratedPath(nodes=("h1", "s1", "h4"), connections=switch_links)


def test_enumerated_path_rejects_host_attachment_as_intermediate_connection():
    path = enumerate_candidate_paths(
        _diamond_graph(), "h1", "h4", candidate_limit=1
    ).paths[0]
    invalid_connections = (
        path.connections[0],
        PathConnection(
            kind=ConnectionKind.HOST_ATTACHMENT,
            from_node="s1",
            to_node="s2",
            from_port=2,
        ),
        *path.connections[2:],
    )

    with pytest.raises(
        ValidationError, match="Intermediate path connections"
    ):
        EnumeratedPath(nodes=path.nodes, connections=invalid_connections)


def test_enumerated_path_accepts_valid_same_and_multi_switch_routes():
    same_switch_path = enumerate_candidate_paths(
        _same_switch_graph(), "h1", "h4", candidate_limit=1
    ).paths[0]
    multi_switch_path = enumerate_candidate_paths(
        _diamond_graph(), "h1", "h4", candidate_limit=1
    ).paths[0]

    assert EnumeratedPath(
        nodes=same_switch_path.nodes,
        connections=same_switch_path.connections,
    ) == same_switch_path
    assert EnumeratedPath(
        nodes=multi_switch_path.nodes,
        connections=multi_switch_path.connections,
    ) == multi_switch_path


def test_parallel_links_remain_distinct_even_with_same_node_sequence():
    graph = _parallel_link_graph()
    result = enumerate_candidate_paths(graph, "h1", "h4", candidate_limit=10)

    assert len(result.paths) == 2
    assert result.paths[0].nodes == result.paths[1].nodes
    identities = {
        path.connections[1].link_identity
        for path in result.paths
    }
    assert len(identities) == 2
    for path in result.paths:
        _assert_physically_valid(graph, path)


@pytest.mark.parametrize("reverse_links", [False, True])
def test_parallel_physical_path_capacity_is_exact_and_order_independent(
    reverse_links,
):
    graph = _parallel_link_graph()
    if reverse_links:
        graph = graph.model_copy(update={"links": list(reversed(graph.links))})

    enumerated = enumerate_candidate_paths(graph, "h1", "h4", candidate_limit=10)
    capacities = {
        path.connections[1].link_identity: physical_path_capacity_mbps(graph, path)
        for path in enumerated.paths
    }
    repeated_capacities = {
        path.connections[1].link_identity: physical_path_capacity_mbps(graph, path)
        for path in enumerate_candidate_paths(
            graph, "h1", "h4", candidate_limit=10
        ).paths
    }

    assert capacities == {
        (("s1", 2), ("s2", 2)): 10,
        (("s1", 3), ("s2", 3)): 20,
    }
    assert sum(capacity >= 15 for capacity in capacities.values()) == 1
    assert repeated_capacities == capacities
    assert graph.path_capacity_mbps(["h1", "s1", "s2", "h4"]) is None
    assert (
        graph.maximum_possible_path_capacity_mbps(
            ["h1", "s1", "s2", "h4"]
        )
        == 20
    )


def test_exact_physical_capacity_is_unknown_when_metadata_is_missing():
    original = _parallel_link_graph()
    graph = original.model_copy(
        update={
            "links": [
                original.links[0],
                original.links[1].model_copy(
                    update={"bw_mbps": None}
                ),
            ]
        }
    )
    paths = enumerate_candidate_paths(graph, "h1", "h4", 10).paths

    capacities = [
        physical_path_capacity_mbps(graph, path)
        for path in paths
    ]

    assert capacities.count(None) == 1
    assert sorted(capacity for capacity in capacities if capacity is not None) == [10]
    assert graph.maximum_possible_path_capacity_mbps(
        ["h1", "s1", "s2", "h4"]
    ) is None


@pytest.mark.parametrize("capacity", [True, False])
def test_link_rejects_boolean_bandwidth_capacity(capacity):
    with pytest.raises(ValidationError, match="not a boolean"):
        Link(
            node_a="s1",
            port_a=2,
            node_b="s2",
            port_b=2,
            bw_mbps=capacity,
        )


@pytest.mark.parametrize(
    "connection_changes",
    [
        {"from_port": 4, "link_identity": (("s1", 4), ("s2", 2))},
        {
            "from_port": 4,
            "to_port": 4,
            "link_identity": (("s1", 4), ("s2", 4)),
        },
    ],
    ids=("wrong-endpoint-port", "nonexistent-link-identity"),
)
def test_exact_physical_capacity_is_unknown_for_nonmatching_path(
    connection_changes,
):
    graph = _parallel_link_graph()
    path = enumerate_candidate_paths(graph, "h1", "h4", 10).paths[0]
    changed = path.connections[1].model_dump()
    changed.update(connection_changes)
    invalid_for_topology = EnumeratedPath(
        nodes=path.nodes,
        connections=(
            path.connections[0],
            PathConnection(**changed),
            path.connections[2],
        ),
    )

    assert physical_path_capacity_mbps(graph, invalid_for_topology) is None


def test_exact_physical_capacity_is_unknown_for_duplicate_matching_link():
    graph = _parallel_link_graph()
    path = enumerate_candidate_paths(graph, "h1", "h4", 10).paths[0]
    ambiguous_graph = graph.model_copy(
        update={"links": [*graph.links, graph.links[0]]}
    )

    assert physical_path_capacity_mbps(ambiguous_graph, path) is None


def test_target_infeasible_on_every_parallel_physical_link():
    original = _parallel_link_graph()
    graph = original.model_copy(
        update={
            "links": [
                original.links[0],
                original.links[1].model_copy(update={"bw_mbps": 12}),
            ]
        }
    )
    paths = enumerate_candidate_paths(graph, "h1", "h4", 10).paths
    capacities = [
        physical_path_capacity_mbps(graph, path)
        for path in paths
    ]

    assert sorted(capacities) == [10, 12]
    assert all(capacity < 15 for capacity in capacities)
    assert graph.maximum_possible_path_capacity_mbps(
        ["h1", "s1", "s2", "h4"]
    ) == 12


def test_exact_physical_capacity_preserves_single_link_behavior():
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={
            "h1": _host("h1", "s1", 1),
            "h4": _host("h4", "s2", 1),
        },
        links=[
            Link(
                node_a="s1",
                port_a=2,
                node_b="s2",
                port_b=2,
                bw_mbps=50,
            )
        ],
    )
    path = enumerate_candidate_paths(graph, "h1", "h4", 1).paths[0]

    assert physical_path_capacity_mbps(graph, path) == 50
    assert graph.path_capacity_mbps(["h1", "s1", "s2", "h4"]) == 50
    assert graph.maximum_possible_path_capacity_mbps(
        ["h1", "s1", "s2", "h4"]
    ) == 50


def test_endpoint_reversal_has_same_link_identity_and_reversed_duplicate_fails():
    forward = Link(node_a="s1", port_a=2, node_b="s2", port_b=3, bw_mbps=10)
    reversed_link = Link(
        node_a="s2",
        port_a=3,
        node_b="s1",
        port_b=2,
        bw_mbps=20,
        intf_a="different-s2-interface",
        intf_b="different-s1-interface",
    )
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s2", 1)},
        links=[forward, reversed_link],
    )

    from backend.planner.path_enumeration import canonical_link_identity

    assert canonical_link_identity(forward) == canonical_link_identity(reversed_link)
    with pytest.raises(InvalidTopologyError, match="Duplicate physical"):
        enumerate_candidate_paths(graph, "h1", "h4", 5)


def test_cyclic_topology_enumerates_only_loop_free_paths():
    graph = _diamond_graph()
    graph.links.append(
        Link(node_a="s2", port_a=3, node_b="s3", port_b=3)
    )

    result = enumerate_candidate_paths(graph, "h1", "h4", candidate_limit=10)

    assert len(result.paths) == 4
    assert all(len(set(path.nodes)) == len(path.nodes) for path in result.paths)


def test_enumeration_order_is_deterministic_under_reordered_input():
    graph = _diamond_graph()
    reordered = TopologyGraph(
        switches=dict(reversed(list(graph.switches.items()))),
        hosts=dict(reversed(list(graph.hosts.items()))),
        links=list(reversed(graph.links)),
    )

    first = enumerate_candidate_paths(graph, "h1", "h4", 10)
    second = enumerate_candidate_paths(reordered, "h1", "h4", 10)
    assert first == second


def test_disconnected_hosts_return_empty_complete_result():
    graph = TopologyGraph(
        switches={"s1": 1, "s2": 2},
        hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s2", 1)},
        links=[],
    )

    result = enumerate_candidate_paths(graph, "h1", "h4", 2)

    assert result.paths == ()
    assert result.truncated is False


@pytest.mark.parametrize(
    ("source", "destination", "message"),
    [
        ("missing", "h4", "Unknown source"),
        ("h1", "missing", "Unknown destination"),
    ],
)
def test_unknown_hosts_are_invalid_requests(source, destination, message):
    with pytest.raises(InvalidPathRequestError, match=message):
        enumerate_candidate_paths(_same_switch_graph(), source, destination, 2)


@pytest.mark.parametrize(
    "graph",
    [
        TopologyGraph(
            switches={"s1": 1},
            hosts={"h1": _host("h1", "missing", 1)},
            links=[],
        ),
        TopologyGraph(
            switches={"s1": 1, "s2": 2},
            hosts={"h1": _host("h1", "s1", 1)},
            links=[Link(node_a="s1", port_a=2, node_b="missing", port_b=1)],
        ),
    ],
)
def test_dangling_switch_references_are_rejected(graph):
    with pytest.raises(InvalidTopologyError, match="unknown switch"):
        enumerate_candidate_paths(graph, "h1", "missing", 1)


def test_host_dictionary_key_must_match_host_name():
    graph = _same_switch_graph()
    graph.hosts["wrong"] = graph.hosts.pop("h1")

    with pytest.raises(InvalidTopologyError, match="does not match Host.name"):
        enumerate_candidate_paths(graph, "wrong", "h4", 2)


@pytest.mark.parametrize("port", [0, -1, True])
def test_invalid_host_attachment_ports_are_rejected(port):
    graph = _same_switch_graph()
    graph.hosts["h1"].switch_port = port

    with pytest.raises(InvalidTopologyError, match="invalid port"):
        enumerate_candidate_paths(graph, "h1", "h4", 2)


@pytest.mark.parametrize("port", [0, -1, True])
def test_invalid_link_ports_are_rejected(port):
    graph = _parallel_link_graph()
    graph.links[0].port_a = port

    with pytest.raises(InvalidTopologyError, match="malformed switch link"):
        enumerate_candidate_paths(graph, "h1", "h4", 2)


@pytest.mark.parametrize(
    "graph",
    [
        TopologyGraph(
            switches={"s1": 1},
            hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s1", 1)},
            links=[],
        ),
        TopologyGraph(
            switches={"s1": 1, "s2": 2},
            hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s2", 1)},
            links=[Link(node_a="s1", port_a=1, node_b="s2", port_b=2)],
        ),
        TopologyGraph(
            switches={"s1": 1, "s2": 2, "s3": 3},
            hosts={"h1": _host("h1", "s1", 1), "h4": _host("h4", "s2", 1)},
            links=[
                Link(node_a="s1", port_a=2, node_b="s2", port_b=2),
                Link(node_a="s1", port_a=2, node_b="s3", port_b=1),
            ],
        ),
    ],
)
def test_switch_port_ownership_conflicts_are_rejected(graph):
    with pytest.raises(InvalidTopologyError, match="claimed by both"):
        enumerate_candidate_paths(graph, "h1", "h4", 10)


def test_self_links_are_rejected():
    graph = _same_switch_graph()
    graph.links.append(Link(node_a="s1", port_a=3, node_b="s1", port_b=4))

    with pytest.raises(InvalidTopologyError, match="self-link"):
        enumerate_candidate_paths(graph, "h1", "h4", 2)


@pytest.mark.parametrize("limit", [0, -1, True, False, 1.0, "2", None])
def test_candidate_limit_must_be_a_positive_non_boolean_integer(limit):
    with pytest.raises(InvalidPathRequestError, match="positive integer"):
        enumerate_candidate_paths(_same_switch_graph(), "h1", "h4", limit)


def test_exact_candidate_limit_exhaustion_is_not_truncated():
    result = enumerate_candidate_paths(_diamond_graph(), "h1", "h4", 2)

    assert len(result.paths) == 2
    assert result.truncated is False


def test_candidate_limit_detects_an_additional_valid_path():
    result = enumerate_candidate_paths(_diamond_graph(), "h1", "h4", 1)

    assert len(result.paths) == 1
    assert result.truncated is True


def test_input_topology_is_not_mutated():
    graph = _diamond_graph()
    before = graph.model_dump(mode="json")

    enumerate_candidate_paths(graph, "h1", "h4", 10)

    assert graph.model_dump(mode="json") == before


def test_path_enumerator_has_no_measurement_or_execution_imports():
    root = Path(__file__).parents[1]
    script = """
import sys
import backend.planner.path_enumeration
forbidden = (
    "backend.measurement",
    "backend.deployment",
    "backend.pipeline",
    "backend.cli",
    "backend.compiler",
    "mininet",
    "ryu",
)
loaded = [
    module for module in sys.modules
    if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)
]
if loaded:
    raise SystemExit(f"unexpected execution dependencies loaded: {loaded}")
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _assert_physically_valid(graph, path):
    assert len(path.connections) == len(path.nodes) - 1
    for index, connection in enumerate(path.connections):
        assert (connection.from_node, connection.to_node) == (
            path.nodes[index],
            path.nodes[index + 1],
        )
        if connection.kind == ConnectionKind.HOST_ATTACHMENT:
            if connection.from_node in graph.hosts:
                host = graph.hosts[connection.from_node]
                assert host.switch == connection.to_node
                assert connection.from_port is None
                assert connection.to_port == host.switch_port
            else:
                host = graph.hosts[connection.to_node]
                assert host.switch == connection.from_node
                assert connection.from_port == host.switch_port
                assert connection.to_port is None
        else:
            identity = connection.link_identity
            matching = [
                link
                for link in graph.links
                if tuple(
                    sorted(
                        (
                            (link.node_a, link.port_a),
                            (link.node_b, link.port_b),
                        )
                    )
                )
                == identity
            ]
            assert len(matching) == 1
            link = matching[0]
            assert (connection.from_port, connection.to_port) in (
                (link.port_a, link.port_b)
                if connection.from_node == link.node_a
                else (link.port_b, link.port_a),
            )
