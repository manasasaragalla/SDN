import type { TopologyDefinitionInput } from "@/types/api";

export type TopologyPattern = "STAR" | "RING" | "TREE" | "MESH" | "RANDOM";

export interface RandomTopologySettings {
  name: string;
  switchCount: number;
  hostCount: number;
  pattern: TopologyPattern;
  extraLinks: number;
  bandwidthMinMbps: number;
  bandwidthMaxMbps: number;
  delayMinMs: number;
  delayMaxMs: number;
  packetLossMinPercent: number;
  packetLossMaxPercent: number;
  seed?: string;
}

export interface GeneratedTopology {
  topology: TopologyDefinitionInput;
  seed: string;
}

const MAX_SWITCHES = 32;
const MAX_HOSTS = 128;

function assertRange(name: string, minimum: number, maximum: number, lower: number, upper: number): void {
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || minimum < lower || maximum < minimum || maximum > upper) {
    throw new Error(`${name} must be between ${lower} and ${upper}, with the minimum no greater than the maximum.`);
  }
}

function createRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function seedValue(seed: string): number {
  let value = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    value ^= seed.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

function roundedBetween(random: () => number, minimum: number, maximum: number): number {
  return Math.round((minimum + random() * (maximum - minimum)) * 100) / 100;
}

function connectedPairs(switchCount: number, pattern: TopologyPattern, random: () => number): [number, number][] {
  const pairs: [number, number][] = [];
  const addPair = (a: number, b: number) => {
    const pair = a < b ? [a, b] as [number, number] : [b, a] as [number, number];
    if (!pairs.some(([left, right]) => left === pair[0] && right === pair[1])) pairs.push(pair);
  };

  if (pattern === "STAR") {
    for (let index = 1; index < switchCount; index += 1) addPair(0, index);
  } else if (pattern === "RING") {
    for (let index = 0; index < switchCount; index += 1) addPair(index, (index + 1) % switchCount);
  } else if (pattern === "TREE") {
    for (let index = 1; index < switchCount; index += 1) addPair(Math.floor((index - 1) / 2), index);
  } else if (pattern === "MESH") {
    for (let left = 0; left < switchCount; left += 1) {
      for (let right = left + 1; right < switchCount; right += 1) addPair(left, right);
    }
  } else {
    for (let index = 1; index < switchCount; index += 1) {
      addPair(index, Math.floor(random() * index));
    }
  }

  return pairs;
}

export function generateRandomTopology(settings: RandomTopologySettings): GeneratedTopology {
  const name = settings.name.trim();
  if (!name || name.length > 80) throw new Error("Topology name must contain 1 to 80 characters.");
  if (!Number.isInteger(settings.switchCount) || settings.switchCount < 2 || settings.switchCount > MAX_SWITCHES) {
    throw new Error(`Switch count must be an integer from 2 to ${MAX_SWITCHES}.`);
  }
  if (!Number.isInteger(settings.hostCount) || settings.hostCount < 1 || settings.hostCount > MAX_HOSTS) {
    throw new Error(`Host count must be an integer from 1 to ${MAX_HOSTS}.`);
  }
  if (!["STAR", "RING", "TREE", "MESH", "RANDOM"].includes(settings.pattern)) {
    throw new Error("Choose a supported topology pattern.");
  }
  if (settings.pattern === "RING" && settings.switchCount < 3) {
    throw new Error("A ring requires at least 3 switches.");
  }
  assertRange("Bandwidth range", settings.bandwidthMinMbps, settings.bandwidthMaxMbps, 0.01, 100000);
  assertRange("Delay range", settings.delayMinMs, settings.delayMaxMs, 0, 10000);
  assertRange("Packet-loss range", settings.packetLossMinPercent, settings.packetLossMaxPercent, 0, 100);

  const seed = settings.seed?.trim() || String(Math.floor(Math.random() * 0x100000000));
  if (seed.length > 80) throw new Error("Seed must be at most 80 characters.");
  const random = createRandom(seedValue(seed));
  const switches = Object.fromEntries(
    Array.from({ length: settings.switchCount }, (_, index) => [`s${index + 1}`, index + 1]),
  );
  const switchNames = Object.keys(switches);
  const hosts: TopologyDefinitionInput["graph"]["hosts"] = {};
  const switchPorts: Record<string, number[]> = Object.fromEntries(switchNames.map((switchName) => [switchName, []]));
  const nextPort: Record<string, number> = Object.fromEntries(switchNames.map((switchName) => [switchName, 1]));
  const hostSwitches: string[] = [];

  for (let index = 0; index < settings.hostCount; index += 1) {
    const hostName = `h${index + 1}`;
    const switchName = switchNames[index % switchNames.length];
    const switchPort = nextPort[switchName];
    nextPort[switchName] += 1;
    switchPorts[switchName].push(switchPort);
    hostSwitches.push(switchName);
    const address = index + 1;
    const ip = `10.0.${Math.floor((address - 1) / 254)}.${((address - 1) % 254) + 1}`;
    const suffix = address.toString(16).padStart(12, "0");
    const mac = `02:${suffix.slice(2, 4)}:${suffix.slice(4, 6)}:${suffix.slice(6, 8)}:${suffix.slice(8, 10)}:${suffix.slice(10, 12)}`;
    hosts[hostName] = {
      name: hostName,
      ip,
      mac,
      switch: switchName,
      switch_port: switchPort,
      attachment_capacity_mbps: roundedBetween(random, settings.bandwidthMinMbps, settings.bandwidthMaxMbps),
      attachment_delay_ms: roundedBetween(random, settings.delayMinMs, settings.delayMaxMs),
      attachment_packet_loss_percent: roundedBetween(random, settings.packetLossMinPercent, settings.packetLossMaxPercent),
      attachment_admin_up: true,
    };
  }

  const pairs = connectedPairs(settings.switchCount, settings.pattern, random);
  const possibleExtraCount = (settings.switchCount * (settings.switchCount - 1)) / 2 - pairs.length;
  if (!Number.isInteger(settings.extraLinks) || settings.extraLinks < 0 || settings.extraLinks > possibleExtraCount) {
    throw new Error(`Extra links must be between 0 and ${possibleExtraCount} for this pattern and switch count.`);
  }
  const existing = new Set(pairs.map(([a, b]) => `${a}:${b}`));
  const remaining: [number, number][] = [];
  for (let left = 0; left < settings.switchCount; left += 1) {
    for (let right = left + 1; right < settings.switchCount; right += 1) {
      if (!existing.has(`${left}:${right}`)) remaining.push([left, right]);
    }
  }
  for (let index = remaining.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [remaining[index], remaining[swap]] = [remaining[swap], remaining[index]];
  }
  pairs.push(...remaining.slice(0, settings.extraLinks));

  const links: TopologyDefinitionInput["graph"]["links"] = pairs.map(([a, b]) => {
    const nodeA = switchNames[a];
    const nodeB = switchNames[b];
    const portA = nextPort[nodeA];
    const portB = nextPort[nodeB];
    nextPort[nodeA] += 1;
    nextPort[nodeB] += 1;
    switchPorts[nodeA].push(portA);
    switchPorts[nodeB].push(portB);
    return {
      node_a: nodeA,
      port_a: portA,
      node_b: nodeB,
      port_b: portB,
      bw_mbps: roundedBetween(random, settings.bandwidthMinMbps, settings.bandwidthMaxMbps),
      delay_ms: roundedBetween(random, settings.delayMinMs, settings.delayMaxMs),
      packet_loss_percent: roundedBetween(random, settings.packetLossMinPercent, settings.packetLossMaxPercent),
      admin_up: true,
      intf_a: null,
      intf_b: null,
    };
  });

  const positions: TopologyDefinitionInput["positions"] = {};
  const centerX = 500;
  const centerY = 360;
  const radius = Math.max(180, settings.switchCount * 32);
  switchNames.forEach((switchName, index) => {
    const angle = (2 * Math.PI * index) / settings.switchCount - Math.PI / 2;
    positions[switchName] = {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  });
  Object.keys(hosts).forEach((hostName, index) => {
    const switchName = hostSwitches[index];
    const switchIndex = switchNames.indexOf(switchName);
    const angle = (2 * Math.PI * switchIndex) / settings.switchCount - Math.PI / 2;
    const offset = 90 + Math.floor(index / settings.switchCount) * 55;
    positions[hostName] = {
      x: centerX + (radius + offset) * Math.cos(angle),
      y: centerY + (radius + offset) * Math.sin(angle),
    };
  });

  return {
    seed,
    topology: {
      name,
      mode: "DESIGN",
      graph: {
        switches,
        switch_ports: switchPorts,
        hosts,
        links,
      },
      positions,
    },
  };
}
