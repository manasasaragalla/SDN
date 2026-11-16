"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CircleDot,
  GitBranch,
  Network,
  Route,
  Send,
  Workflow,
} from "lucide-react";
import type { PageId } from "@/types/dashboard";
import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import { useActiveTopology } from "@/hooks/use-active-topology";
import { useBackendHealth } from "@/hooks/use-backend-health";
import { Panel, SectionHeading, StatusPill } from "@/components/ui/dashboard-ui";
import { Button } from "@/components/ui/button";
import type { ExecutionSummary, TopologyDefinition } from "@/types/api";

const unavailable = "Not available";

function statusTone(value: string) {
  if (value === "CONNECTED") return "positive" as const;
  if (value === "DISCONNECTED") return "negative" as const;
  return "warning" as const;
}

function intentLabel(record: ExecutionSummary): string {
  if (typeof record.submitted_intent === "string") return record.submitted_intent;
  const intent = record.submitted_intent;
  if (!intent) return "Intent details not recorded";
  if (typeof intent.natural_language === "string") return intent.natural_language;
  return "Structured intent";
}

function TopologySnapshot({ topology }: { topology: TopologyDefinition }) {
  const positions = topology.positions;
  const nodes = useMemo(() => [
    ...Object.entries(topology.graph.switches).map(([name, dpid]) => ({
      name,
      kind: "switch" as const,
      detail: `DPID ${dpid}`,
    })),
    ...Object.values(topology.graph.hosts).map((host) => ({
      name: host.name,
      kind: "host" as const,
      detail: `${host.ip} · ${host.switch}:${host.switch_port}`,
    })),
  ], [topology]);

  const viewBox = useMemo(() => {
    const values = Object.values(positions);
    if (!values.length) return "0 0 1000 500";
    const xs = values.map((point) => point.x);
    const ys = values.map((point) => point.y);
    const minX = Math.min(...xs) - 70;
    const minY = Math.min(...ys) - 60;
    const width = Math.max(300, Math.max(...xs) - minX + 70);
    const height = Math.max(180, Math.max(...ys) - minY + 60);
    return `${minX} ${minY} ${width} ${height}`;
  }, [positions]);

  const linkState = topology.graph.links.reduce(
    (counts, link) => {
      if (link.admin_up === true) counts.up += 1;
      else if (link.admin_up === false) counts.down += 1;
      else counts.unknown += 1;
      return counts;
    },
    { up: 0, down: 0, unknown: 0 },
  );

  return (
    <>
      <svg className="overview-topology-svg" viewBox={viewBox} role="img" aria-label={`${topology.name} configured topology`}>
        {topology.graph.links.map((link, index) => {
          const a = positions[link.node_a];
          const b = positions[link.node_b];
          if (!a || !b) return null;
          const stroke = link.admin_up === false
            ? "var(--error)"
            : link.admin_up === true
              ? "var(--success)"
              : "var(--steel)";
          return (
            <line
              key={`${link.node_a}:${link.port_a}:${link.node_b}:${link.port_b}:${index}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={stroke}
              strokeWidth="4"
              strokeDasharray={link.admin_up == null ? "8 7" : undefined}
            >
              <title>{`${link.node_a}:${link.port_a} ↔ ${link.node_b}:${link.port_b} · ${link.admin_up == null ? "admin state unknown" : link.admin_up ? "administratively up" : "administratively down"} · configured capacity ${link.bw_mbps == null ? "unavailable" : `${link.bw_mbps} Mbps`}`}</title>
            </line>
          );
        })}
        {Object.values(topology.graph.hosts).map((host) => {
          const a = positions[host.name];
          const b = positions[host.switch];
          if (!a || !b) return null;
          const up = host.attachment_admin_up;
          return (
            <line
              key={`attachment:${host.name}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={up === false ? "var(--error)" : up === true ? "var(--success)" : "var(--steel)"}
              strokeWidth="2"
              strokeDasharray={up == null ? "6 6" : "4 5"}
            >
              <title>{`${host.name} attachment to ${host.switch}:${host.switch_port} · ${up == null ? "admin state unknown" : up ? "administratively up" : "administratively down"}`}</title>
            </line>
          );
        })}
        {nodes.map((node) => {
          const point = positions[node.name];
          if (!point) return null;
          return (
            <g key={node.name} transform={`translate(${point.x}, ${point.y})`}>
              {node.kind === "switch"
                ? <rect x="-28" y="-19" width="56" height="38" rx="7" className="overview-switch-node" />
                : <circle r="19" className="overview-host-node" />}
              <text textAnchor="middle" dominantBaseline="central" className="overview-node-label">{node.name}</text>
              <title>{`${node.name} · ${node.kind} · ${node.detail}`}</title>
            </g>
          );
        })}
      </svg>
      <div className="overview-topology-legend">
        <span><i className="legend-dot green" /> Admin up: {linkState.up}</span>
        <span><i className="legend-dot red" /> Admin down: {linkState.down}</span>
        <span>Unknown admin state: {linkState.unknown}</span>
        <span>{topology.graph.links.length} inter-switch links</span>
      </div>
    </>
  );
}

export function OverviewPage({ navigate }: { navigate: (id: PageId) => void }) {
  const topologyState = useActiveTopology();
  const healthConnection = useBackendHealth();
  const [executions, setExecutions] = useState<ExecutionSummary[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    if (!API_BASE_URL) return;
    let active = true;
    apiRequest<ExecutionSummary[]>("/api/v1/executions")
      .then((records) => {
        if (active) {
          setExecutions(records.slice(0, 4));
          setHistoryError(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setHistoryError(error instanceof Error ? error.message : "Historical execution records are unavailable.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const topology = topologyState.status === "loaded" ? topologyState.topology : null;
  const inventory = [
    { label: "Switches", value: topology ? Object.keys(topology.graph.switches).length : unavailable, icon: Network, color: "blue" },
    { label: "Hosts", value: topology ? Object.keys(topology.graph.hosts).length : unavailable, icon: CircleDot, color: "violet" },
    { label: "Inter-switch links", value: topology ? topology.graph.links.length : unavailable, icon: GitBranch, color: "teal" },
    { label: "Active flows", value: unavailable, icon: Workflow, color: "amber" },
  ];

  const health = healthConnection.state === "connected" ? healthConnection.health : null;
  const endpointStatus = health
    ? health.backend_status
    : healthConnection.state === "disconnected"
      ? "DISCONNECTED"
      : "UNKNOWN";

  return (
    <div className="page-stack">
      <div className="demo-banner">
        <div className="demo-banner-icon"><Network size={17} /></div>
        <div>
          <strong>{topology ? `Active topology · ${topology.name}` : "Active topology unavailable"}</strong>
          <span>
            {topology
              ? `${topology.mode} v${topology.version} · configured topology data, not live network state.`
              : topologyState.status === "error"
                ? topologyState.error
                : topologyState.status === "demo"
                  ? "Configure the backend API to load the active topology."
                  : "Loading active topology from the backend."}
          </span>
        </div>
      </div>

      <section>
        <SectionHeading title="Network inventory" description="Counts from the active topology definition; flow state is not exposed as topology inventory." />
        <div className="stat-grid">
          {inventory.map(({ label, value, icon: Icon, color }) => (
            <Panel key={label} className="stat-card">
              <div className={`stat-icon icon-${color}`}><Icon size={18} /></div>
              <div className="stat-copy">
                <span>{label}</span>
                <strong>{value}</strong>
                <small>{label === "Active flows" ? "No current flow inventory available" : topology ? `${topology.mode} topology definition` : "Active topology not loaded"}</small>
              </div>
            </Panel>
          ))}
        </div>
      </section>

      <section>
        <SectionHeading title="Service connectivity" description="API, controller and Mininet status are reported independently." />
        <div className="overview-service-grid">
          {[
            { name: "Backend API", value: endpointStatus },
            { name: "Ryu controller", value: health?.ryu_status ?? "UNKNOWN" },
            { name: "Mininet / OVS", value: health?.mininet_status ?? "UNKNOWN" },
          ].map((item) => (
            <Panel className="overview-service-card" key={item.name}>
              <span>{item.name}</span>
              <StatusPill tone={statusTone(item.value)}>{item.value}</StatusPill>
            </Panel>
          ))}
        </div>
        {healthConnection.state === "disconnected" && <p className="overview-note" role="status">{healthConnection.error}</p>}
      </section>

      <div className="overview-lower">
        <Panel className="topology-overview">
          <div className="panel-title-row">
            <div>
              <h3>Active topology snapshot</h3>
              <p>{topology ? `${topology.name} · ${topology.mode} v${topology.version}` : "No active topology definition loaded"}</p>
            </div>
            <button className="text-button" onClick={() => navigate("topology")}>Explore topology <ArrowRight size={14} /></button>
          </div>
          {topology
            ? <TopologySnapshot topology={topology} />
            : <div className="timeline-unavailable">{topologyState.status === "error" ? topologyState.error : "Create or activate a topology in Network Topology to display its graph here."}</div>}
          {topology && <p className="overview-note">Administrative link state is configuration metadata. DESIGN topology does not establish that a link is running.</p>}
        </Panel>

        <Panel className="activity-panel">
          <div className="panel-title-row">
            <div><h3>Historical executions</h3><p>Persisted backend records; not current network state.</p></div>
            <StatusPill tone={historyError ? "negative" : "info"}>{historyError ? "Unavailable" : "Backend history"}</StatusPill>
          </div>
          {historyError
            ? <div className="timeline-unavailable">{historyError}</div>
            : !API_BASE_URL
              ? <div className="timeline-unavailable">Backend history is unavailable in local demo mode.</div>
              : executions.length === 0
                ? <div className="timeline-unavailable">No persisted execution records were returned.</div>
                : <div className="activity-list">{executions.map((record) => (
                  <div className="activity-item" key={record.execution_id}>
                    <div className="activity-icon"><Route size={14} /></div>
                    <div className="activity-content">
                      <strong>{intentLabel(record)}</strong>
                      <span>{record.status} · historical record · {record.selected_path?.join(" → ") ?? "No selected path recorded"}</span>
                    </div>
                    <time>{record.started_at ? new Date(record.started_at).toLocaleString() : "Time unavailable"}</time>
                  </div>
                ))}</div>}
          <button className="activity-footer" onClick={() => navigate("executions")}>View execution history <ArrowRight size={14} /></button>
        </Panel>
      </div>

      <div className="quick-actions">
        <div><strong>What would you like to do?</strong><span>Submit a network requirement or inspect current paths.</span></div>
        <Button variant="primary" className="button-primary" onClick={() => navigate("intents")}><Send size={15} /> Create an intent</Button>
        <Button variant="secondary" className="button-secondary" onClick={() => navigate("planning")}><Route size={15} /> View path planning</Button>
      </div>
    </div>
  );
}
