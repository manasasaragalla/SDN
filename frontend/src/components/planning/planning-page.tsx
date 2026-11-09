import { ArrowDown, CircleHelp, ExternalLink, Info, Route } from "lucide-react";
import { demoCandidates } from "@/lib/demo-data";
import { DemoTag, Panel, StatusPill } from "@/components/ui/dashboard-ui";

function stateTone(state: string): "positive" | "warning" | "negative" | "neutral" | "info" {
  if (state === "SATISFIED" || state === "SELECTED" || state === "CANDIDATE") return "positive";
  if (state === "VIOLATED" || state === "PROVEN_INFEASIBLE") return "negative";
  if (state === "UNKNOWN") return "warning";
  return "neutral";
}

export function PlanningPage() {
  return (
    <div className="page-stack">
      <div className="demo-banner"><div className="demo-banner-icon"><Route size={17} /></div><div><strong>Candidate evaluation · demo evidence</strong><span>Example values are illustrative and are not a current live topology query.</span></div><DemoTag /></div>
      <Panel className="planning-request">
        <div className="planning-request-main"><div className="request-avatar"><Route size={18} /></div><div><span className="request-label">ACTIVE PLANNING EXAMPLE</span><h3>Minimize latency between h1 and h4</h3><p>Constrained by measured bandwidth ≥ 20 Mbps</p></div></div>
        <div className="planning-policy"><div><span>Hard constraint</span><strong>bandwidth <b>GTE</b> 20 Mbps</strong></div><div className="policy-divider" /><div><span>Optimization objective</span><strong><ArrowDown size={14} /> Minimize latency</strong></div></div>
      </Panel>
      <Panel className="candidate-panel">
        <div className="panel-title-row candidate-header"><div><h3>Candidate paths <span className="candidate-count">2</span></h3><p>Hard constraints are evaluated first; optimization ranks only eligible candidates.</p></div><DemoTag /></div>
        <div className="candidate-table-wrap">
          <table className="data-table candidate-table">
            <thead><tr><th>Candidate / physical path</th><th>Hops</th><th>Bottleneck</th><th>Latency</th><th>Bandwidth</th><th>Packet loss</th><th>Feasibility</th><th>Constraint</th><th>Selection</th></tr></thead>
            <tbody>{demoCandidates.slice(0, 2).map((candidate) => (
              <tr key={candidate.id} className={candidate.selection === "SELECTED" ? "selected-row" : ""}>
                <td><div className="candidate-path-cell"><code>{candidate.id}</code><strong>{candidate.path.join(" → ")}</strong></div></td>
                <td>{candidate.path.length - 1}</td>
                <td><span className="capacity-value">{candidate.bottleneckMbps} Mbps</span></td>
                <td>{candidate.latencyMs === null ? <span className="unknown-value">—</span> : <strong>{candidate.latencyMs} ms</strong>}</td>
                <td>{candidate.bandwidthMbps === null ? <span className="unknown-value">—</span> : <strong>{candidate.bandwidthMbps} Mbps</strong>}</td>
                <td>{candidate.packetLossPercent === null ? <span className="unknown-value">—</span> : `${candidate.packetLossPercent}%`}</td>
                <td><StatusPill tone={stateTone(candidate.feasibility)}>{candidate.feasibility}</StatusPill></td>
                <td><StatusPill tone={stateTone(candidate.constraint)}>{candidate.constraint}</StatusPill></td>
                <td><StatusPill tone={candidate.selection === "SELECTED" ? "info" : "neutral"}>{candidate.selection}</StatusPill></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="candidate-reasons">{demoCandidates.slice(0, 2).map((candidate) => <div className={`candidate-reason ${candidate.selection === "SELECTED" ? "reason-selected" : ""}`} key={candidate.id}><span className="reason-bullet" /><div><strong>{candidate.path[2] === "s2" ? "Upper route" : "Lower route"}</strong><span>{candidate.reason}</span></div><span className="reason-value">{candidate.path[2] === "s2" ? "Static infeasibility" : "Selected · lowest measured RTT"}</span></div>)}</div>
      </Panel>

      <div className="planning-bottom-grid">
        <Panel><div className="panel-title-row"><div><h3>Evaluation sequence</h3><p>Hard gates precede objective ranking</p></div><Info size={15} className="muted-icon" /></div><div className="evaluation-steps"><div className="evaluation-step step-complete"><span>1</span><div><strong>Enumerate physical paths</strong><small>2 candidates discovered from topology</small></div></div><div className="evaluation-step step-complete"><span>2</span><div><strong>Check static feasibility</strong><small>Exclude paths that cannot meet capacity bounds</small></div></div><div className="evaluation-step step-complete"><span>3</span><div><strong>Measure and evaluate constraints</strong><small>Use fresh candidate-bound observations</small></div></div><div className="evaluation-step step-current"><span>4</span><div><strong>Rank eligible paths</strong><small>Optimize latency only among passing candidates</small></div></div><div className="evaluation-step"><span>5</span><div><strong>Compile, deploy, verify</strong><small>Final preflight and flow readback required</small></div></div></div></Panel>
        <Panel><div className="panel-title-row"><div><h3>State legend</h3><p>Evaluation and selection outcomes</p></div><CircleHelp size={15} className="muted-icon" /></div><div className="state-legend"><div><StatusPill tone="positive">SATISFIED</StatusPill><span>All applicable hard constraints pass</span></div><div><StatusPill tone="negative">VIOLATED</StatusPill><span>Measured evidence failed a constraint</span></div><div><StatusPill tone="warning">UNKNOWN</StatusPill><span>Evidence is missing or not current</span></div><div><StatusPill tone="negative">PROVEN_INFEASIBLE</StatusPill><span>Static bound rules out feasibility</span></div><div><StatusPill tone="info">SELECTED</StatusPill><span>Chosen after eligibility and ranking</span></div><div><StatusPill>SKIPPED</StatusPill><span>Not probed or ranked</span></div></div></Panel>
      </div>
      <div className="constraint-note"><Info size={15} /><span>Configured link capacity is a static feasibility bound. It is not a substitute for measured throughput when evaluating runtime constraints or maximizing bandwidth.</span><button aria-label="More about evaluation"><ExternalLink size={14} /></button></div>
    </div>
  );
}
