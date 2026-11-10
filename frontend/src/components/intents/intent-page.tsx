"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleHelp, FileJson2, Send, Sparkles } from "lucide-react";
import { DemoTag, Panel, SectionHeading, StatusPill } from "@/components/ui/dashboard-ui";
import { Button } from "@/components/ui/button";
import { API_BASE_URL, apiRequest } from "@/lib/api-client";
import type {
  ActiveTopologyResponse,
  ExecutionAcceptedResponse,
  ExecutionDetail,
  ExecutionStatusResponse,
  IntentPreviewResponse,
} from "@/types/api";

const examples = [
  "Minimize latency between the selected hosts.",
  "Maintain latency below 50 ms between the selected hosts.",
  "Ensure bandwidth is at least 20 Mbps between the selected hosts.",
  "Minimize latency between the selected hosts while maintaining bandwidth above 20 Mbps.",
  "Maximize bandwidth between the selected hosts.",
  "Keep packet loss below 1% between the selected hosts.",
];
const demoHosts = ["h1", "h2", "h3", "h4"];

function localIntentPreview(text: string, source: string, destination: string) {
  const lower = text.toLowerCase();
  const metric = lower.includes("latency") ? "latency" : lower.includes("bandwidth") ? "bandwidth" : lower.includes("packet loss") || lower.includes("packet_loss") ? "packet_loss" : null;
  const objective = metric && (lower.includes("minimiz") || lower.includes("lowest") || lower.includes("best latency"))
    ? { direction: "MINIMIZE", metric }
    : metric && (lower.includes("maximiz") || lower.includes("highest"))
      ? { direction: "MAXIMIZE", metric }
      : null;
  const constraints: { metric: string; operator: string; threshold: number; unit: string }[] = [];
  const patterns = [
    { metric: "latency", regex: /latency\s*(?:is\s*)?(below|under|less than|<=|<|at most)\s*(\d+(?:\.\d+)?)\s*(ms|milliseconds)?/i, unit: "ms" },
    { metric: "bandwidth", regex: /bandwidth\s*(?:is\s*)?(at least|above|over|>=|>)\s*(\d+(?:\.\d+)?)\s*(mbps)?/i, unit: "Mbps" },
    { metric: "packet_loss", regex: /packet(?:_|\s+)loss\s*(?:is\s*)?(below|under|less than|<=|<|at most)\s*(\d+(?:\.\d+)?)\s*(%)?/i, unit: "%" },
  ];
  for (const item of patterns) {
    const match = lower.match(item.regex);
    if (match) {
      const operatorText = match[1].toLowerCase();
      const operator = item.metric === "bandwidth"
        ? (["at least", ">="].includes(operatorText) ? "GTE" : "GT")
        : (["at most", "<="].includes(operatorText) ? "LTE" : "LT");
      constraints.push({ metric: item.metric, operator, threshold: Number(match[2]), unit: item.unit });
    }
  }
  return {
    supported: Boolean(metric && (objective || constraints.length)),
    source,
    destination,
    objective,
    constraints,
    metric,
  };
}

export function IntentPage() {
  const [text, setText] = useState("");
  const [hosts, setHosts] = useState<string[]>(API_BASE_URL ? [] : demoHosts);
  const [source, setSource] = useState(API_BASE_URL ? "" : "h1");
  const [destination, setDestination] = useState(API_BASE_URL ? "" : "h4");
  const [activeTopology, setActiveTopology] = useState<ActiveTopologyResponse["topology"]>(null);
  const [topologyLoadError, setTopologyLoadError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [serverPreview, setServerPreview] = useState<IntentPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [executionStarted, setExecutionStarted] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionDetail | null>(null);
  const statusPoll = useRef<AbortController | null>(null);
  const activeTopologyRef = useRef<ActiveTopologyResponse["topology"]>(null);
  const sourceRef = useRef(source);
  const destinationRef = useRef(destination);
  const preview = useMemo(() => localIntentPreview(text, source, destination), [text, source, destination]);
  const capabilityLabel = serverPreview
    ? `Capabilities ${serverPreview.capability_resolution.eligibility === "CAPABILITY_READY"
      ? "ready"
      : serverPreview.capability_resolution.eligibility === "CONDITIONAL"
        ? "conditional"
        : "not ready"}`
    : null;
  const planningLabel = serverPreview?.planning_eligible === true
    ? "Eligible candidate selected"
    : serverPreview?.planning_eligible === false
      ? serverPreview.planning_result?.status === "NO_PATH"
        ? "Planning ineligible · no path"
        : "Planning ineligible · no eligible candidate"
      : serverPreview?.planning_result
        ? "Planning result inconclusive"
        : "Planning not assessed";

  useEffect(() => {
    sourceRef.current = source;
    destinationRef.current = destination;
  }, [source, destination]);

  useEffect(() => () => {
    statusPoll.current?.abort();
  }, []);

  useEffect(() => {
    if (!API_BASE_URL) return;
    let active = true;
    const refreshHosts = async () => {
      try {
        const result = await apiRequest<ActiveTopologyResponse>("/api/v1/topologies/active");
        if (!active) return;
        const previous = activeTopologyRef.current;
        const changed = previous?.id !== result.topology?.id
          || previous?.version !== result.topology?.version;
        if (previous && changed) {
          setSubmitted(false);
          setServerPreview(null);
          setPreviewError(null);
          setExecutionMessage(null);
          setExecutionStarted(false);
          setExecutionResult(null);
        }
        activeTopologyRef.current = result.topology;
        setActiveTopology(result.topology);
        setTopologyLoadError(null);
        const actualHosts = result.topology
          ? Object.keys(result.topology.graph.hosts).sort()
          : [];
        setHosts(actualHosts);
        const nextSource = actualHosts.includes(sourceRef.current)
          ? sourceRef.current
          : actualHosts[0] ?? "";
        setSource(nextSource);
        setDestination((current) => actualHosts.includes(destinationRef.current) && destinationRef.current !== nextSource
          ? current
          : actualHosts.find((host) => host !== nextSource) ?? "");
      } catch (error) {
        if (active) {
          setTopologyLoadError(error instanceof Error ? error.message : "Active topology could not be loaded.");
        }
      }
    };
    void refreshHosts();
    const timer = window.setInterval(() => void refreshHosts(), 5000);
    window.addEventListener("focus", refreshHosts);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshHosts);
    };
  }, []);

  const resetPreview = () => {
    setSubmitted(false);
    setServerPreview(null);
    setPreviewError(null);
    setExecutionMessage(null);
    setExecutionStarted(false);
    setExecutionResult(null);
    statusPoll.current?.abort();
    statusPoll.current = null;
  };

  const monitorExecution = async (
    executionId: string,
    signal: AbortSignal,
  ): Promise<void> => {
    try {
      while (!signal.aborted) {
        const status = await apiRequest<ExecutionStatusResponse>(
          `/api/v1/executions/${encodeURIComponent(executionId)}/status`,
          { signal },
        );
        const latestEvent = status.events.at(-1);
        if (latestEvent) {
          setExecutionMessage(latestEvent.detail ?? latestEvent.event.replaceAll("_", " "));
        }
        if (status.status !== "RUNNING") {
          setExecuting(false);
          const result = await apiRequest<ExecutionDetail>(
            `/api/v1/executions/${encodeURIComponent(executionId)}`,
            { signal },
          );
          setExecutionResult(result);
          setExecutionMessage(`Execution ${executionId} finished with status ${result.status}.`);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (error) {
      if (signal.aborted) return;
      setExecuting(false);
      setExecutionMessage(
        `Execution ${executionId} was accepted, but its status could not be loaded: ${
          error instanceof Error ? error.message : "unknown API error"
        }`,
      );
    }
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    setServerPreview(null);
    setPreviewError(null);
    setExecutionMessage(null);
    setExecutionStarted(false);
    setExecutionResult(null);
    statusPoll.current?.abort();
    if (!API_BASE_URL) return;

    setSubmitting(true);
    try {
      const result = await apiRequest<IntentPreviewResponse>("/api/v1/intents/preview", {
        method: "POST",
        body: JSON.stringify({
          natural_language: text,
          source,
          destination,
        }),
      });
      setServerPreview(result);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Intent preview failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const execute = async () => {
    if (!serverPreview?.execution_eligible || !API_BASE_URL) return;
    setExecuting(true);
    setExecutionMessage("Submitting execution request…");
    try {
      const accepted = await apiRequest<ExecutionAcceptedResponse>("/api/v1/executions", {
        method: "POST",
        body: JSON.stringify({ preview_id: serverPreview.preview_id }),
      });
      setExecutionStarted(true);
      setExecutionMessage(`Execution ${accepted.execution_id} accepted and running.`);
      const controller = new AbortController();
      statusPoll.current = controller;
      void monitorExecution(accepted.execution_id, controller.signal);
    } catch (error) {
      setExecutionMessage(error instanceof Error ? error.message : "Execution request failed.");
      setExecuting(false);
    }
  };

  return (
    <div className="page-stack">
      {API_BASE_URL
        ? <div className="demo-banner"><div className="demo-banner-icon"><Sparkles size={17} /></div><div><strong>Backend preview enabled</strong><span>Only explicit preview and execution requests reach the API. Other dashboard measurements remain demo data.</span></div><DemoTag /></div>
        : <div className="demo-banner"><div className="demo-banner-icon"><Sparkles size={17} /></div><div><strong>Intent parsing is not connected</strong><span>Previews below are local examples only. No LLM, backend, or network operation is invoked.</span></div><DemoTag /></div>}
      <div className="intent-layout">
        <div className="intent-main-column">
          <Panel className="intent-form-panel">
            <SectionHeading title="Describe your network intent" description="Use plain language to express the outcome you need." action={<DemoTag />} />
            <form onSubmit={submit}>
              <label className="form-label" htmlFor="intent-text">Natural language requirement</label>
              <textarea id="intent-text" className="intent-textarea" value={text} onChange={(event) => { setText(event.target.value); resetPreview(); }} placeholder="e.g. Minimize latency between h1 and h4 while maintaining bandwidth above 20 Mbps" />
              <div className="char-count">{text.length} characters <span>·</span> {API_BASE_URL ? "Explicit backend preview" : "Demo preview only"}</div>
              <div className="endpoint-selectors">
                <label><span>Source host</span><div className="select-wrap"><select value={source} onChange={(event) => { setSource(event.target.value); resetPreview(); }} disabled={!hosts.length}>{hosts.map((host) => <option key={host}>{host}</option>)}</select><ChevronDown size={15} /></div></label>
                <ArrowRight size={17} className="selector-arrow" />
                <label><span>Destination host</span><div className="select-wrap"><select value={destination} onChange={(event) => { setDestination(event.target.value); resetPreview(); }} disabled={!hosts.length}>{hosts.map((host) => <option key={host}>{host}</option>)}</select><ChevronDown size={15} /></div></label>
                <Button type="submit" variant="primary" className="button-primary submit-intent" disabled={!text.trim() || !source || !destination || source === destination || submitting}><Send size={15} /> {submitting ? "Parsing…" : API_BASE_URL ? "Preview with backend" : "Preview intent"}</Button>
              </div>
              {source === destination && <div className="inline-warning">Source and destination must be different hosts.</div>}
              {API_BASE_URL && !activeTopology && <div className="submit-notice notice-warning" role="status"><CircleHelp size={15} /><span>{topologyLoadError ?? "No active topology. Create or import a DESIGN topology in Network Topology, then activate it to populate these selectors."}</span></div>}
              {previewError && <div className="submit-notice notice-warning" role="alert"><CircleHelp size={15} /><span>Backend preview unavailable: {previewError}</span></div>}
              {submitted && !API_BASE_URL && <div className={`submit-notice ${preview.supported ? "notice-info" : "notice-warning"}`}><CircleHelp size={15} /><span>{preview.supported ? "Local structured preview generated. It has not been validated by the backend and cannot be deployed." : "This local example cannot interpret the request. Backend capability and ambiguity checks are not available."}</span></div>}
            </form>
          </Panel>

          <Panel className="example-panel">
            <div className="panel-title-row"><div><h3>Try an example</h3><p>Choose an example to populate the intent field</p></div><span className="examples-label">SAMPLE INPUTS</span></div>
            <div className="example-list">{examples.map((example) => <button key={example} className="example-item" onClick={() => { setText(example); resetPreview(); }}><span>{example}</span><ArrowRight size={14} /></button>)}</div>
          </Panel>
        </div>

        <Panel className="parsed-panel">
          <div className="panel-title-row"><div className="parsed-title"><div className="parsed-icon"><FileJson2 size={17} /></div><div><h3>Structured preview</h3><p>{API_BASE_URL ? "Backend capability assessment" : "Local illustrative interpretation"}</p></div></div><span className="local-badge">{API_BASE_URL ? "API" : "LOCAL"}</span></div>
          {API_BASE_URL ? serverPreview ? (
            <div className="parsed-content">
              <div className="parsed-status parsed-status-group">
                <StatusPill tone="positive">Intent valid</StatusPill>
                {capabilityLabel && <StatusPill tone={serverPreview.capability_resolution.eligibility === "CAPABILITY_READY" ? "positive" : serverPreview.capability_resolution.eligibility === "CONDITIONAL" ? "warning" : "negative"}>{capabilityLabel}</StatusPill>}
                {planningLabel && <StatusPill tone={serverPreview.planning_eligible === true ? "positive" : serverPreview.planning_eligible === false ? "negative" : "warning"}>Planning: {planningLabel}</StatusPill>}
                <StatusPill tone={serverPreview.execution_status === "AVAILABLE" ? "positive" : "neutral"}>
                  {serverPreview.execution_status === "AVAILABLE" ? "Execution available" : serverPreview.topology_identity?.mode === "DESIGN" ? "Execution unavailable · DESIGN topology" : "Execution unavailable"}
                </StatusPill>
                <span>{serverPreview.parser_kind === "MOCK" ? "Deterministic mock parser · limited language coverage" : `${serverPreview.parser_kind} · ${serverPreview.parser}`}</span>
              </div>
              <div className="preview-route"><span className="endpoint-chip">{serverPreview.canonical_intent.scope.source}</span><ArrowRight size={14} /><span className="endpoint-chip">{serverPreview.canonical_intent.scope.destination}</span></div>
              {serverPreview.topology_identity && <div className="preview-fields">
                <div className="preview-field"><span>Topology</span><strong>{serverPreview.topology_identity.name}</strong></div>
                <div className="preview-field"><span>Mode / version</span><strong>{serverPreview.topology_identity.mode}{serverPreview.topology_identity.version ? ` · v${serverPreview.topology_identity.version}` : ""}</strong></div>
              </div>}
              <div className="preview-fields">
                <div className="preview-field"><span>Source</span><strong>{serverPreview.canonical_intent.scope.source}</strong></div>
                <div className="preview-field"><span>Destination</span><strong>{serverPreview.canonical_intent.scope.destination}</strong></div>
                <div className="preview-field"><span>Optimization</span><strong>{serverPreview.canonical_intent.optimization ? `${serverPreview.canonical_intent.optimization.direction} ${serverPreview.canonical_intent.optimization.metric}` : "None"}</strong></div>
              </div>
              <div className="preview-constraints"><span className="preview-section-label">Hard constraints</span>
                {serverPreview.canonical_intent.constraints.length ? serverPreview.canonical_intent.constraints.map((constraint, index) => <div key={`${constraint.metric}-${index}`} className="constraint-preview-row"><span>{constraint.metric}</span><code>{constraint.comparison === "BETWEEN" ? `${constraint.lower_bound}–${constraint.upper_bound}` : `${constraint.comparison} ${constraint.value}`} {constraint.unit}</code></div>) : <div className="empty-constraint">No hard constraints in the canonical intent.</div>}
              </div>
              {serverPreview.unsupported_or_conditional.length > 0 && <div className="preview-caveat"><CircleHelp size={14} /><span>{serverPreview.unsupported_or_conditional.join(" ")}</span></div>}
              {serverPreview.explanation.map((message) => <div key={message} className="preview-caveat"><CircleHelp size={14} /><span>{message}</span></div>)}
              {serverPreview.planning_result && <div className="preview-candidates">
                <div className="preview-section-label">Deterministic topology plan · {serverPreview.planning_result.status} · {serverPreview.planning_result.candidate_count} candidates</div>
                <div className="preview-fields">
                  <div className="preview-field"><span>Planning scope</span><strong>{serverPreview.planning_result.source} → {serverPreview.planning_result.destination}</strong></div>
                  <div className="preview-field"><span>Planning objective</span><strong>{serverPreview.planning_result.optimization ? `${serverPreview.planning_result.optimization.direction} ${serverPreview.planning_result.optimization.metric}` : "None"}</strong></div>
                </div>
                {serverPreview.planning_result.selection_reason && <p className="inspector-note">{serverPreview.planning_result.selection_reason}</p>}
                {serverPreview.planning_result.candidates.map((candidate) => (
                  <div className={`preview-candidate ${candidate.selection === "SELECTED" ? "preview-candidate-selected" : ""}`} key={candidate.candidate_id}>
                    <div className="preview-candidate-heading">
                      <strong>{candidate.path.join(" → ")}</strong>
                      <StatusPill tone={candidate.selection === "SELECTED" ? "positive" : candidate.status === "REJECTED" ? "negative" : candidate.status === "UNKNOWN" ? "warning" : "neutral"}>
                        {candidate.selection === "SELECTED" ? "SELECTED" : candidate.status}
                      </StatusPill>
                    </div>
                    <span>Configured bottleneck capacity: {candidate.configured_metrics.bandwidth_mbps == null ? "unknown" : `${candidate.configured_metrics.bandwidth_mbps} Mbps`} · configured path delay: {candidate.configured_metrics.latency_ms == null ? "unknown" : `${candidate.configured_metrics.latency_ms} ms`}</span>
                    {candidate.constraints.map((constraint, index) => <small key={`${candidate.candidate_id}-${constraint.metric}-${index}`}>{constraint.metric} {constraint.status}: {constraint.reason}</small>)}
                    {candidate.reasons.map((reason) => <small key={`${candidate.candidate_id}-${reason}`}>{reason}</small>)}
                  </div>
                ))}
                <p className="inspector-note">{serverPreview.planning_result.provenance}</p>
              </div>}
              {serverPreview.execution_eligible && <Button type="button" variant="primary" className="button-primary" disabled={executing || executionStarted} onClick={() => void execute()}><Send size={14} /> {executionStarted ? "Execution submitted" : executing ? "Submitting…" : "Execute intent"}</Button>}
              {executionMessage && <div className="submit-notice notice-info" role="status"><CircleHelp size={15} /><span>{executionMessage}</span></div>}
              {executionResult && <div className="execution-result" role="status">
                <p><strong>Status:</strong> {executionResult.status}</p>
                <p><strong>Selected path:</strong> {executionResult.selected_path?.join(" → ") ?? "No path selected"}</p>
                <p><strong>Final measurement:</strong> {executionResult.final_measurement ? JSON.stringify(executionResult.final_measurement) : "Not recorded"}</p>
                {executionResult.evidence && <details>
                  <summary>Full execution evidence</summary>
                  <pre>{JSON.stringify(executionResult.evidence, null, 2)}</pre>
                </details>}
              </div>}
            </div>
          ) : previewError ? <div className="preview-unsupported" role="alert"><CircleHelp size={20} /><strong>{previewError.startsWith("Clarification required:") ? "Intent interpretation · Clarification required" : "Backend preview failed"}</strong><span>{previewError} No planning result is generated until the intent is clarified. Demo interpretation is intentionally not substituted for the unavailable backend response.</span></div> : (
            <div className="preview-empty"><div className="preview-empty-icon"><FileJson2 size={21} /></div><strong>{text.trim() ? "Preview is waiting for backend validation" : "Your parsed intent will appear here"}</strong><span>Submit an intent to request parsing and capability resolution from the configured backend.</span><div className="preview-empty-flow"><span>Intent</span><ArrowRight size={12} /><span>Backend preview</span></div></div>
          ) : text.trim() ? preview.supported ? (
            <div className="parsed-content">
              <div className="parsed-status"><StatusPill tone="info">Preview only</StatusPill><span>Not backend-validated</span></div>
              <div className="preview-route"><span className="endpoint-chip">{preview.source}</span><ArrowRight size={14} /><span className="endpoint-chip">{preview.destination}</span></div>
              <div className="preview-fields">
                <div className="preview-field"><span>Source</span><strong>{preview.source}</strong></div>
                <div className="preview-field"><span>Destination</span><strong>{preview.destination}</strong></div>
                <div className="preview-field"><span>Optimization</span><strong>{preview.objective ? `${preview.objective.direction} ${preview.objective.metric}` : "None detected"}</strong></div>
              </div>
              <div className="preview-constraints"><span className="preview-section-label">Detected constraints</span>
                {preview.constraints.length ? preview.constraints.map((constraint) => <div key={constraint.metric} className="constraint-preview-row"><span>{constraint.metric}</span><code>{constraint.operator} {constraint.threshold} {constraint.unit}</code></div>) : <div className="empty-constraint">No hard constraints detected by this demo parser.</div>}
              </div>
              <div className="preview-caveat"><CircleHelp size={14} /><span>Supported metrics, units, and operators must be confirmed by actual backend capability resolution.</span></div>
            </div>
          ) : <div className="preview-unsupported"><CircleHelp size={20} /><strong>Not recognized by the demo parser</strong><span>The backend may support more capabilities; this UI preview is intentionally limited and is not an authoritative validation.</span></div> : (
            <div className="preview-empty"><div className="preview-empty-icon"><FileJson2 size={21} /></div><strong>Your parsed intent will appear here</strong><span>Enter an example or write a requirement to see a local structured preview.</span><div className="preview-empty-flow"><span>Natural language</span><ArrowRight size={12} /><span>Structured preview</span></div></div>
          )}
          <div className="parsed-panel-foot"><Check size={14} /><span>The LLM should return structured intent only. Network configuration and deployment remain deterministic backend responsibilities.</span></div>
        </Panel>
      </div>
    </div>
  );
}
