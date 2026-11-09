"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Check, ChevronRight, CircleDot, Clock3, FileText, GitBranch, ShieldCheck } from "lucide-react";
import { demoExecutions } from "@/lib/demo-data";
import { DemoTag, Panel, StatusPill } from "@/components/ui/dashboard-ui";
import type { ExecutionRecord } from "@/types/dashboard";
import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import type { ExecutionDetail, ExecutionSummary } from "@/types/api";

const timeline = [
  { name: "Intent received", detail: "Canonical request accepted", time: "15:18:48.631", done: true },
  { name: "Candidates enumerated", detail: "2 physical paths discovered", time: "15:18:48.632", done: true },
  { name: "Hard constraint evaluated", detail: "10 Mbps path excluded; 45.14 Mbps path passed ≥ 20 Mbps", time: "15:19:03.975", done: true },
  { name: "Objective ranked", detail: "Selected lowest measured latency: 2.483 ms", time: "15:19:04.035", done: true },
  { name: "Final preflight", detail: "Fresh topology and port validation passed", time: "15:19:04.119", done: true },
  { name: "Rules deployed and verified", detail: "16 / 16 flows read back", time: "15:19:04.186", done: true },
  { name: "Connectivity checked", detail: "10 / 10 replies · 0% packet loss", time: "15:19:13.212", done: true },
];

export function ExecutionsPage() {
  const [selected, setSelected] = useState<ExecutionRecord>(demoExecutions[0]);
  const [apiExecutions, setApiExecutions] = useState<ExecutionSummary[]>([]);
  const [apiDetail, setApiDetail] = useState<ExecutionDetail | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loadingApiHistory, setLoadingApiHistory] = useState(Boolean(API_BASE_URL));

  useEffect(() => {
    if (!API_BASE_URL) return;
    let active = true;
    apiRequest<ExecutionSummary[]>("/api/v1/executions")
      .then((records) => {
        if (active) {
          setApiExecutions(records);
          setApiError(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setApiError(error instanceof Error ? error.message : "Execution history is unavailable.");
        }
      })
      .finally(() => {
        if (active) setLoadingApiHistory(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const openApiExecution = async (executionId: string) => {
    try {
      setApiDetail(await apiRequest<ExecutionDetail>(`/api/v1/executions/${encodeURIComponent(executionId)}`));
      setApiError(null);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Execution evidence is unavailable.");
    }
  };

  const intentLabel = (record: ExecutionSummary) => {
    if (typeof record.submitted_intent === "string") return record.submitted_intent;
    const request = record.submitted_intent;
    if (!request) return "Intent details not recorded";
    if (typeof request.natural_language === "string") return request.natural_language;
    const source = request.source ?? (request.scope as { source?: string } | undefined)?.source;
    const destination = request.destination ?? (request.scope as { destination?: string } | undefined)?.destination;
    return typeof source === "string" && typeof destination === "string"
      ? `${source} → ${destination} · structured intent`
      : "Structured intent";
  };

  const measurementLabel = (record: ExecutionSummary) => {
    const measurement = record.final_measurement;
    if (!measurement) return "No final measurement recorded";
    const values: string[] = [];
    if (typeof measurement.rtt_avg_ms === "number") values.push(`${measurement.rtt_avg_ms} ms RTT`);
    if (typeof measurement.received_mbps === "number") values.push(`${measurement.received_mbps} Mbps received`);
    if (typeof measurement.packet_loss_pct === "number") values.push(`${measurement.packet_loss_pct}% loss`);
    return values.length ? values.join(" · ") : "Measurement recorded; no recognized summary fields";
  };

  const statusTone = (status: string) => {
    if (status === "SUCCEEDED") return "positive";
    if (status === "FAILED") return "negative";
    if (status === "RUNNING") return "info";
    if (status === "NO_FEASIBLE_CANDIDATE" || status === "NO_SATISFYING_CANDIDATE") return "warning";
    return "neutral";
  };

  return (
    <div className="page-stack">
      {API_BASE_URL && <Panel className="execution-table-panel">
        <div className="panel-title-row"><div><h3>Persisted backend evidence <span className="candidate-count">{apiExecutions.length}</span></h3><p>Records read from the Python adapter; unavailable fields are not inferred.</p></div><StatusPill tone={apiError ? "negative" : "info"}>{apiError ? "Disconnected" : loadingApiHistory ? "Loading" : "API evidence"}</StatusPill></div>
        {apiError && <div className="submit-notice notice-warning" role="alert">{apiError}</div>}
        {!loadingApiHistory && !apiError && apiExecutions.length === 0 && <div className="timeline-unavailable">The API returned no persisted execution records. The demo examples below are separate and are not live backend history.</div>}
        {apiExecutions.length > 0 && <div className="candidate-table-wrap">
          <table className="data-table executions-table">
            <thead><tr><th>Execution</th><th>Intent</th><th>Started</th><th>Status</th><th>Selected path</th><th>Final measurement</th><th /></tr></thead>
            <tbody>{apiExecutions.map((record) => <tr key={record.execution_id} onClick={() => void openApiExecution(record.execution_id)}>
              <td><code>{record.execution_id}</code></td>
              <td className="execution-intent">{intentLabel(record)}</td>
              <td>{record.started_at ? new Date(record.started_at).toLocaleString() : "Not recorded"}</td>
              <td><StatusPill tone={statusTone(record.status)}>{record.status}</StatusPill></td>
              <td className="execution-path">{record.selected_path?.join(" → ") ?? "Not recorded"}</td>
              <td>{measurementLabel(record)}</td>
              <td><ChevronRight size={15} className="muted-icon" /></td>
            </tr>)}</tbody>
          </table>
        </div>}
        {apiDetail && <details className="evidence-preview"><summary>Evidence details · {apiDetail.execution_id}</summary><pre>{JSON.stringify(apiDetail.evidence, null, 2)}</pre></details>}
      </Panel>}
      <div className="demo-banner"><div className="demo-banner-icon"><Clock3 size={17} /></div><div><strong>Execution evidence examples</strong><span>Sample records below are not live backend history. API-persisted records, when available, are shown separately above.</span></div><DemoTag /></div>
      <Panel className="execution-table-panel">
        <div className="panel-title-row"><div><h3>Recent executions <span className="candidate-count">{demoExecutions.length}</span></h3><p>Select a run to review its recorded summary and workflow.</p></div><DemoTag /></div>
        <div className="candidate-table-wrap">
          <table className="data-table executions-table">
            <thead><tr><th>Execution</th><th>Intent</th><th>Started</th><th>Status</th><th>Selected path</th><th>Deployment verification</th><th /></tr></thead>
            <tbody>{demoExecutions.map((execution) => <tr key={execution.id} className={selected.id === execution.id ? "execution-active-row" : ""} onClick={() => setSelected(execution)}>
              <td><code>{execution.id.slice(0, 8)}…</code></td><td className="execution-intent">{execution.intent}</td><td>{execution.createdAt}</td><td><StatusPill tone={execution.status === "SUCCEEDED" ? "positive" : "neutral"}>{execution.status}</StatusPill></td><td className="execution-path">{execution.path}</td><td><span className="verification-cell"><Check size={13} /> {execution.verification}</span></td><td><ChevronRight size={15} className="muted-icon" /></td>
            </tr>)}</tbody>
          </table>
        </div>
      </Panel>
      <Panel className="execution-detail-panel">
        <div className="panel-title-row detail-run-header"><div><div className="detail-run-id"><FileText size={16} /><code>{selected.id}</code><StatusPill tone="positive">{selected.status}</StatusPill></div><h3>{selected.intent}</h3><p>{selected.createdAt} <span>·</span> Record shown as demo data</p></div><button className="button-secondary compact-button"><FileText size={14} /> Evidence preview <ArrowRight size={13} /></button></div>
        <div className="execution-summary-grid">
          <div className="execution-summary-cell"><span>Selected physical path</span><strong><GitBranch size={14} /> {selected.path}</strong></div>
          <div className="execution-summary-cell"><span>Final measurement</span><strong>{selected.result}</strong></div>
          <div className="execution-summary-cell"><span>Deployment readback</span><strong><ShieldCheck size={14} /> {selected.verification}</strong></div>
        </div>
        <div className="timeline-heading"><span>WORKFLOW TIMELINE</span><span>{selected.id === demoExecutions[0].id ? "RECORDED EXECUTION EVIDENCE" : "DETAILS NOT INCLUDED IN THIS SUMMARY"}</span></div>
        {selected.id === demoExecutions[0].id ? <div className="execution-timeline">{timeline.map((item, index) => <div className="timeline-item" key={item.name}><div className={`timeline-marker ${item.done ? "timeline-done" : ""}`}>{item.done ? <Check size={11} /> : <CircleDot size={11} />}{index < timeline.length - 1 && <i />}</div><div className="timeline-copy"><strong>{item.name}</strong><span>{item.detail}</span></div><time>{item.time}</time></div>)}</div> : <div className="timeline-unavailable">This summary does not contain a detailed per-stage timeline. No stage events are inferred.</div>}
      </Panel>
    </div>
  );
}
