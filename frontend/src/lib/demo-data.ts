import type { CandidatePath, ExecutionRecord, NetworkMetric } from "@/types/dashboard";

export const demoMetrics: NetworkMetric[] = [
  { label: "Avg. latency", value: "2.1", unit: "ms", change: "−0.4 ms", state: "healthy" },
  { label: "Available bandwidth", value: "45.5", unit: "Mbps", change: "+3.2%", state: "healthy" },
  { label: "Packet loss", value: "0.02", unit: "%", change: "−0.01%", state: "healthy" },
  { label: "Active paths", value: "12", change: "2 optimized", state: "healthy" },
];

export const demoCandidates: CandidatePath[] = [
  {
    id: "physical-6ae1c9c3…",
    path: ["h1", "s1", "s2", "s4", "h4"],
    bottleneckMbps: 10,
    latencyMs: 2.238,
    bandwidthMbps: 9.47,
    packetLossPercent: 0,
    feasibility: "CANDIDATE",
    constraint: "VIOLATED",
    selection: "NOT_SELECTED",
    reason: "Measured throughput is below the 20 Mbps hard constraint.",
  },
  {
    id: "physical-dbcbec51…",
    path: ["h1", "s1", "s3", "s5", "s4", "h4"],
    bottleneckMbps: 50,
    latencyMs: 1.954,
    bandwidthMbps: 45.51,
    packetLossPercent: 0,
    feasibility: "CANDIDATE",
    constraint: "SATISFIED",
    selection: "SELECTED",
    reason: "Satisfies the bandwidth constraint and has the lowest measured latency.",
  },
  {
    id: "physical-84f30a12…",
    path: ["h1", "s1", "s3", "s5", "s4", "h4"],
    bottleneckMbps: 50,
    latencyMs: 2.14,
    bandwidthMbps: 44.92,
    packetLossPercent: 0.1,
    feasibility: "UNKNOWN",
    constraint: "UNKNOWN",
    selection: "SKIPPED",
    reason: "No current observation is available for this illustrative candidate.",
  },
];

export const demoExecutions: ExecutionRecord[] = [
  {
    id: "cc52186702694cd48f43c114cb7a52d3",
    intent: "Minimize latency while maintaining bandwidth above 20 Mbps",
    createdAt: "Today, 15:19",
    status: "SUCCEEDED",
    path: "h1 → s1 → s3 → s5 → s4 → h4",
    result: "2.483 ms avg. RTT · 45.14 Mbps",
    verification: "16 / 16 flows verified",
  },
  {
    id: "65a057a1098145b69798d31e8733a203",
    intent: "Maximize bandwidth between h1 and h4",
    createdAt: "Today, 15:18",
    status: "SUCCEEDED",
    path: "h1 → s1 → s3 → s5 → s4 → h4",
    result: "45.51 Mbps receiver throughput",
    verification: "16 / 16 flows verified",
  },
  {
    id: "3d429ec3e38a418da9080b346b56a0a9",
    intent: "Minimize latency between h1 and h4",
    createdAt: "Today, 14:01",
    status: "SUCCEEDED",
    path: "h1 → s1 → s3 → s5 → s4 → h4",
    result: "1.954 ms avg. RTT",
    verification: "16 / 16 flows verified",
  },
  {
    id: "5059d4848fb74e93a03071730465cdf9",
    intent: "Ensure bandwidth ≥ 20 Mbps and latency ≤ 50 ms",
    createdAt: "Yesterday, 11:42",
    status: "SUCCEEDED",
    path: "h1 → s1 → s3 → s5 → s4 → h4",
    result: "45.14 Mbps · 2.31 ms avg. RTT",
    verification: "16 / 16 flows verified",
  },
];

export const activityItems = [
  { label: "Deployment verification completed", detail: "16 / 16 flows · h1 → h4", time: "15:19:13", icon: "check" },
  { label: "Path selected", detail: "Minimum latency · 2.483 ms", time: "15:19:04", icon: "route" },
  { label: "Constraint evaluation completed", detail: "Bandwidth ≥ 20 Mbps · satisfied", time: "15:19:03", icon: "scale" },
  { label: "Candidate paths enumerated", detail: "2 physical paths discovered", time: "15:18:48", icon: "network" },
  { label: "Intent submitted", detail: "Constrained latency optimization", time: "15:18:48", icon: "send" },
];
