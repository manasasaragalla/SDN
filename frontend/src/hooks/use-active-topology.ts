"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import type { ActiveTopologyResponse } from "@/types/api";

type ActiveTopologyState =
  | { status: "demo"; topology: null; error: null }
  | { status: "loading"; topology: null; error: null }
  | { status: "loaded"; topology: ActiveTopologyResponse["topology"]; error: null }
  | { status: "error"; topology: null; error: string };

export function useActiveTopology(): ActiveTopologyState {
  const [state, setState] = useState<ActiveTopologyState>(
    API_BASE_URL
      ? { status: "loading", topology: null, error: null }
      : { status: "demo", topology: null, error: null },
  );

  useEffect(() => {
    if (!API_BASE_URL) return;
    let active = true;

    const refresh = async () => {
      try {
        const response = await apiRequest<ActiveTopologyResponse>("/api/v1/topologies/active");
        if (active) {
          setState({ status: "loaded", topology: response.topology, error: null });
        }
      } catch (error) {
        if (active) {
          setState({
            status: "error",
            topology: null,
            error: error instanceof Error ? error.message : "Active topology could not be loaded.",
          });
        }
      }
    };

    void refresh();
    const intervalId = window.setInterval(refresh, 15_000);
    window.addEventListener("focus", refresh);
    return () => {
      active = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refresh);
    };
  }, []);

  return state;
}
