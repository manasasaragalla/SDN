"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, CircleHelp, ExternalLink, Info, LockKeyhole, PlugZap, Settings2, ShieldCheck, SlidersHorizontal, Wifi } from "lucide-react";
import { DemoTag, Panel, SectionHeading, StatusPill } from "@/components/ui/dashboard-ui";
import { API_BASE_URL, AUTH_DISABLED, apiRequest } from "@/lib/api-client";
import type { ApiHealth } from "@/types/api";

export function SettingsPage() {
  const [apiBaseUrl, setApiBaseUrl] = useState(process.env.NEXT_PUBLIC_API_BASE_URL ?? "");
  const [testing, setTesting] = useState(Boolean(API_BASE_URL));
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [apiToken, setApiToken] = useState("");
  const [authenticating, setAuthenticating] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const configured = Boolean(API_BASE_URL);

  const testConnection = useCallback(async () => {
    setTesting(true);
    setHealth(null);
    setConnectionError(null);
    try {
      setHealth(await apiRequest<ApiHealth>("/api/v1/health"));
    } catch (error) {
      setConnectionError(
        error instanceof Error ? error.message : "The backend health check failed.",
      );
    } finally {
      setTesting(false);
    }
  }, []);

  useEffect(() => {
    if (!configured || !AUTH_DISABLED) return;
    let active = true;
    apiRequest<ApiHealth>("/api/v1/health")
      .then((result) => {
        if (active) setHealth(result);
      })
      .catch((error: unknown) => {
        if (active) {
          setConnectionError(
            error instanceof Error ? error.message : "The backend health check failed.",
          );
        }
      })
      .finally(() => {
        if (active) setTesting(false);
      });
    return () => {
      active = false;
    };
  }, [configured]);

  const authenticate = async () => {
    setAuthenticating(true);
    setConnectionError(null);
    try {
      await apiRequest<{ authenticated: boolean }>("/api/v1/auth/session", {
        method: "POST",
        headers: { Authorization: `Bearer ${apiToken}` },
      });
      setAuthenticated(true);
      await testConnection();
    } catch (error) {
      setConnectionError(
        error instanceof Error ? error.message : "API authentication failed.",
      );
    } finally {
      setApiToken("");
      setAuthenticating(false);
    }
  };

  const signOut = async () => {
    setConnectionError(null);
    try {
      await apiRequest<void>("/api/v1/auth/session", { method: "DELETE" });
      setAuthenticated(false);
      setHealth(null);
    } catch (error) {
      setConnectionError(
        error instanceof Error ? error.message : "Could not end the API session.",
      );
    }
  };

  const connectionLabel = !configured
    ? "Not configured"
    : testing
      ? "Checking"
      : health
        ? "Connected"
        : connectionError
          ? "Disconnected"
          : !AUTH_DISABLED && !authenticated
            ? "Authentication required"
            : "Unavailable";
  const connectionTone = health
    ? "positive"
    : connectionError
      ? "negative"
      : "warning";

  return (
    <div className="page-stack">
      <div className="demo-banner"><div className="demo-banner-icon"><Settings2 size={17} /></div><div><strong>Integration boundary</strong><span>Backend connection state is live when configured. Dashboard metrics and execution records remain labeled sample data.</span></div><DemoTag /></div>
      <Panel className="settings-panel">
        <SectionHeading title="Backend connection" description={AUTH_DISABLED ? "The local dashboard connects directly without a token or browser session." : "Production API access uses the configured authenticated session."} action={<StatusPill tone={connectionTone}>{connectionLabel}</StatusPill>} />
        <div className="settings-field">
          <div className="settings-field-label"><div className="settings-icon"><PlugZap size={16} /></div><div><strong>API base URL</strong><span>Set with NEXT_PUBLIC_API_BASE_URL in the frontend environment.</span></div></div>
          <input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} placeholder="http://localhost:8000" aria-label="API base URL" />
          <span className="settings-readonly-note"><Info size={13} /> The configured environment URL is used for requests. Editing this field is local only.</span>
        </div>
        {!AUTH_DISABLED && <div className="settings-field">
          <div className="settings-field-label"><div className="settings-icon"><LockKeyhole size={16} /></div><div><strong>Production API access</strong><span>Authenticate to create a time-limited browser session.</span></div></div>
          <input type="password" autoComplete="current-password" value={apiToken} onChange={(event) => setApiToken(event.target.value)} placeholder="API access token" aria-label="API access token" />
          <span className="settings-readonly-note"><Info size={13} /> The token is exchanged for an HttpOnly session cookie and is not stored by the dashboard.</span>
          <div className="settings-actions">
            <button className="button-secondary" disabled={!configured || authenticating || !apiToken} onClick={() => void authenticate()}>{authenticating ? "Authenticating…" : "Authenticate"}</button>
            {authenticated && <button className="button-secondary" onClick={() => void signOut()}>End session</button>}
          </div>
        </div>}
        <div className="settings-actions"><button className="button-secondary" disabled={!configured || testing || (!AUTH_DISABLED && !authenticated)} onClick={() => void testConnection()}><Wifi size={14} /> {testing ? "Checking…" : "Test connection"}</button><span>{connectionError ?? (health ? `API ${health.backend_status.toLowerCase()} · Ryu ${health.ryu_status.toLowerCase()} · Mininet ${health.mininet_status.toLowerCase()}` : configured ? AUTH_DISABLED ? "Checking the local API; topology checks do not start Mininet." : authenticated ? "Checking API connectivity." : "Authenticate to inspect the protected API." : "Set NEXT_PUBLIC_API_BASE_URL and restart the frontend to enable requests.")}</span></div>
        {connectionError && <div className="inline-warning" role="alert">{connectionError}</div>}
        {health?.details.worker && <div className="settings-readonly-note"><Info size={13} /> SDN worker: {health.details.worker.toLowerCase()}. Mininet status is unknown until a topology operation runs.</div>}
      </Panel>
      <div className="settings-grid">
        <Panel><div className="panel-title-row"><div><h3>Controller integration</h3><p>Live status is queried from the local adapter</p></div><ShieldCheck size={16} className="muted-icon" /></div><div className="integration-row"><div className="integration-icon"><Wifi size={16} /></div><div><strong>Ryu controller</strong><span>{health ? `OpenFlow API · ${health.ryu_status.toLowerCase()}` : "No live controller status available"}</span></div><StatusPill tone={health?.ryu_status === "CONNECTED" ? "positive" : "neutral"}>{health?.ryu_status ?? "Unknown"}</StatusPill></div><div className="integration-row"><div className="integration-icon"><SlidersHorizontal size={16} /></div><div><strong>Mininet / OVS</strong><span>Started only for an explicit topology or execution request</span></div><StatusPill tone="neutral">{health?.mininet_status ?? "Unknown"}</StatusPill></div></Panel>
        <Panel><div className="panel-title-row"><div><h3>Data and privacy</h3><p>Current frontend behavior</p></div><CircleHelp size={15} className="muted-icon" /></div><div className="privacy-list"><div><Check size={15} /><span>Dashboard sample data remains separate from API responses.</span></div><div><Check size={15} /><span>Intent is sent only when preview or execution is explicitly requested.</span></div><div><Check size={15} /><span>The API accepts declarative intent, never OpenFlow rules or shell commands.</span></div><div><Check size={15} /><span>{AUTH_DISABLED ? "Local development requests omit Bearer headers and authentication cookies." : "Production requests use authenticated API sessions."}</span></div><div><Check size={15} /><span>Production API authentication remains required.</span></div></div>{API_BASE_URL && <a className="inline-doc-link" href={`${API_BASE_URL}/api/v1/health`} target="_blank" rel="noreferrer">API health endpoint <ExternalLink size={13} /></a>}</Panel>
      </div>
    </div>
  );
}
