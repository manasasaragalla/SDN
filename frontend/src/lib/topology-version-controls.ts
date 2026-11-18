export function isHistoricalVersion(
  version: number,
  latestVersion: number | undefined,
): boolean {
  return latestVersion !== undefined && version !== latestVersion;
}

export function canActivateTopology(
  hasDefinition: boolean,
  dirty: boolean,
  isActive: boolean,
  apiConfigured: boolean,
): boolean {
  return apiConfigured && (hasDefinition ? !isActive || dirty : dirty);
}

export function activeTopologyLabel(
  topology: { name: string; version: number } | null,
): string {
  return topology
    ? `Active planning topology · ${topology.name} · v${topology.version}`
    : "No active design";
}

export function activateVersionRequest(version: number): {
  method: "POST";
  body: string;
} {
  return { method: "POST", body: JSON.stringify({ version }) };
}
