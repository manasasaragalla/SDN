"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  Download,
  FileJson2,
  Info,
  Link2,
  Plus,
  Router,
  Save,
  Server,
  Upload,
  X,
} from "lucide-react";
import { Panel, StatusPill } from "@/components/ui/dashboard-ui";
import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import type {
  ActiveTopologyResponse,
  TopologyCatalogItem,
  TopologyDefinition,
  TopologyDefinitionInput,
  TopologyLinkDefinition,
  TopologyResponse,
} from "@/types/api";

type NetworkData = {
  label: string;
  kind: "host" | "switch";
  detail: string;
  status?: string;
  ip?: string;
  mac?: string;
  switchName?: string;
  switchPort?: number;
  attachmentCapacity?: number | null;
  attachmentDelay?: number | null;
  attachmentLoss?: number | null;
  attachmentAdminUp?: boolean | null;
  dpid?: number;
  ports?: number[];
};
type NetworkNodeType = Node<NetworkData, "network">;
type NetworkEdgeData = {
  status: string;
  capacity_mbps: number | null;
  delay_ms: number | null;
  packet_loss_percent: number | null;
  admin_up: boolean | null;
  source_port: number | null;
  target_port: number | null;
  attachment: boolean;
};
type NetworkEdgeType = Edge<NetworkEdgeData>;

const defaultEdgeData = (): NetworkEdgeData => ({
  status: "UNKNOWN",
  capacity_mbps: null,
  delay_ms: null,
  packet_loss_percent: null,
  admin_up: true,
  source_port: null,
  target_port: null,
  attachment: false,
});
const edgeStyle = { stroke: "var(--steel)", strokeWidth: 2 };
const selectedEdgeStyle = { stroke: "var(--accent)", strokeWidth: 2.5 };

function NetworkNode({ data, selected }: NodeProps<NetworkNodeType>) {
  const isHost = data.kind === "host";
  return (
    <div className={`flow-node ${isHost ? "flow-host" : "flow-switch"} ${selected ? "flow-node-selected" : ""}`}>
      <Handle type="target" position={Position.Left} className="flow-handle" />
      <div className="flow-node-icon">{isHost ? <Server size={17} /> : <Router size={18} />}</div>
      <div className="flow-node-name">{data.label}</div>
      <div className="flow-node-kind">{isHost ? "HOST" : "SWITCH"}</div>
      <Handle type="source" position={Position.Right} className="flow-handle" />
    </div>
  );
}

const nodeTypes = { network: NetworkNode };

function graphToFlow(
  definition: Pick<TopologyDefinition, "graph" | "positions">,
): { nodes: NetworkNodeType[]; edges: NetworkEdgeType[] } {
  const nodes: NetworkNodeType[] = [];
  const edges: NetworkEdgeType[] = [];
  const { graph, positions } = definition;
  for (const [name, dpid] of Object.entries(graph.switches)) {
    nodes.push({
      id: name,
      type: "network",
      position: positions[name] ?? { x: 180 + nodes.length * 150, y: 180 },
      data: {
        label: name,
        kind: "switch",
        dpid,
        ports: graph.switch_ports[name] ?? [],
        detail: `DPID ${dpid} · OpenFlow switch`,
      },
    });
  }
  for (const host of Object.values(graph.hosts)) {
    nodes.push({
      id: host.name,
      type: "network",
      position: positions[host.name] ?? { x: 30 + nodes.length * 30, y: 100 },
      data: {
        label: host.name,
        kind: "host",
        ip: host.ip,
        mac: host.mac,
        switchName: host.switch,
        switchPort: host.switch_port,
        attachmentCapacity: host.attachment_capacity_mbps,
        attachmentDelay: host.attachment_delay_ms,
        attachmentLoss: host.attachment_packet_loss_percent,
        attachmentAdminUp: host.attachment_admin_up ?? true,
        detail: `${host.ip} · ${host.mac} · Attached to ${host.switch}:${host.switch_port}`,
      },
    });
    edges.push({
      id: `attachment:${host.name}`,
      source: host.name,
      target: host.switch,
      label: host.attachment_capacity_mbps == null
        ? "host attachment"
        : `${host.attachment_capacity_mbps} Mbps`,
      type: "smoothstep",
      style: edgeStyle,
      data: {
        ...defaultEdgeData(),
        status: host.attachment_admin_up === false ? "DISCONNECTED" : "DESIGN",
        capacity_mbps: host.attachment_capacity_mbps,
        delay_ms: host.attachment_delay_ms,
        packet_loss_percent: host.attachment_packet_loss_percent,
        admin_up: host.attachment_admin_up ?? true,
        target_port: host.switch_port,
        attachment: true,
      },
    });
  }
  graph.links.forEach((link, index) => {
    edges.push({
      id: `link:${link.node_a}:${link.port_a}:${link.node_b}:${link.port_b}:${index}`,
      source: link.node_a,
      target: link.node_b,
      label: link.bw_mbps == null ? "link" : `${link.bw_mbps} Mbps`,
      type: "smoothstep",
      style: link.admin_up === false ? { stroke: "var(--error)", strokeWidth: 2 } : edgeStyle,
      data: {
        ...defaultEdgeData(),
        status: link.admin_up === false ? "DISCONNECTED" : "DESIGN",
        capacity_mbps: link.bw_mbps,
        delay_ms: link.delay_ms,
        packet_loss_percent: link.packet_loss_percent,
        admin_up: link.admin_up ?? true,
        source_port: link.port_a,
        target_port: link.port_b,
        attachment: false,
      },
    });
  });
  return { nodes, edges };
}

function liveTopologyToFlow(topology: TopologyResponse): {
  nodes: NetworkNodeType[];
  edges: NetworkEdgeType[];
} {
  const positions = new Map<string, { x: number; y: number }>();
  topology.switches.forEach((item, index) => {
    positions.set(item.name, {
      x: 230 + (index % 4) * 195,
      y: 100 + Math.floor(index / 4) * 170,
    });
  });
  const nodes: NetworkNodeType[] = topology.switches.map((item) => ({
    id: item.name,
    type: "network",
    position: positions.get(item.name) ?? { x: 240, y: 180 },
    data: {
      label: item.name,
      kind: "switch",
      dpid: item.dpid,
      ports: [],
      detail: `DPID ${item.dpid} · OpenFlow switch`,
      status: item.status,
    },
  }));
  for (const [index, host] of topology.hosts.entries()) {
    const attached = positions.get(host.switch) ?? { x: 400, y: 180 };
    nodes.push({
      id: host.name,
      type: "network",
      position: { x: attached.x - 100, y: attached.y + (index % 3) * 85 - 40 },
      data: {
        label: host.name,
        kind: "host",
        ip: host.ip,
        mac: host.mac,
        switchName: host.switch,
        switchPort: host.switch_port,
        detail: `${host.ip} · ${host.mac} · Attached to ${host.switch}:${host.switch_port}`,
        status: topology.links.find((link) => link.node_a === host.name)?.status,
      },
    });
  }
  const edges: NetworkEdgeType[] = topology.links.map((link, index) => ({
    id: `live:${link.node_a}:${link.port_a ?? "host"}:${link.node_b}:${link.port_b}:${index}`,
    source: link.node_a,
    target: link.node_b,
    label: link.capacity_mbps == null ? "host attachment" : `${link.capacity_mbps} Mbps`,
    type: "smoothstep",
    style: link.status === "CONNECTED" ? edgeStyle : { stroke: "var(--text-muted)", strokeWidth: 2 },
    data: {
      ...defaultEdgeData(),
      status: link.status,
      capacity_mbps: link.capacity_mbps,
      delay_ms: link.delay_ms ?? null,
      packet_loss_percent: link.packet_loss_percent ?? null,
      admin_up: link.admin_up ?? null,
      source_port: link.port_a,
      target_port: link.port_b,
      attachment: link.port_a == null,
    },
  }));
  return { nodes, edges };
}

function definitionFromFlow(
  name: string,
  nodes: NetworkNodeType[],
  edges: NetworkEdgeType[],
): TopologyDefinitionInput {
  const switches = Object.fromEntries(
    nodes
      .filter((node) => node.data.kind === "switch")
      .map((node) => [node.id, Number(node.data.dpid)]),
  );
  const switch_ports = Object.fromEntries(
    nodes
      .filter((node) => node.data.kind === "switch")
      .map((node) => [node.id, [...new Set(node.data.ports ?? [])].sort((a, b) => a - b)]),
  );
  const hosts = Object.fromEntries(
    nodes
      .filter((node) => node.data.kind === "host")
      .map((node) => [
        node.id,
        {
          name: node.id,
          ip: node.data.ip ?? "",
          mac: node.data.mac ?? "",
          switch: node.data.switchName ?? "",
          switch_port: Number(node.data.switchPort),
          attachment_capacity_mbps: node.data.attachmentCapacity ?? null,
          attachment_delay_ms: node.data.attachmentDelay ?? null,
          attachment_packet_loss_percent: node.data.attachmentLoss ?? null,
          attachment_admin_up: node.data.attachmentAdminUp ?? true,
        },
      ]),
  );
  const links: TopologyLinkDefinition[] = edges
    .filter((edge) => {
      const source = nodes.find((node) => node.id === edge.source);
      const target = nodes.find((node) => node.id === edge.target);
      return source?.data.kind === "switch" && target?.data.kind === "switch";
    })
    .map((edge) => ({
      node_a: edge.source,
      port_a: Number(edge.data?.source_port),
      node_b: edge.target,
      port_b: Number(edge.data?.target_port),
      bw_mbps: edge.data?.capacity_mbps ?? null,
      delay_ms: edge.data?.delay_ms ?? null,
      packet_loss_percent: edge.data?.packet_loss_percent ?? null,
      admin_up: edge.data?.admin_up ?? true,
      intf_a: null,
      intf_b: null,
    }));
  return {
    name,
    mode: "DESIGN",
    graph: { switches, switch_ports, hosts, links },
    positions: Object.fromEntries(
      nodes.map((node) => [node.id, { x: node.position.x, y: node.position.y }]),
    ),
  };
}

function nextName(prefix: string, names: string[]): string {
  let index = 1;
  while (names.includes(`${prefix}${index}`)) index += 1;
  return `${prefix}${index}`;
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function nextHostAddress(nodes: NetworkNodeType[]): { ip: string; mac: string } | null {
  const hosts = nodes.filter((node) => node.data.kind === "host");
  const usedIps = new Set(hosts.map((node) => node.data.ip));
  const usedMacs = new Set(hosts.map((node) => node.data.mac?.toLowerCase()));
  for (let address = 1; address <= 254 * 255; address += 1) {
    const thirdOctet = Math.floor((address - 1) / 254);
    const fourthOctet = (address - 1) % 254 + 1;
    const ip = `10.0.${thirdOctet}.${fourthOctet}`;
    const suffix = address.toString(16).padStart(6, "0");
    const mac = `02:00:00:${suffix.slice(0, 2)}:${suffix.slice(2, 4)}:${suffix.slice(4)}`;
    if (!usedIps.has(ip) && !usedMacs.has(mac)) return { ip, mac };
  }
  return null;
}

export function TopologyPage() {
  const [nodes, setNodes, onNodesChange] = useNodesState<NetworkNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<NetworkEdgeType>([]);
  const [catalog, setCatalog] = useState<TopologyCatalogItem[]>([]);
  const [definition, setDefinition] = useState<TopologyDefinition | null>(null);
  const [topologyName, setTopologyName] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [versions, setVersions] = useState<TopologyDefinition[]>([]);
  const [dirty, setDirty] = useState(false);
  const [viewMode, setViewMode] = useState<"DESIGN" | "LIVE">("DESIGN");
  const [liveTopology, setLiveTopology] = useState<TopologyResponse | null>(null);
  const [selected, setSelected] = useState<{ type: "node" | "edge"; id: string } | null>(null);
  const [nodeNameDraft, setNodeNameDraft] = useState("");
  const [sourceNode, setSourceNode] = useState("");
  const [targetNode, setTargetNode] = useState("");
  const [sourcePort, setSourcePort] = useState("1");
  const [targetPort, setTargetPort] = useState("2");
  const [capacity, setCapacity] = useState("");
  const [delay, setDelay] = useState("");
  const [loss, setLoss] = useState("");
  const [linkAdminUp, setLinkAdminUp] = useState(true);
  const [loading, setLoading] = useState(Boolean(API_BASE_URL));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const importRef = useRef<HTMLInputElement>(null);

  const selectedNode = useMemo(
    () => selected?.type === "node" ? nodes.find((node) => node.id === selected.id) ?? null : null,
    [nodes, selected],
  );
  const selectedEdge = useMemo(
    () => selected?.type === "edge" ? edges.find((edge) => edge.id === selected.id) ?? null : null,
    [edges, selected],
  );
  const switchNodes = useMemo(
    () => nodes.filter((node) => node.data.kind === "switch"),
    [nodes],
  );
  const active = Boolean(definition && definition.id === activeId && definition.version === activeVersion);
  const editable = viewMode === "DESIGN";
  const readOnlyVersion = Boolean(
    definition && versions.length && definition.version !== versions[0].version,
  );

  const applyDefinition = useCallback((item: TopologyDefinition) => {
    const flow = graphToFlow(item);
    setDefinition(item);
    setTopologyName(item.name);
    setNodes(flow.nodes);
    setEdges(flow.edges);
    setSelected(null);
    setNodeNameDraft("");
    setDirty(false);
    setViewMode("DESIGN");
  }, [setEdges, setNodes]);

  const loadDefinition = useCallback(async (id: string, version?: number) => {
    const item = await apiRequest<TopologyDefinition>(
      `/api/v1/topologies/${encodeURIComponent(id)}${version ? `?version=${version}` : ""}`,
    );
    applyDefinition(item);
    const history = await apiRequest<{ versions: TopologyDefinition[] }>(
      `/api/v1/topologies/${encodeURIComponent(id)}/versions`,
    );
    setVersions(history.versions);
  }, [applyDefinition]);

  const refreshCatalog = useCallback(async () => {
    if (!API_BASE_URL) return;
    try {
      const [list, current] = await Promise.all([
        apiRequest<{ topologies: TopologyCatalogItem[] }>("/api/v1/topologies"),
        apiRequest<ActiveTopologyResponse>("/api/v1/topologies/active"),
      ]);
      setCatalog(list.topologies);
      setActiveId(current.topology?.id ?? null);
      setActiveVersion(current.topology?.version ?? null);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology catalog could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadInitialCatalog = async () => {
      try {
        const [list, current] = await Promise.all([
          apiRequest<{ topologies: TopologyCatalogItem[] }>("/api/v1/topologies"),
          apiRequest<ActiveTopologyResponse>("/api/v1/topologies/active"),
        ]);
        let selected = current.topology;
        if (!selected && list.topologies.length) {
          selected = await apiRequest<TopologyDefinition>(
            `/api/v1/topologies/${encodeURIComponent(list.topologies[0].id)}`,
          );
        }
        const history = selected
          ? await apiRequest<{ versions: TopologyDefinition[] }>(
              `/api/v1/topologies/${encodeURIComponent(selected.id)}/versions`,
            )
          : { versions: [] };
        if (cancelled) return;
        setCatalog(list.topologies);
        setActiveId(current.topology?.id ?? null);
        setActiveVersion(current.topology?.version ?? null);
        if (selected) {
          applyDefinition(selected);
          setVersions(history.versions);
        } else {
          setDefinition(null);
          setTopologyName("Untitled topology");
          setNodes([]);
          setEdges([]);
          setVersions([]);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Topology catalog could not be loaded.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void loadInitialCatalog();
    return () => {
      cancelled = true;
    };
  }, [applyDefinition, setEdges, setNodes]);

  const markDirty = () => {
    setDirty(true);
    setError(null);
  };
  const handleNodesChange: typeof onNodesChange = (changes) => {
    onNodesChange(changes);
    if (changes.some((change) => change.type === "position" && change.position)) markDirty();
  };
  const handleEdgesChange: typeof onEdgesChange = (changes) => {
    onEdgesChange(changes);
    if (changes.some((change) => change.type === "remove" || change.type === "select")) {
      if (changes.some((change) => change.type === "remove")) markDirty();
    }
  };

  const updateNode = (nodeId: string, updates: Partial<NetworkData>) => {
    setNodes((current) => current.map((node) =>
      node.id === nodeId ? { ...node, data: { ...node.data, ...updates } } : node,
    ));
    setEdges((current) => current.map((edge) => {
      if (edge.id !== `attachment:${nodeId}`) return edge;
      return {
        ...edge,
        target: updates.switchName ?? edge.target,
        label: updates.attachmentCapacity !== undefined && updates.attachmentCapacity !== null
          ? `${updates.attachmentCapacity} Mbps`
          : edge.label,
        data: {
          ...defaultEdgeData(),
          ...edge.data,
          target_port: updates.switchPort ?? edge.data?.target_port ?? null,
          capacity_mbps: updates.attachmentCapacity !== undefined
            ? updates.attachmentCapacity
            : edge.data?.capacity_mbps ?? null,
          delay_ms: updates.attachmentDelay !== undefined
            ? updates.attachmentDelay
            : edge.data?.delay_ms ?? null,
          packet_loss_percent: updates.attachmentLoss !== undefined
            ? updates.attachmentLoss
            : edge.data?.packet_loss_percent ?? null,
          admin_up: updates.attachmentAdminUp ?? edge.data?.admin_up ?? true,
        },
      };
    }));
    markDirty();
  };

  const updateEdge = (edgeId: string, updates: Partial<NetworkEdgeData>) => {
    setEdges((current) => current.map((edge) =>
      edge.id === edgeId
        ? {
            ...edge,
            label: updates.capacity_mbps !== undefined
              ? updates.capacity_mbps == null ? "link" : `${updates.capacity_mbps} Mbps`
              : edge.label,
            style: updates.admin_up === false ? { stroke: "var(--error)", strokeWidth: 2 } : edgeStyle,
            data: { ...defaultEdgeData(), ...edge.data, ...updates },
          }
        : edge,
    ));
    if (selectedEdge?.data?.attachment) {
      const hostId = selectedEdge.source;
      const node = nodes.find((item) => item.id === hostId);
      if (node?.data.kind === "host") {
        setNodes((current) => current.map((item) =>
          item.id === hostId
            ? {
                ...item,
                data: {
                  ...item.data,
                  switchName: selectedEdge.target,
                  switchPort: updates.target_port ?? selectedEdge.data?.target_port ?? item.data.switchPort,
                  attachmentCapacity: updates.capacity_mbps ?? item.data.attachmentCapacity,
                  attachmentDelay: updates.delay_ms ?? item.data.attachmentDelay,
                  attachmentLoss: updates.packet_loss_percent ?? item.data.attachmentLoss,
                  attachmentAdminUp: updates.admin_up ?? item.data.attachmentAdminUp,
                },
              }
            : item,
        ));
      }
    }
    markDirty();
  };

  const applyNodeName = () => {
    if (!selectedNode || !nodeNameDraft.trim() || nodeNameDraft === selectedNode.id) return;
    const newId = nodeNameDraft.trim();
    if (nodes.some((node) => node.id === newId)) {
      setError(`A node named ${newId} already exists.`);
      return;
    }
    setNodes((current) => current.map((node) => {
      if (node.id === selectedNode.id) {
        return { ...node, id: newId, data: { ...node.data, label: newId } };
      }
      if (node.data.kind === "host" && node.data.switchName === selectedNode.id) {
        return { ...node, data: { ...node.data, switchName: newId } };
      }
      return node;
    }));
    setEdges((current) => current.map((edge) => {
      const source = edge.source === selectedNode.id ? newId : edge.source;
      const target = edge.target === selectedNode.id ? newId : edge.target;
      const id = edge.data?.attachment
        ? `attachment:${source}`
        : `link:${source}:${edge.data?.source_port}:${target}:${edge.data?.target_port}`;
      return { ...edge, id, source, target };
    }));
    setSelected({ type: "node", id: newId });
    setNodeNameDraft(newId);
    markDirty();
  };

  const addSwitch = () => {
    const name = nextName("s", nodes.map((node) => node.id));
    const dpid = Math.max(0, ...nodes.map((node) => node.data.dpid ?? 0)) + 1;
    setNodes((current) => [...current, {
      id: name,
      type: "network",
      position: { x: 280 + current.length % 4 * 150, y: 90 + Math.floor(current.length / 4) * 145 },
      data: { label: name, kind: "switch", dpid, ports: [1, 2, 3, 4, 5, 6, 7, 8], detail: `DPID ${dpid} · OpenFlow switch` },
    }]);
    setSelected({ type: "node", id: name });
    setNodeNameDraft(name);
    markDirty();
  };

  const addHost = () => {
    const switchNode = switchNodes[0];
    if (!switchNode) {
      setError("Add a switch before adding a host.");
      return;
    }
    const name = nextName("h", nodes.map((node) => node.id));
    const occupied = new Set(
      nodes
        .filter((node) => node.data.kind === "host" && node.data.switchName === switchNode.id)
        .map((node) => node.data.switchPort),
    );
    const switchPortInventory = switchNode.data.ports ?? [];
    let port: number;
    if (switchPortInventory.length) {
      const availablePort = switchPortInventory.find((candidate) => !occupied.has(candidate));
      if (availablePort === undefined) {
        setError(`Switch ${switchNode.id} has no free configured ports. Add ports to its inventory first.`);
        return;
      }
      port = availablePort;
    } else {
      port = 1;
      while (occupied.has(port)) port += 1;
    }
    const address = nextHostAddress(nodes);
    if (!address) {
      setError("No unused default IPv4/MAC address is available. Edit an existing host or import a larger address plan.");
      return;
    }
    const host: NetworkNodeType = {
      id: name,
      type: "network",
      position: { x: 35 + (nodes.length % 3) * 100, y: 120 + Math.floor(nodes.length / 3) * 100 },
      data: {
        label: name,
        kind: "host",
        ip: address.ip,
        mac: address.mac,
        switchName: switchNode.id,
        switchPort: port,
        attachmentAdminUp: true,
        detail: `${address.ip} · Attached to ${switchNode.id}:${port}`,
      },
    };
    setNodes((current) => current.map((node) =>
      node.id === switchNode.id
        ? { ...node, data: { ...node.data, ports: [...new Set([...(node.data.ports ?? []), port])] } }
        : node,
    ).concat(host));
    setEdges((current) => [...current, {
      id: `attachment:${name}`,
      source: name,
      target: switchNode.id,
      label: "host attachment",
      type: "smoothstep",
      style: edgeStyle,
      data: { ...defaultEdgeData(), attachment: true, target_port: port },
    }]);
    setSelected({ type: "node", id: name });
    setNodeNameDraft(name);
    markDirty();
  };

  const createConnection = () => {
    const first = nodes.find((node) => node.id === sourceNode);
    const second = nodes.find((node) => node.id === targetNode);
    if (!first || !second || first.id === second.id) {
      setError("Choose two different existing nodes to connect.");
      return;
    }
    if (first.data.kind === "host" && second.data.kind === "host") {
      setError("Host-to-host links are not supported; attach each host to a switch.");
      return;
    }
    const portA = Number(sourcePort);
    const portB = Number(targetPort);
    if (!Number.isInteger(portA) || portA <= 0 || !Number.isInteger(portB) || portB <= 0) {
      setError("Both switch-side ports must be positive integers.");
      return;
    }
    const hostToMove = first.data.kind === "host"
      ? first.id
      : second.data.kind === "host"
        ? second.id
        : null;
    const switchPorts: [string, number][] =
      first.data.kind === "switch" && second.data.kind === "switch"
        ? [[first.id, portA], [second.id, portB]]
        : [[
            first.data.kind === "switch" ? first.id : second.id,
            first.data.kind === "switch" ? portA : portB,
          ]];
    const missingPort = switchPorts.find(([switchName, port]) => {
      const switchNode = nodes.find((node) => node.id === switchName);
      const inventory = switchNode?.data.ports ?? [];
      return inventory.length > 0 && !inventory.includes(port);
    });
    if (missingPort) {
      setError(`Port ${missingPort[1]} is not in switch ${missingPort[0]}'s configured inventory.`);
      return;
    }
    const occupied = switchPorts.some(([switchName, port]) => edges.some((edge) => {
      if (edge.data?.attachment) {
        return edge.id !== `attachment:${hostToMove}`
          && edge.target === switchName
          && edge.data.target_port === port;
      }
      return (edge.source === switchName && edge.data?.source_port === port)
        || (edge.target === switchName && edge.data?.target_port === port);
    }));
    if (occupied) {
      setError("A switch port can belong to only one host attachment or physical link.");
      return;
    }
    const connectionData: NetworkEdgeData = {
      ...defaultEdgeData(),
      capacity_mbps: numberOrNull(capacity),
      delay_ms: numberOrNull(delay),
      packet_loss_percent: numberOrNull(loss),
      admin_up: linkAdminUp,
      source_port: portA,
      target_port: portB,
      attachment: first.data.kind === "host" || second.data.kind === "host",
    };
    if (connectionData.attachment) {
      const host = first.data.kind === "host" ? first : second;
      const sw = first.data.kind === "switch" ? first : second;
      const switchPort = first.data.kind === "switch" ? portA : portB;
      const attachment = edges.find((edge) => edge.id === `attachment:${host.id}`);
      if (attachment) setEdges((current) => current.filter((edge) => edge.id !== attachment.id));
      updateNode(host.id, {
        switchName: sw.id,
        switchPort,
        attachmentCapacity: connectionData.capacity_mbps,
        attachmentDelay: connectionData.delay_ms,
        attachmentLoss: connectionData.packet_loss_percent,
        attachmentAdminUp: linkAdminUp,
      });
      setEdges((current) => [...current.filter((edge) => edge.id !== `attachment:${host.id}`), {
        id: `attachment:${host.id}`,
        source: host.id,
        target: sw.id,
        label: capacity ? `${capacity} Mbps` : "host attachment",
        type: "smoothstep",
        style: linkAdminUp ? edgeStyle : { stroke: "var(--error)", strokeWidth: 2 },
        data: { ...connectionData, source_port: null, target_port: switchPort, attachment: true },
      }]);
      setNodes((current) => current.map((node) =>
        node.id === sw.id
          ? { ...node, data: { ...node.data, ports: [...new Set([...(node.data.ports ?? []), switchPort])] } }
          : node,
      ));
    } else {
      const id = `link:${first.id}:${portA}:${second.id}:${portB}`;
      if (edges.some((edge) => edge.id === id)) {
        setError("A physical link already uses this exact pair of switch ports.");
        return;
      }
      setEdges((current) => [...current, {
        id,
        source: first.id,
        target: second.id,
        label: capacity ? `${capacity} Mbps` : "link",
        type: "smoothstep",
        style: linkAdminUp ? edgeStyle : { stroke: "var(--error)", strokeWidth: 2 },
        data: connectionData,
      }]);
      setNodes((current) => current.map((node) => {
        if (node.id === first.id) {
          return { ...node, data: { ...node.data, ports: [...new Set([...(node.data.ports ?? []), portA])] } };
        }
        if (node.id === second.id) {
          return { ...node, data: { ...node.data, ports: [...new Set([...(node.data.ports ?? []), portB])] } };
        }
        return node;
      }));
    }
    setCapacity("");
    setDelay("");
    setLoss("");
    markDirty();
  };

  const deleteSelectedNode = () => {
    if (!selectedNode) return;
    setNodes((current) => current.filter((node) => node.id !== selectedNode.id));
    setEdges((current) => current.filter(
      (edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id,
    ));
    setSelected(null);
    markDirty();
  };

  const deleteSelectedEdge = () => {
    if (!selectedEdge) return;
    if (selectedEdge.data?.attachment) {
      setError("Host attachments are part of the host configuration. Edit the host attachment or delete the host.");
      return;
    }
    setEdges((current) => current.filter((edge) => edge.id !== selectedEdge.id));
    setSelected(null);
    markDirty();
  };

  const save = async (): Promise<TopologyDefinition | null> => {
    if (!API_BASE_URL) {
      setError("Configure the local backend to persist topologies.");
      return null;
    }
    if (!topologyName.trim()) {
      setError("Enter a topology name before saving.");
      return null;
    }
    setSaving(true);
    setError(null);
    try {
      const input = definitionFromFlow(topologyName, nodes, edges);
      const saved = definition
        ? await apiRequest<TopologyDefinition>(`/api/v1/topologies/${encodeURIComponent(definition.id)}`, {
            method: "PUT",
            body: JSON.stringify({ ...input, expected_version: versions[0]?.version ?? definition.version }),
          })
        : await apiRequest<TopologyDefinition>("/api/v1/topologies", {
            method: "POST",
            body: JSON.stringify(input),
          });
      applyDefinition(saved);
      setCatalog(await apiRequest<{ topologies: TopologyCatalogItem[] }>("/api/v1/topologies").then((result) => result.topologies));
      setVersions(await apiRequest<{ versions: TopologyDefinition[] }>(
        `/api/v1/topologies/${encodeURIComponent(saved.id)}/versions`,
      ).then((result) => result.versions));
      if (activeId === saved.id) setActiveVersion(saved.version);
      return saved;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology could not be saved.");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const startNew = () => {
    setDefinition(null);
    setTopologyName("Untitled topology");
    setVersions([]);
    setNodes([]);
    setEdges([]);
    setSelected(null);
    setDirty(true);
    setViewMode("DESIGN");
    setError(null);
  };

  const activate = async () => {
    if (!definition && dirty) {
      const saved = await save();
      if (!saved) return;
      await apiRequest<ActiveTopologyResponse>(
        `/api/v1/topologies/${encodeURIComponent(saved.id)}/activate`,
        { method: "POST", body: JSON.stringify({}) },
      );
      await refreshCatalog();
      return;
    }
    if (!definition) return;
    try {
      if (dirty) {
        const saved = await save();
        if (!saved) return;
      }
      await apiRequest<ActiveTopologyResponse>(
        `/api/v1/topologies/${encodeURIComponent(definition.id)}/activate`,
        { method: "POST", body: JSON.stringify({}) },
      );
      await refreshCatalog();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology activation failed.");
    }
  };

  const duplicate = async () => {
    if (!definition) return;
    try {
      const copy = await apiRequest<TopologyDefinition>(
        `/api/v1/topologies/${encodeURIComponent(definition.id)}/duplicate`,
        {
          method: "POST",
          body: JSON.stringify({ name: `${topologyName} copy` }),
        },
      );
      await loadDefinition(copy.id);
      await refreshCatalog();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology duplication failed.");
    }
  };

  const rename = async () => {
    if (!definition || !topologyName.trim()) return;
    try {
      const renamed = await apiRequest<TopologyDefinition>(
        `/api/v1/topologies/${encodeURIComponent(definition.id)}/rename`,
        {
          method: "POST",
          body: JSON.stringify({ name: topologyName, expected_version: versions[0]?.version ?? definition.version }),
        },
      );
      applyDefinition(renamed);
      await refreshCatalog();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology rename failed.");
    }
  };

  const removeTopology = async () => {
    if (!definition) return;
    try {
      await apiRequest<void>(`/api/v1/topologies/${encodeURIComponent(definition.id)}`, { method: "DELETE" });
      startNew();
      await refreshCatalog();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology deletion failed.");
    }
  };

  const exportTopology = () => {
    try {
      const input = definitionFromFlow(topologyName, nodes, edges);
      const payload = JSON.stringify({ format: "intentflow-topology-v1", topology: input }, null, 2);
      const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${topologyName.trim().replace(/[^A-Za-z0-9_-]+/g, "-") || "topology"}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Topology export failed.");
    }
  };

  const importTopology = async (file?: File) => {
    if (!file) return;
    setError(null);
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const imported = await apiRequest<TopologyDefinition>("/api/v1/topologies/import", {
        method: "POST",
        body: JSON.stringify(parsed),
      });
      await loadDefinition(imported.id);
      await refreshCatalog();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Topology import failed.");
    } finally {
      if (importRef.current) importRef.current.value = "";
    }
  };

  const discoverLive = async () => {
    setLoading(true);
    setError(null);
    try {
      const topology = await apiRequest<TopologyResponse>("/api/v1/topology");
      const flow = liveTopologyToFlow(topology);
      setLiveTopology(topology);
      setNodes(flow.nodes);
      setEdges(flow.edges);
      setSelected(null);
      setViewMode("LIVE");
      setDirty(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Live topology discovery failed.");
    } finally {
      setLoading(false);
    }
  };

  const returnToDesign = async () => {
    setViewMode("DESIGN");
    setLiveTopology(null);
    if (definition) await loadDefinition(definition.id, definition.version);
    else {
      setNodes([]);
      setEdges([]);
    }
  };

  const currentNames = nodes.map((node) => node.id);
  const canEdit = editable && !readOnlyVersion;

  return (
    <div className="page-stack">
      <div className="topology-toolbar">
        <div className="topology-summary">
          <StatusPill tone={active ? "positive" : "warning"}>
            {active ? "Active planning topology" : "No active design"}
          </StatusPill>
          <span>{switchNodes.length} switches</span><span className="toolbar-sep">·</span>
          <span>{nodes.length - switchNodes.length} hosts</span><span className="toolbar-sep">·</span>
          <span>{edges.filter((edge) => !edge.data?.attachment).length} physical links</span>
          {dirty && <StatusPill tone="warning">Unsaved changes</StatusPill>}
        </div>
        <StatusPill tone={viewMode === "LIVE" ? "info" : "neutral"}>
          {viewMode}{definition ? ` · v${definition.version}` : ""}
        </StatusPill>
      </div>

      <Panel className="topology-editor-controls">
        <div className="topology-editor-row">
          <label className="topology-control-field"><span>Saved topologies</span>
            <select
              value={definition?.id ?? ""}
              onChange={(event) => {
                if (event.target.value) void loadDefinition(event.target.value).catch((loadError: unknown) =>
                  setError(loadError instanceof Error ? loadError.message : "Topology could not be loaded."),
                );
              }}
              disabled={!API_BASE_URL || loading}
            >
              <option value="">Select a topology…</option>
              {catalog.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · v{item.version}{item.active ? " · ACTIVE" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="topology-control-field topology-name-field"><span>Topology name</span>
            <input value={topologyName} onChange={(event) => { setTopologyName(event.target.value); markDirty(); }} disabled={!canEdit} />
          </label>
          <div className="topology-control-actions">
            <button className="button-secondary compact-button" onClick={startNew} disabled={!API_BASE_URL || viewMode === "LIVE"}><Plus size={13} /> New</button>
            <button className="button-primary compact-button" onClick={() => void save()} disabled={!canEdit || !dirty || saving}><Save size={13} /> {saving ? "Saving…" : "Save version"}</button>
            <button className="button-secondary compact-button" onClick={() => void activate()} disabled={!definition && !dirty || active && !dirty || !API_BASE_URL}><span>Activate</span></button>
            <button className="button-secondary compact-button" onClick={() => void duplicate()} disabled={!definition || !API_BASE_URL}><span>Duplicate</span></button>
            <button className="button-secondary compact-button" onClick={() => void rename()} disabled={!definition || !dirty || !API_BASE_URL}><span>Rename</span></button>
            <button className="button-secondary compact-button" onClick={() => void removeTopology()} disabled={!definition || !API_BASE_URL}><span>Delete</span></button>
          </div>
        </div>
        <div className="topology-editor-row topology-editor-row-secondary">
          <label className="topology-control-field"><span>Version history</span>
            <select
              value={definition?.version ?? ""}
              onChange={(event) => {
                if (definition && event.target.value) {
                  void loadDefinition(definition.id, Number(event.target.value));
                }
              }}
              disabled={!definition || dirty || versions.length < 2}
            >
              {versions.map((item) => <option key={item.version} value={item.version}>Version {item.version}</option>)}
            </select>
          </label>
          <div className="topology-control-actions">
            <button className="button-secondary compact-button" onClick={() => importRef.current?.click()} disabled={!API_BASE_URL || viewMode === "LIVE"}><Upload size={13} /> Import JSON</button>
            <input ref={importRef} className="topology-file-input" type="file" accept="application/json,.json" onChange={(event) => void importTopology(event.target.files?.[0])} />
            <button className="button-secondary compact-button" onClick={exportTopology} disabled={viewMode === "LIVE"}><Download size={13} /> Export JSON</button>
            {viewMode === "LIVE"
              ? <button className="button-secondary compact-button" onClick={() => void returnToDesign()}>Return to design</button>
              : <button className="button-secondary compact-button" onClick={() => void discoverLive()} disabled={!API_BASE_URL || loading}>{loading ? "Discovering…" : "Discover LIVE snapshot"}</button>}
          </div>
        </div>
        {readOnlyVersion && <div className="preview-caveat"><Info size={14} /><span>Historical version is read-only. Load the latest version to edit it.</span></div>}
        {viewMode === "DESIGN" && <div className="topology-editor-row topology-node-actions">
          <div className="topology-control-actions">
            <button className="button-secondary compact-button" onClick={addSwitch} disabled={!canEdit}><Plus size={13} /> Add switch</button>
            <button className="button-secondary compact-button" onClick={addHost} disabled={!canEdit}><Plus size={13} /> Add host</button>
          </div>
          <div className="topology-connect-controls">
            <span>Connect nodes</span>
            <select value={sourceNode} onChange={(event) => setSourceNode(event.target.value)}>
              <option value="">From node</option>
              {nodes.map((node) => <option key={node.id} value={node.id}>{node.data.label}</option>)}
            </select>
            <input aria-label="Source switch port" type="number" min="1" value={sourcePort} onChange={(event) => setSourcePort(event.target.value)} />
            <select value={targetNode} onChange={(event) => setTargetNode(event.target.value)}>
              <option value="">To node</option>
              {nodes.map((node) => <option key={node.id} value={node.id}>{node.data.label}</option>)}
            </select>
            <input aria-label="Destination switch port" type="number" min="1" value={targetPort} onChange={(event) => setTargetPort(event.target.value)} />
            <input aria-label="Link capacity Mbps" placeholder="Mbps" type="number" min="0.001" step="any" value={capacity} onChange={(event) => setCapacity(event.target.value)} />
            <input aria-label="Link delay ms" placeholder="Delay ms" type="number" min="0" step="any" value={delay} onChange={(event) => setDelay(event.target.value)} />
            <input aria-label="Link packet loss percent" placeholder="Loss %" type="number" min="0" max="100" step="any" value={loss} onChange={(event) => setLoss(event.target.value)} />
            <label className="topology-state-toggle"><input type="checkbox" checked={linkAdminUp} onChange={(event) => setLinkAdminUp(event.target.checked)} /> Up</label>
            <button className="button-secondary compact-button" onClick={createConnection} disabled={!canEdit}><Link2 size={13} /> Connect</button>
          </div>
        </div>}
      </Panel>

      {error && <div className="submit-notice notice-warning" role="alert"><Info size={15} /><span>{error}</span></div>}
      {!API_BASE_URL && <div className="submit-notice notice-warning" role="status"><Info size={15} /><span>Topology management requires the configured backend API. No local-only changes will be presented as saved.</span></div>}
      {viewMode === "LIVE" && liveTopology && <div className="submit-notice notice-info"><Info size={15} /><span>Read-only LIVE discovery snapshot · {new Date(liveTopology.snapshot_timestamp).toLocaleString()} · {liveTopology.snapshot_status}. This snapshot is not a DESIGN topology and cannot be edited or activated as a design.</span></div>}
      {viewMode === "DESIGN" && !active && <div className="submit-notice notice-info"><Info size={15} /><span>Only an explicitly activated DESIGN topology is used by intent planning. Saving or activating does not start Mininet or install flows.</span></div>}

      <Panel className="topology-panel">
        <div className="topology-canvas-header">
          <div>
            <h3>{definition?.name ?? "Topology design canvas"}</h3>
            <span>{viewMode === "LIVE"
              ? `Ryu / OVS snapshot · ${liveTopology?.source ?? "live source"}`
              : `DESIGN · ${definition ? `Version ${definition.version}` : "Unsaved topology"} · drag nodes to lay out`}
            </span>
          </div>
          <div className="canvas-header-right">
            {definition && <StatusPill tone={active ? "positive" : "neutral"}>{active ? "Active" : "Saved design"}</StatusPill>}
            <button className="button-secondary compact-button" onClick={() => { setSelected(null); }}>
              Clear selection
            </button>
          </div>
        </div>
        <div className="react-flow-wrap">
          <ReactFlow
            nodes={nodes}
            edges={edges.map((edge) => ({
              ...edge,
              style: selected?.type === "edge" && selected.id === edge.id
                ? selectedEdgeStyle
                : edge.style,
            }))}
            nodeTypes={nodeTypes}
            onNodesChange={canEdit ? handleNodesChange : onNodesChange}
            onEdgesChange={canEdit ? handleEdgesChange : onEdgesChange}
            onNodeClick={(_, node) => {
              setSelected({ type: "node", id: node.id });
              setNodeNameDraft(node.data.label);
            }}
            onEdgeClick={(_, edge) => setSelected({ type: "edge", id: edge.id })}
            onPaneClick={() => setSelected(null)}
            fitView
            fitViewOptions={{ padding: 0.18 }}
            minZoom={0.35}
            maxZoom={1.6}
            nodesDraggable={canEdit}
            nodesConnectable={false}
            elementsSelectable
          >
            <Background color="var(--border)" gap={22} size={1} />
            <Controls position="bottom-left" showInteractive={false} />
            <MiniMap position="bottom-right" nodeColor={(node) => node.data.kind === "host" ? "var(--periwinkle)" : "var(--accent)"} maskColor="rgba(8, 12, 18, .72)" />
          </ReactFlow>
          {(selectedNode || selectedEdge) && <div className="topology-inspector topology-editor-inspector">
            <div className="inspector-header">
              <div className="inspector-title-icon">{selectedNode?.data.kind === "host" ? <Server size={16} /> : selectedNode ? <Router size={16} /> : <Link2 size={16} />}</div>
              <div><strong>{selectedNode?.data.label ?? `${selectedEdge?.source} — ${selectedEdge?.target}`}</strong><small>{selectedNode ? `${selectedNode.data.kind} properties` : "Physical link properties"}</small></div>
              <button className="icon-button" aria-label="Close details" onClick={() => setSelected(null)}><X size={15} /></button>
            </div>
            <div className="inspector-body topology-inspector-form">
              {selectedNode ? <>
                <label>Name<input value={nodeNameDraft} onChange={(event) => setNodeNameDraft(event.target.value)} disabled={!canEdit} /></label>
                {nodeNameDraft !== selectedNode.id && <button className="button-secondary compact-button" onClick={applyNodeName} disabled={!canEdit}>Apply name</button>}
                {selectedNode.data.kind === "switch" ? <>
                  <label>DPID<input type="number" min="1" value={selectedNode.data.dpid ?? ""} onChange={(event) => updateNode(selectedNode.id, { dpid: Number(event.target.value) })} disabled={!canEdit} /></label>
                  <label>Switch ports<input value={(selectedNode.data.ports ?? []).join(", ")} onChange={(event) => {
                    const ports = event.target.value.split(",").map((item) => Number(item.trim())).filter((item) => Number.isInteger(item) && item > 0);
                    updateNode(selectedNode.id, { ports });
                  }} disabled={!canEdit} /></label>
                </> : <>
                  <label>IP address<input value={selectedNode.data.ip ?? ""} onChange={(event) => updateNode(selectedNode.id, { ip: event.target.value })} disabled={!canEdit} /></label>
                  <label>MAC address<input value={selectedNode.data.mac ?? ""} onChange={(event) => updateNode(selectedNode.id, { mac: event.target.value })} disabled={!canEdit} /></label>
                  <label>Attached switch<select value={selectedNode.data.switchName ?? ""} onChange={(event) => updateNode(selectedNode.id, { switchName: event.target.value })} disabled={!canEdit}>
                    <option value="">Select switch</option>{switchNodes.map((node) => <option key={node.id} value={node.id}>{node.id}</option>)}
                  </select></label>
                  <label>Switch port<input type="number" min="1" value={selectedNode.data.switchPort ?? ""} onChange={(event) => updateNode(selectedNode.id, { switchPort: Number(event.target.value) })} disabled={!canEdit} /></label>
                  <label>Attachment capacity Mbps<input type="number" min="0.001" step="any" value={selectedNode.data.attachmentCapacity ?? ""} onChange={(event) => updateNode(selectedNode.id, { attachmentCapacity: numberOrNull(event.target.value) })} disabled={!canEdit} /></label>
                  <label>Attachment delay ms<input type="number" min="0" step="any" value={selectedNode.data.attachmentDelay ?? ""} onChange={(event) => updateNode(selectedNode.id, { attachmentDelay: numberOrNull(event.target.value) })} disabled={!canEdit} /></label>
                  <label>Attachment packet loss %<input type="number" min="0" max="100" step="any" value={selectedNode.data.attachmentLoss ?? ""} onChange={(event) => updateNode(selectedNode.id, { attachmentLoss: numberOrNull(event.target.value) })} disabled={!canEdit} /></label>
                  <label className="topology-state-toggle"><input type="checkbox" checked={selectedNode.data.attachmentAdminUp ?? true} onChange={(event) => updateNode(selectedNode.id, { attachmentAdminUp: event.target.checked })} disabled={!canEdit} /> Attachment administratively up</label>
                </>}
                <button className="button-secondary compact-button topology-delete-button" onClick={deleteSelectedNode} disabled={!canEdit}>Delete node</button>
              </> : selectedEdge ? <>
                <label>Source node<input value={selectedEdge.source} readOnly /></label>
                <label>Destination node<input value={selectedEdge.target} readOnly /></label>
                {!selectedEdge.data?.attachment && <>
                  <label>Source switch port<input type="number" min="1" value={selectedEdge.data?.source_port ?? ""} onChange={(event) => updateEdge(selectedEdge.id, { source_port: Number(event.target.value) })} disabled={!canEdit} /></label>
                  <label>Destination switch port<input type="number" min="1" value={selectedEdge.data?.target_port ?? ""} onChange={(event) => updateEdge(selectedEdge.id, { target_port: Number(event.target.value) })} disabled={!canEdit} /></label>
                </>}
                <label>Capacity Mbps<input type="number" min="0.001" step="any" value={selectedEdge.data?.capacity_mbps ?? ""} onChange={(event) => updateEdge(selectedEdge.id, { capacity_mbps: numberOrNull(event.target.value) })} disabled={!canEdit} /></label>
                <label>Delay ms<input type="number" min="0" step="any" value={selectedEdge.data?.delay_ms ?? ""} onChange={(event) => updateEdge(selectedEdge.id, { delay_ms: numberOrNull(event.target.value) })} disabled={!canEdit} /></label>
                <label>Packet loss %<input type="number" min="0" max="100" step="any" value={selectedEdge.data?.packet_loss_percent ?? ""} onChange={(event) => updateEdge(selectedEdge.id, { packet_loss_percent: numberOrNull(event.target.value) })} disabled={!canEdit} /></label>
                <label className="topology-state-toggle"><input type="checkbox" checked={selectedEdge.data?.admin_up ?? false} onChange={(event) => updateEdge(selectedEdge.id, { admin_up: event.target.checked })} disabled={!canEdit} /> Administratively up</label>
                <button className="button-secondary compact-button topology-delete-button" onClick={deleteSelectedEdge} disabled={!canEdit || Boolean(selectedEdge.data?.attachment)}>Delete link</button>
                {selectedEdge.data?.attachment && <small className="inspector-note">Host attachments are managed with the host record.</small>}
              </> : null}
            </div>
          </div>}
        </div>
        <div className="topology-legend">
          <span><i className="legend-line active-line" /> Administratively up</span>
          <span><i className="legend-line inactive-line" /> Administratively down</span>
          <span className="legend-note"><Info size={13} /> Configured capacity is not measured throughput.</span>
        </div>
      </Panel>

      <div className="topology-bottom-grid">
        <Panel>
          <div className="panel-title-row"><div><h3>Topology inventory</h3><p>{definition ? `${definition.name} · version ${definition.version}` : "Current editor inventory"}</p></div><StatusPill>{viewMode}</StatusPill></div>
          <div className="inventory-row"><div><Router size={15} /><span>Switches</span></div><strong>{switchNodes.map((node) => `${node.id} (DPID ${node.data.dpid})`).join(", ") || "None"}</strong><span>{switchNodes.length}</span></div>
          <div className="inventory-row"><div><Server size={15} /><span>Hosts</span></div><strong>{nodes.filter((node) => node.data.kind === "host").map((node) => `${node.id} → ${node.data.switchName}:${node.data.switchPort}`).join(", ") || "None"}</strong><span>{nodes.length - switchNodes.length}</span></div>
          <div className="inventory-row"><div><Link2 size={15} /><span>Physical links</span></div><strong>Parallel links retain their port identities</strong><span>{edges.filter((edge) => !edge.data?.attachment).length}</span></div>
        </Panel>
        <Panel>
          <div className="panel-title-row"><div><h3>Planning and execution mode</h3><p>Topology provenance stays explicit</p></div><FileJson2 size={15} className="muted-icon" /></div>
          <div className="topology-mode-note"><StatusPill tone={viewMode === "LIVE" ? "info" : "neutral"}>{viewMode}</StatusPill><span>{viewMode === "LIVE"
            ? "Controller-discovered snapshot. Read-only and accepted only when complete."
            : "User-authored graph used for deterministic planning simulation only."}</span></div>
          <div className="topology-mode-note"><StatusPill tone="warning">MININET</StatusPill><span>Instantiation is not available in this release. Activating a DESIGN topology never starts Mininet or changes the network.</span></div>
        </Panel>
      </div>
      <span className="sr-only">{currentNames.join(", ")}</span>
    </div>
  );
}
