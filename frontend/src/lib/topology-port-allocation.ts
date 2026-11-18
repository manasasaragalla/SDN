type PortNode = {
  id: string;
  data: {
    kind: "host" | "switch";
    switchName?: string;
    switchPort?: number;
  };
};

type PortEdge = {
  source: string;
  target: string;
  data?: {
    source_port?: number | null;
    target_port?: number | null;
  };
};

export function nextAvailableAttachmentPort(
  switchName: string,
  portInventory: number[],
  nodes: PortNode[],
  edges: PortEdge[],
): number {
  const occupied = new Set<number>();
  for (const node of nodes) {
    if (node.data.kind === "host" && node.data.switchName === switchName && node.data.switchPort != null) {
      occupied.add(node.data.switchPort);
    }
  }
  for (const edge of edges) {
    if (edge.source === switchName && edge.data?.source_port != null) {
      occupied.add(edge.data.source_port);
    }
    if (edge.target === switchName && edge.data?.target_port != null) {
      occupied.add(edge.data.target_port);
    }
  }

  const availableConfiguredPort = portInventory.find(
    (port) => Number.isInteger(port) && port > 0 && !occupied.has(port),
  );
  if (availableConfiguredPort !== undefined) return availableConfiguredPort;

  let port = Math.max(0, ...portInventory.filter((candidate) => Number.isInteger(candidate) && candidate > 0)) + 1;
  while (occupied.has(port)) port += 1;
  return port;
}
