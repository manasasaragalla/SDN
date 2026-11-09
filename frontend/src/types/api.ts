export type ApiAvailability = "CONNECTED" | "DISCONNECTED" | "UNKNOWN";

export interface ApiHealth {
  api_status: "CONNECTED";
  backend_status: ApiAvailability;
  ryu_status: ApiAvailability;
  mininet_status: ApiAvailability;
  current_execution_status: string;
  checked_at: string;
  details: Record<string, string | null>;
}

export interface CanonicalConstraint {
  metric: string;
  comparison: "GT" | "GTE" | "LT" | "LTE" | "EQ" | "BETWEEN";
  unit: string;
  value: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
}

export interface CanonicalIntent {
  schema_version: 1;
  scope: {
    source: string;
    destination: string;
    selector: {
      protocol: string | null;
      source_port: number | null;
      destination_port: number | null;
    } | null;
  };
  constraints: CanonicalConstraint[];
  optimization: {
    metric: string;
    direction: "MINIMIZE" | "MAXIMIZE";
    unit: string;
  } | null;
  requested_actions: { name: string; parameters: Record<string, unknown> }[];
  legacy_metadata: { loss_tolerance: string | null } | null;
}

export interface IntentPreviewRequest {
  natural_language?: string;
  structured_intent?: CanonicalIntent;
  source: string;
  destination: string;
}

export interface IntentPreviewResponse {
  preview_id: string;
  parser: string;
  parser_kind: "PROVIDER" | "MOCK" | "STRUCTURED";
  canonical_intent: CanonicalIntent;
  capability_resolution: {
    eligibility: "CAPABILITY_READY" | "CONDITIONAL" | "INELIGIBLE";
    reasons: string[];
    [key: string]: unknown;
  };
  execution_eligible: boolean;
  topology_status: ApiAvailability;
  topology_identity: TopologyIdentity | null;
  planning_result: TopologyPlanningResult | null;
  unsupported_or_conditional: string[];
  explanation: string[];
}

export interface TopologyIdentity {
  id: string | null;
  name: string;
  version: number | null;
  mode: "DESIGN" | "MININET" | "LIVE";
  fingerprint: string;
  snapshot_timestamp?: string;
  snapshot_status?: string;
}

export interface TopologyHostDefinition {
  name: string;
  ip: string;
  mac: string;
  switch: string;
  switch_port: number;
  attachment_capacity_mbps: number | null;
  attachment_delay_ms: number | null;
  attachment_packet_loss_percent: number | null;
  attachment_admin_up: boolean | null;
}

export interface TopologyLinkDefinition {
  node_a: string;
  port_a: number;
  node_b: string;
  port_b: number;
  bw_mbps: number | null;
  delay_ms: number | null;
  packet_loss_percent: number | null;
  admin_up: boolean | null;
  intf_a: string | null;
  intf_b: string | null;
}

export interface TopologyGraphDefinition {
  switches: Record<string, number>;
  switch_ports: Record<string, number[]>;
  hosts: Record<string, TopologyHostDefinition>;
  links: TopologyLinkDefinition[];
}

export interface TopologyDefinitionInput {
  name: string;
  mode: "DESIGN";
  graph: TopologyGraphDefinition;
  positions: Record<string, { x: number; y: number }>;
}

export interface TopologyDefinition extends TopologyDefinitionInput {
  id: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface TopologyCatalogItem {
  id: string;
  name: string;
  version: number;
  mode: "DESIGN" | "MININET" | "LIVE";
  active: boolean;
  node_count: number;
  link_count: number;
  updated_at: string;
}

export interface ActiveTopologyResponse {
  topology: TopologyDefinition | null;
  active: boolean;
}

export interface TopologyPlanningCandidate {
  candidate_id: string;
  path: string[];
  physical_links: {
    node_a: string;
    port_a: number | null;
    node_b: string;
    port_b: number | null;
    capacity_mbps: number | null;
    delay_ms: number | null;
    packet_loss_percent: number | null;
    admin_up: boolean | null;
  }[];
  configured_metrics: {
    bandwidth_mbps: number | null;
    latency_ms: number | null;
    packet_loss_percent: number | null;
  };
  constraints: {
    metric: string;
    comparison: string;
    unit: string;
    threshold: number | number[] | null;
    configured_value: number | null;
    status: "SATISFIED" | "VIOLATED" | "UNKNOWN";
    reason: string;
  }[];
  status: "ELIGIBLE" | "REJECTED" | "UNKNOWN";
  selection: "SELECTED" | "NOT_SELECTED";
  reasons: string[];
}

export interface TopologyPlanningResult {
  topology_identity?: TopologyIdentity;
  source: string;
  destination: string;
  optimization: CanonicalIntent["optimization"];
  constraints: CanonicalConstraint[];
  status: "SELECTED" | "NO_PATH" | "NO_ELIGIBLE_PATH" | "INSUFFICIENT_CONFIGURED_DATA" | "INCOMPLETE_SEARCH";
  candidate_count: number;
  candidate_limit: number;
  truncated: boolean;
  selected_candidate_id: string | null;
  selection_reason: string | null;
  candidates: TopologyPlanningCandidate[];
  provenance: string;
}

export interface ExecutionAcceptedResponse {
  execution_id: string;
  status: "RUNNING";
  accepted_at: string;
  events_url: string;
}

export interface TopologyResponse {
  switches: {
    name: string;
    dpid: number;
    status: ApiAvailability;
  }[];
  hosts: {
    name: string;
    ip: string;
    mac: string;
    switch: string;
    switch_port: number;
  }[];
  links: {
    node_a: string;
    port_a: number | null;
    node_b: string;
    port_b: number;
    capacity_mbps: number | null;
    delay_ms?: number | null;
    packet_loss_percent?: number | null;
    admin_up?: boolean | null;
    status: ApiAvailability;
  }[];
  mode?: "LIVE";
  topology_fingerprint: string;
  snapshot_timestamp: string;
  snapshot_status: string;
  source: string;
}

export interface ExecutionSummary {
  execution_id: string;
  submitted_intent: Record<string, unknown> | string | null;
  started_at: string | null;
  completed_at: string | null;
  status: string;
  selected_path: string[] | null;
  final_measurement: Record<string, unknown> | null;
  evidence_json: string | null;
  evidence_markdown: string | null;
}

export interface ExecutionDetail extends ExecutionSummary {
  evidence: Record<string, unknown> | null;
}

export interface ExecutionEvent {
  execution_id: string;
  event:
    | "EXECUTION_ACCEPTED"
    | "EXECUTION_RUNNING"
    | "EXECUTION_SUCCEEDED"
    | "EXECUTION_COMPLETED"
    | "EXECUTION_FAILED";
  timestamp: string;
  detail: string | null;
}

export interface ExecutionStatusResponse {
  execution_id: string;
  status: string;
  events: ExecutionEvent[];
}
