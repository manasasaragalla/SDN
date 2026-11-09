import pytest
from pydantic import ValidationError

from backend.compiler.physical_path import compile_physical_path
from backend.models.network import Host, Link, TopologyGraph
from backend.planner.path_enumeration import (
    ConnectionKind,
    EnumeratedPath,
    PathConnection,
    enumerate_candidate_paths,
)


def _host(name, ip, switch, switch_port):
    return Host(
        name=name,
        ip=ip,
        mac=f"00:00:00:00:00:{switch_port:02x}",
        switch=switch,
        switch_port=switch_port,
    )


def _single_switch_graph():
    return TopologyGraph(
        switches={"s1": 11},
        hosts={
            "h1": _host("h1", "10.0.0.1", "s1", 1),
            "h2": _host("h2", "10.0.0.2", "s1", 2),
        },
        links=[],
    )


def _multi_switch_graph(parallel=False):
    links = [
        Link(node_a="s1", port_a=2, node_b="s2", port_b=1),
        Link(node_a="s2", port_a=2, node_b="s3", port_b=1),
    ]
    if parallel:
        links.insert(1, Link(node_a="s1", port_a=3, node_b="s2", port_b=3))
    return TopologyGraph(
        switches={"s1": 11, "s2": 22, "s3": 33},
        hosts={
            "h1": _host("h1", "10.0.0.1", "s1", 1),
            "h2": _host("h2", "10.0.0.2", "s3", 2),
        },
        links=links,
    )


def _path(graph):
    return enumerate_candidate_paths(
        graph, "h1", "h2", candidate_limit=10
    ).paths


def test_single_switch_compiles_bidirectional_ipv4_and_arp_rules():
    graph = _single_switch_graph()
    rules = compile_physical_path(graph, _path(graph)[0])

    assert len(rules) == 4
    forward = next(rule for rule in rules if rule.match.get("ipv4_src") == "10.0.0.1")
    reverse = next(rule for rule in rules if rule.match.get("ipv4_src") == "10.0.0.2")
    assert forward.match["in_port"] == 1
    assert forward.actions == [{"type": "OUTPUT", "port": 2}]
    assert reverse.match["in_port"] == 2
    assert reverse.actions == [{"type": "OUTPUT", "port": 1}]
    assert {rule.match["eth_type"] for rule in rules} == {0x0800, 0x0806}


def test_multi_switch_rules_use_each_exact_ingress_and_egress_port():
    graph = _multi_switch_graph()
    rules = compile_physical_path(graph, _path(graph)[0])

    assert len(rules) == 12
    forward_s1 = next(
        rule for rule in rules
        if rule.dpid == 11 and rule.match.get("ipv4_src") == "10.0.0.1"
    )
    forward_s2 = next(
        rule for rule in rules
        if rule.dpid == 22 and rule.match.get("ipv4_src") == "10.0.0.1"
    )
    reverse_s2 = next(
        rule for rule in rules
        if rule.dpid == 22 and rule.match.get("ipv4_src") == "10.0.0.2"
    )
    reverse_s3 = next(
        rule for rule in rules
        if rule.dpid == 33 and rule.match.get("ipv4_src") == "10.0.0.2"
    )
    assert (forward_s1.match["in_port"], forward_s1.actions[0]["port"]) == (1, 2)
    assert (forward_s2.match["in_port"], forward_s2.actions[0]["port"]) == (1, 2)
    assert (reverse_s2.match["in_port"], reverse_s2.actions[0]["port"]) == (2, 1)
    assert (reverse_s3.match["in_port"], reverse_s3.actions[0]["port"]) == (2, 1)


def test_parallel_links_compile_only_selected_physical_connection():
    graph = _multi_switch_graph(parallel=True)
    paths = _path(graph)
    assert len(paths) == 2

    rules = compile_physical_path(graph, paths[1])
    forward_s1 = next(
        rule for rule in rules
        if rule.dpid == 11 and rule.match.get("ipv4_src") == "10.0.0.1"
    )
    forward_s2 = next(
        rule for rule in rules
        if rule.dpid == 22 and rule.match.get("ipv4_src") == "10.0.0.1"
    )
    assert (forward_s1.match["in_port"], forward_s1.actions[0]["port"]) == (1, 3)
    assert (forward_s2.match["in_port"], forward_s2.actions[0]["port"]) == (3, 2)


def test_output_is_deterministic_and_has_no_duplicate_or_conflicting_matches():
    graph = _multi_switch_graph()
    path = _path(graph)[0]
    rules = compile_physical_path(graph, path)

    assert rules == compile_physical_path(graph, path)
    keys = [
        (rule.dpid, rule.priority, tuple(sorted(rule.match.items())))
        for rule in rules
    ]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    "priority",
    [True, 0, 65536],
)
def test_rejects_invalid_priority(priority):
    graph = _single_switch_graph()
    with pytest.raises(ValueError):
        compile_physical_path(graph, _path(graph)[0], priority=priority)


def test_rejects_path_with_incorrect_host_attachment_port():
    graph = _single_switch_graph()
    path = _path(graph)[0]
    wrong_first = PathConnection(
        kind=ConnectionKind.HOST_ATTACHMENT,
        from_node="h1",
        to_node="s1",
        to_port=3,
    )
    malformed = EnumeratedPath(
        nodes=path.nodes,
        connections=(wrong_first, path.connections[1]),
    )

    with pytest.raises(ValueError, match="host attachments"):
        compile_physical_path(graph, malformed)


def test_rejects_switch_link_with_incorrect_physical_ports():
    graph = _multi_switch_graph()
    path = _path(graph)[0]
    wrong_link = PathConnection(
        kind=ConnectionKind.SWITCH_LINK,
        from_node="s1",
        to_node="s2",
        from_port=7,
        to_port=8,
        link_identity=(("s1", 7), ("s2", 8)),
    )
    malformed = EnumeratedPath(
        nodes=path.nodes,
        connections=(path.connections[0], wrong_link, *path.connections[2:]),
    )

    with pytest.raises(ValueError, match="does not match"):
        compile_physical_path(graph, malformed)


def test_rejects_missing_endpoint_host_or_switch_attachment():
    graph = _single_switch_graph()
    path = _path(graph)[0]
    without_host = TopologyGraph(
        switches=graph.switches,
        hosts={"h1": graph.hosts["h1"]},
        links=[],
    )
    with pytest.raises(ValueError):
        compile_physical_path(without_host, path)

    without_switch = TopologyGraph(
        switches={},
        hosts=graph.hosts,
        links=[],
    )
    with pytest.raises(ValueError):
        compile_physical_path(without_switch, path)


def test_rejects_duplicate_dpids_that_could_create_rule_conflicts():
    graph = _multi_switch_graph()
    graph.switches["s2"] = graph.switches["s1"]
    with pytest.raises(ValueError, match="Topology switches"):
        compile_physical_path(graph, _path(graph)[0])


def test_rejects_duplicate_dpid_between_selected_and_off_path_switches():
    graph = _multi_switch_graph()
    graph.switches["s3"] = 44
    graph.switches["s2"] = 22
    graph.switches["s1"] = 11
    graph.switches["s4"] = 11
    graph.hosts["h3"] = _host("h3", "10.0.0.3", "s4", 1)

    with pytest.raises(ValueError, match="Topology switches"):
        compile_physical_path(graph, _path(graph)[0])


def test_rejects_duplicate_dpid_between_two_off_path_switches():
    graph = _multi_switch_graph()
    graph.switches["s4"] = 44
    graph.switches["s5"] = 55
    graph.switches["s6"] = 55
    graph.hosts["h3"] = _host("h3", "10.0.0.3", "s4", 3)
    graph.hosts["h4"] = _host("h4", "10.0.0.4", "s5", 1)
    graph.hosts["h5"] = _host("h5", "10.0.0.5", "s6", 1)

    with pytest.raises(ValueError, match="Topology switches"):
        compile_physical_path(graph, _path(graph)[0])


@pytest.mark.parametrize("invalid_dpid", [True, False, 0, -1])
def test_rejects_invalid_dpid_values(invalid_dpid):
    graph = _single_switch_graph()
    graph.switches["s1"] = invalid_dpid

    with pytest.raises(ValueError, match="Topology switches"):
        compile_physical_path(graph, _path(graph)[0])


def test_rejects_unsupported_or_ambiguous_endpoint_addresses():
    graph = _single_switch_graph()
    graph.hosts["h1"].ip = "2001:db8::1"
    with pytest.raises(ValueError, match="valid IPv4"):
        compile_physical_path(graph, _path(graph)[0])

    graph = _single_switch_graph()
    graph.hosts["h2"].ip = graph.hosts["h1"].ip
    with pytest.raises(ValueError, match="distinct IPv4"):
        compile_physical_path(graph, _path(graph)[0])


def test_rejects_duplicate_endpoint_ip_used_by_another_host():
    graph = _single_switch_graph()
    graph.switches["s2"] = 22
    graph.hosts["h3"] = _host("h3", "10.0.0.1", "s2", 1)
    with pytest.raises(ValueError, match="must be unique"):
        compile_physical_path(graph, _path(graph)[0])


def test_wrong_endpoint_path_is_rejected_without_fallback():
    graph = _multi_switch_graph(parallel=True)
    selected = _path(graph)[1]
    # Remove the selected link; compilation must reject instead of substituting another route.
    graph.links = graph.links[:1]
    with pytest.raises(ValueError):
        compile_physical_path(graph, selected)


def test_invalid_enumerated_path_is_rejected():
    graph = _single_switch_graph()
    path = _path(graph)[0]
    with pytest.raises(ValidationError):
        EnumeratedPath(nodes=("h1", "s1", "h2", "s1"), connections=path.connections)
