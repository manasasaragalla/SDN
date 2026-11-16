import assert from "node:assert/strict";
import test from "node:test";
import { generateRandomTopology } from "../src/lib/topology-generator.ts";

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

test("invalid generation ranges, pattern sizes, and extra-link counts are rejected", () => {
  assert.throws(() => generateRandomTopology(settings({ switchCount: 1 })), /Switch count/);
  assert.throws(() => generateRandomTopology(settings({ pattern: "RING", switchCount: 2 })), /ring requires/);
  assert.throws(() => generateRandomTopology(settings({ bandwidthMinMbps: 110 })), /Bandwidth range/);
  assert.throws(() => generateRandomTopology(settings({ pattern: "MESH", extraLinks: 1 })), /Extra links/);
});
