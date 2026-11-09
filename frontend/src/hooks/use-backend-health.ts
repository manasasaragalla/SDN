"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import type { ApiHealth } from "@/types/api";

type BackendConnection =
  | { state: "demo"; health: null; error: null }
  | { state: "checking"; health: null; error: null }
  | { state: "connected"; health: ApiHealth; error: null }
  | { state: "disconnected"; health: ApiHealth | null; error: string };

export function useBackendHealth(): BackendConnection {
  const [connection, setConnection] = useState<BackendConnection>(
    API_BASE_URL
      ? { state: "checking", health: null, error: null }
      : { state: "demo", health: null, error: null },
  );

  useEffect(() => {
    if (!API_BASE_URL) return;

    let active = true;
    const check = async () => {
      try {
        const health = await apiRequest<ApiHealth>("/api/v1/health");
        if (active) {
          setConnection({ state: "connected", health, error: null });
        }
      } catch (error) {
        if (active) {
          setConnection({
            state: "disconnected",
            health: null,
            error: error instanceof Error ? error.message : "Backend health check failed.",
          });
        }
      }
    };

    void check();
    const intervalId = window.setInterval(check, 15_000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  return connection;
}
