export type PageId =
  | "overview"
  | "topology"
  | "intents"
  | "planning"
  | "metrics"
  | "executions"
  | "settings";

export type HealthState = "healthy" | "warning" | "critical" | "unknown";

export interface NetworkMetric {
  label: string;
  value: string;
  unit?: string;
  change?: string;
  state?: HealthState;
}

export interface CandidatePath {
  id: string;
  path: string[];
  bottleneckMbps: number;
  latencyMs: number | null;
  bandwidthMbps: number | null;
  packetLossPercent: number | null;
  feasibility: "CANDIDATE" | "PROVEN_INFEASIBLE" | "UNKNOWN";
  constraint: "SATISFIED" | "VIOLATED" | "UNKNOWN" | "SKIPPED";
  selection: "SELECTED" | "SKIPPED" | "NOT_SELECTED";
  reason: string;
}

export interface ExecutionRecord {
  id: string;
  intent: string;
  createdAt: string;
  status: "SUCCEEDED" | "RUNNING" | "FAILED" | "NO_FEASIBLE_CANDIDATE" | "NO_SATISFYING_CANDIDATE";
  path: string;
  result: string;
  verification: string;
}
