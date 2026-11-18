import assert from "node:assert/strict";
import test from "node:test";
import { generateRandomTopology } from "../src/lib/topology-generator.ts";
import { nextAvailableAttachmentPort } from "../src/lib/topology-port-allocation.ts";

const settings = (overrides = {}) => ({
  name: "Generated test",
  switchCount: 6,
  hostCount: 8,
  pattern: "RANDOM",
  extraLinks: 1,
  bandwidthMinMbps: 10,
  bandwidthMaxMbps: 100,
  delayMinMs: 0,
  delayMaxMs: 20,
  packetLossMinPercent: 0,
  packetLossMaxPercent: 2,
  seed: "repeatable-seed",
  ...overrides,
});

function assertConnected(topology) {
  const switches = Object.keys(topology.graph.switches);
  const visited = new Set([switches[0]]);
  const pending = [switches[0]];
  while (pending.length) {
    const node = pending.pop();
    for (const link of topology.graph.links) {
      const neighbor = link.node_a === node ? link.node_b : link.node_b === node ? link.node_a : null;
      if (neighbor && !visited.has(neighbor)) {
        visited.add(neighbor);
        pending.push(neighbor);
      }
    }
  }
  assert.equal(visited.size, switches.length);
}

for (const [pattern, extraLinks] of [
  ["STAR", 1],
  ["RING", 1],
  ["TREE", 2],
  ["MESH", 0],
  ["RANDOM", 2],
]) {
  test(`${pattern} generates a connected graph with valid unique ports and attached hosts`, () => {
    const { topology } = generateRandomTopology(settings({ pattern, extraLinks }));
    assertConnected(topology);
    assert.equal(Object.keys(topology.graph.hosts).length, 8);
    assert.ok(Object.values(topology.graph.hosts).every((host) => topology.graph.switches[host.switch]));
    assert.equal(topology.graph.links.length, pattern === "MESH" ? 15 : pattern === "RING" ? 7 : pattern === "STAR" ? 6 : pattern === "TREE" ? 7 : 7);
    const assigned = new Set();
    for (const [switchName, ports] of Object.entries(topology.graph.switch_ports)) {
      assert.equal(new Set(ports).size, ports.length);
      for (const port of ports) {
        const key = `${switchName}:${port}`;
        assert.ok(!assigned.has(key), `duplicate assigned port ${key}`);
        assigned.add(key);
      }
    }
    assert.ok(topology.graph.links.every((link) => link.node_a !== link.node_b));
    assert.ok(topology.graph.links.every((link) =>
      link.bw_mbps >= 10 && link.bw_mbps <= 100
      && link.delay_ms >= 0 && link.delay_ms <= 20
      && link.packet_loss_percent >= 0 && link.packet_loss_percent <= 2));
  });
}

test("the same seed and settings produce identical topology data", () => {
  const first = generateRandomTopology(settings());
  const second = generateRandomTopology(settings());
  assert.deepEqual(first, second);
});

test("adding a host to the default seed-42 topology uses an unoccupied s1 port", () => {
  const { topology } = generateRandomTopology(settings({
    name: "test1",
    switchCount: 6,
    hostCount: 6,
    pattern: "RANDOM",
    extraLinks: 2,
    bandwidthMinMbps: 20,
    bandwidthMaxMbps: 100,
    delayMinMs: 1,
    delayMaxMs: 10,
    packetLossMinPercent: 0,
    packetLossMaxPercent: 1,
    seed: "42",
  }));
  const graph = topology.graph;
  const nodes = [
    ...Object.keys(graph.switches).map((id) => ({ id, data: { kind: "switch" } })),
    ...Object.values(graph.hosts).map((host) => ({
      id: host.name,
      data: { kind: "host", switchName: host.switch, switchPort: host.switch_port },
    })),
  ];
  const edges = graph.links.map((link) => ({
    source: link.node_a,
    target: link.node_b,
    data: { source_port: link.port_a, target_port: link.port_b },
  }));

  const selectedPort = nextAvailableAttachmentPort("s1", graph.switch_ports.s1, nodes, edges);
  const occupiedPorts = [
    ...Object.values(graph.hosts)
      .filter((host) => host.switch === "s1")
      .map((host) => host.switch_port),
    ...graph.links.flatMap((link) => [
      ...(link.node_a === "s1" ? [link.port_a] : []),
      ...(link.node_b === "s1" ? [link.port_b] : []),
    ]),
  ];

  assert.equal(selectedPort, 5);
  assert.ok(!occupiedPorts.includes(selectedPort));
});

test("invalid generation ranges, pattern sizes, and extra-link counts are rejected", () => {
  assert.throws(() => generateRandomTopology(settings({ switchCount: 1 })), /Switch count/);
  assert.throws(() => generateRandomTopology(settings({ pattern: "RING", switchCount: 2 })), /ring requires/);
  assert.throws(() => generateRandomTopology(settings({ bandwidthMinMbps: 110 })), /Bandwidth range/);
  assert.throws(() => generateRandomTopology(settings({ pattern: "MESH", extraLinks: 1 })), /Extra links/);
});
