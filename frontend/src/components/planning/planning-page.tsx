"use client";

import { useSyncExternalStore } from "react";
import { ArrowDown, ArrowRight, CircleHelp, Info, Route } from "lucide-react";
import { useActiveTopology } from "@/hooks/use-active-topology";
import {
  getPlanningPreviewSnapshot,
  subscribePlanningPreview,
} from "@/lib/planning-preview.mjs";
import { Panel, StatusPill } from "@/components/ui/dashboard-ui";
import { Button } from "@/components/ui/button";
import type { PageId } from "@/types/dashboard";
import type { TopologyPlanningCandidate } from "@/types/api";

function stateTone(state: string): "positive" | "warning" | "negative" | "neutral" | "info" {
  if (state === "SATISFIED" || state === "SELECTED" || state === "ELIGIBLE") return "positive";
  if (state === "VIOLATED" || state === "REJECTED" || state === "NO_ELIGIBLE_PATH" || state === "NO_PATH") return "negative";
  if (state === "UNKNOWN" || state === "INSUFFICIENT_CONFIGURED_DATA" || state === "INCOMPLETE_SEARCH") return "warning";
  return "neutral";
}

function candidateMetric(value: number | null, unit: string): string {
  return value == null ? "UNKNOWN" : `${value} ${unit}`;
}

function CandidateCard({ candidate }: { candidate: TopologyPlanningCandidate }) {
  const metrics = candidate.configured_metrics;
  const displayStatus = candidate.selection === "SELECTED" ? "SELECTED" : candidate.status;
  return (
    <article
      aria-label={`Candidate ${candidate.path.join(" to ")}, ${displayStatus}`}
      className={`planning-result-candidate ${candidate.selection === "SELECTED" ? "planning-result-selected" : ""}`}
    >
      <div className="planning-result-heading">
        <div>
          <strong>{candidate.path.join(" → ")}</strong>
          <code>{candidate.candidate_id}</code>
        </div>
        <div className="planning-result-badges">
          <StatusPill tone={stateTone(displayStatus)}>{displayStatus}</StatusPill>
        </div>
      </div>
      <div className="planning-result-metrics">
        <span>Hops <strong>{Math.max(0, candidate.path.length - 1)}</strong></span>
        <span>Configured bottleneck capacity <strong>{candidateMetric(metrics.bandwidth_mbps, "Mbps")}</strong></span>
        <span>Configured path delay <strong>{candidateMetric(metrics.latency_ms, "ms")}</strong></span>
        <span>Configured packet loss <strong>{candidateMetric(metrics.packet_loss_percent, "%")}</strong></span>
      </div>
      <div className="planning-physical-path">
        <strong>Physical links and ports</strong>
        {candidate.physical_links.length
          ? candidate.physical_links.map((link, index) => (
            <div key={`${link.node_a}:${link.port_a}:${link.node_b}:${link.port_b}:${index}`}>
              <code>{link.node_a}:{link.port_a ?? "?"} ↔ {link.node_b}:{link.port_b ?? "?"}</code>
              <span>
                Capacity {candidateMetric(link.capacity_mbps, "Mbps")} · delay {candidateMetric(link.delay_ms, "ms")} · loss {candidateMetric(link.packet_loss_percent, "%")} · admin {link.admin_up == null ? "UNKNOWN" : link.admin_up ? "UP" : "DOWN"}
              </span>
            </div>
          ))
          : <span>Physical link details unavailable.</span>}
      </div>
      <div className="planning-constraint-results">
        <strong>Hard-constraint evaluation</strong>
        {candidate.constraints.length
          ? candidate.constraints.map((constraint, index) => (
            <div key={`${constraint.metric}:${index}`}>
              <StatusPill tone={stateTone(constraint.status)}>{constraint.status}</StatusPill>
              <span>{constraint.metric} {constraint.comparison} {Array.isArray(constraint.threshold) ? constraint.threshold.join("–") : constraint.threshold ?? "UNKNOWN"} {constraint.unit}</span>
              <small>{constraint.reason}</small>
            </div>
          ))
          : <span>No hard constraints were requested.</span>}
      </div>
      {candidate.reasons.length > 0 && (
        <div className="planning-candidate-reasons">
          <strong>Candidate explanation</strong>
          {candidate.reasons.map((reason) => <span key={reason}>{reason}</span>)}
        </div>
      )}
    </article>
  );
}

export function PlanningPage({ navigate }: { navigate: (id: PageId) => void }) {
  const stored = useSyncExternalStore(
    subscribePlanningPreview,
    getPlanningPreviewSnapshot,
    () => null,
  );
  const topologyState = useActiveTopology();

  const preview = stored?.response ?? null;
  const plan = preview?.planning_result ?? null;
  const plannedTopology = preview?.topology_identity ?? plan?.topology_identity ?? null;
  const currentTopology = topologyState.status === "loaded" ? topologyState.topology : null;
  const topologyChanged = Boolean(
    plannedTopology
    && currentTopology
    && (plannedTopology.id !== currentTopology.id || plannedTopology.version !== currentTopology.version),
  );
  const outcome = plan?.status ?? "NOT_AVAILABLE";
  const selectedCandidate = plan?.candidates.find((candidate) => candidate.selection === "SELECTED") ?? null;

  return (
    <div className="page-stack planning-page-content">
      <div className="demo-banner">
        <div className="demo-banner-icon"><Route size={17} /></div>
        <div>
          <strong>Backend deterministic planning preview</strong>
          <span>Results below are the planner response generated for the latest submitted Intent Management preview. Planning does not deploy routes or verify flows.</span>
        </div>
        <span className="demo-tag"><span /> BACKEND PREVIEW</span>
      </div>

      {!stored ? (
        <Panel className="planning-empty">
          <div className="planning-empty-content">
            <span className="planning-empty-icon"><CircleHelp size={20} /></span>
            <div>
              <strong>No preview is available in this tab</strong>
              <span>Path Planning displays the exact backend response from Intent Management. Submit a preview to inspect its objective, constraints, candidates, and selection here.</span>
            </div>
          </div>
          <Button type="button" variant="secondary" className="button-secondary" onClick={() => navigate("intents")}>
            Open Intent Management <ArrowRight size={14} />
          </Button>
        </Panel>
      ) : !preview ? (
        <Panel className="planning-empty">
          <div className="planning-empty-content">
            <span className="planning-empty-icon"><CircleHelp size={20} /></span>
            <div>
              <strong>Saved preview is unavailable</strong>
              <span>The saved browser entry could not be read as a backend preview. Submit a new preview to replace it.</span>
            </div>
          </div>
          <Button type="button" variant="secondary" className="button-secondary" onClick={() => navigate("intents")}>
            Open Intent Management <ArrowRight size={14} />
          </Button>
        </Panel>
      ) : !plan ? (
        <Panel className="planning-empty">
          <div className="planning-empty-content">
            <span className="planning-empty-icon"><CircleHelp size={20} /></span>
            <div>
              <strong>No topology planning result was returned</strong>
              <span>The submitted intent was interpreted, but no deterministic candidate plan is available. Check the preview explanation or submit a new request.</span>
            </div>
          </div>
          {preview.explanation.length > 0 && <ul className="planning-empty-reasons">{preview.explanation.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul>}
          <Button type="button" variant="secondary" className="button-secondary" onClick={() => navigate("intents")}>
            Open Intent Management <ArrowRight size={14} />
          </Button>
        </Panel>
      ) : (
        <>
          {topologyChanged && <div className="submit-notice notice-warning" role="status">The active topology changed after this preview. The result below remains the exact historical planning response for {plannedTopology?.name} v{plannedTopology?.version}; submit a new intent preview for the current topology.</div>}
          {topologyState.status === "error" && <div className="submit-notice notice-warning" role="status">Current active topology could not be rechecked: {topologyState.error}</div>}
          <Panel className="planning-request">
            <div className="planning-request-main">
              <div className="request-avatar"><Route size={18} /></div>
              <div>
                <span className="request-label">SUBMITTED INTENT · {preview.parser_kind === "MOCK" ? "MOCK PARSER" : preview.parser}</span>
                <h3>{stored.naturalLanguage}</h3>
                <p className="planning-route">{preview.canonical_intent.scope.source} → {preview.canonical_intent.scope.destination}</p>
                <div className="planning-structured-intent">
                  <span>Source <strong>{plan.source}</strong></span>
                  <span>Destination <strong>{plan.destination}</strong></span>
                  <span>Topology <strong>{plannedTopology ? `${plannedTopology.name} · ${plannedTopology.mode} v${plannedTopology.version ?? "?"}` : "Not identified"}</strong></span>
                </div>
              </div>
            </div>
            <div className="planning-policy">
              <div><span>Active topology at planning</span><strong>{plannedTopology ? `${plannedTopology.name} · ${plannedTopology.mode} v${plannedTopology.version ?? "?"}` : "Not identified"}</strong></div>
              <div className="policy-divider" />
              <div><span>Optimization objective</span><strong>{plan.optimization ? <><ArrowDown size={14} /> {plan.optimization.direction} {plan.optimization.metric}</> : "None"}</strong></div>
              <div className="policy-divider" />
              <div><span>Planning outcome</span><StatusPill tone={stateTone(outcome)}>{outcome}</StatusPill></div>
            </div>
          </Panel>

          <Panel className="planning-constraints-panel">
            <div className="planning-section-heading">
              <div><h3><Info size={15} /> Hard constraints</h3><p>Requirements evaluated by the deterministic planner.</p></div>
              <span>{plan.constraints.length} {plan.constraints.length === 1 ? "constraint" : "constraints"}</span>
            </div>
            {plan.constraints.length
              ? <div className="planning-request-constraints">{plan.constraints.map((constraint, index) => (
                <div className="planning-request-constraint" key={`${constraint.metric}:${index}`}>
                  <strong>{constraint.metric}</strong>
                  <code>{constraint.comparison} {constraint.comparison === "BETWEEN"
                    ? `${constraint.lower_bound}–${constraint.upper_bound}`
                    : constraint.value} {constraint.unit}</code>
                </div>
              ))}</div>
              : <p className="planning-no-constraints">No hard constraints specified.</p>}
          </Panel>

          {plan.status === "NO_ELIGIBLE_PATH" && (
            <Panel className="planning-outcome-callout planning-outcome-ineligible">
              <StatusPill tone="negative">NO_ELIGIBLE_PATH</StatusPill>
              <div><strong>No candidate satisfies all hard constraints</strong><span>Candidate feasibility and rejection reasons below come directly from the backend planner. No route was selected or deployed.</span></div>
            </Panel>
          )}

          {plan.status === "SELECTED" && selectedCandidate && (
            <Panel className="planning-selected-path">
              <div className="planning-section-heading">
                <div><h3><Route size={15} /> Selected path</h3><p>Backend planner selection · not deployed or runtime-verified</p></div>
                <StatusPill tone="positive">SELECTED</StatusPill>
              </div>
              <strong className="planning-selected-route">{selectedCandidate.path.join(" → ")}</strong>
              <div className="planning-result-metrics">
                <span>Hops <strong>{Math.max(0, selectedCandidate.path.length - 1)}</strong></span>
                <span>Configured bottleneck capacity <strong>{candidateMetric(selectedCandidate.configured_metrics.bandwidth_mbps, "Mbps")}</strong></span>
                <span>Configured path delay <strong>{candidateMetric(selectedCandidate.configured_metrics.latency_ms, "ms")}</strong></span>
                <span>Configured packet loss <strong>{candidateMetric(selectedCandidate.configured_metrics.packet_loss_percent, "%")}</strong></span>
              </div>
              <p>{plan.selection_reason ?? "No selection rationale was returned."}</p>
            </Panel>
          )}

          <Panel className="planning-rationale-panel">
            <div className="planning-status-copy">
              <strong>Planner provenance and result</strong>
              <span>{plan.provenance}</span>
              <span>Plan preview generated {new Date(stored.savedAt).toLocaleString()}. This result does not imply deployment or live verification.</span>
            </div>
          </Panel>

          <Panel className="candidate-panel">
            <div className="panel-title-row candidate-header">
              <div><h3>Enumerated candidate paths <span className="candidate-count">{plan.candidate_count}</span></h3><p>Candidate order, feasibility and selection are taken directly from the backend planner.</p></div>
              <StatusPill tone={stateTone(plan.status)}>{plan.status}</StatusPill>
            </div>
            {plan.candidates.length
              ? <div className="planning-result-candidate-list">{plan.candidates.map((candidate) => <CandidateCard key={candidate.candidate_id} candidate={candidate} />)}</div>
              : <div className="timeline-unavailable">The planner returned no physical candidate paths.</div>}
          </Panel>

          <div className="constraint-note"><Info size={15} /><span>Configured capacity, delay and loss are topology attributes, not measured throughput, RTT or runtime packet-loss telemetry. This page does not deploy routes.</span></div>
        </>
      )}
    </div>
  );
}
