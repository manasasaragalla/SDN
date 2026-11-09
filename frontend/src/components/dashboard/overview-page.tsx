"use client";

import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleDot,
  GitBranch,
  Gauge,
  Network,
  Route,
  Send,
  Scale,
  Workflow,
  Zap,
} from "lucide-react";
import type { PageId } from "@/types/dashboard";
import { activityItems, demoMetrics } from "@/lib/demo-data";
import { DemoTag, Panel, SectionHeading } from "@/components/ui/dashboard-ui";
import { Button } from "@/components/ui/button";

const stats = [
  { label: "Switches", value: "5", detail: "All operational", icon: Network, color: "blue" },
  { label: "Hosts", value: "4", detail: "2 active endpoints", icon: CircleDot, color: "violet" },
  { label: "Active links", value: "9", detail: "9 / 9 links operational", icon: GitBranch, color: "teal" },
  { label: "Active flows", value: "32", detail: "Across 4 switches", icon: Workflow, color: "amber" },
];

const activityIcons = [Check, Route, Scale, Network, Send];

export function OverviewPage({ navigate }: { navigate: (id: PageId) => void }) {
  return (
    <div className="page-stack">
      <div className="demo-banner"><div className="demo-banner-icon"><Zap size={17} /></div><div><strong>Illustrative demo environment</strong><span>Displayed topology and measurements are sample data—not live Mininet telemetry.</span></div><DemoTag /></div>

      <section>
        <SectionHeading title="Network summary" description="Current inventory and controller plane status" action={<span className="updated-note"><span className="live-dot" /> Snapshot · Demo</span>} />
        <div className="stat-grid">
          {stats.map(({ label, value, detail, icon: Icon, color }) => (
            <Panel key={label} className="stat-card">
              <div className={`stat-icon icon-${color}`}><Icon size={18} /></div>
              <div className="stat-copy"><span>{label}</span><strong>{value}</strong><small><span className="tiny-check">✓</span> {detail}</small></div>
              <span className="stat-card-menu">•••</span>
            </Panel>
          ))}
        </div>
      </section>

      <section>
        <SectionHeading title="Network health" description="Recent observed metrics from sample execution records" action={<DemoTag />} />
        <div className="health-grid">
          {demoMetrics.map((metric, index) => {
            const Icon = [Gauge, ArrowUpRight, ArrowDownRight, Route][index];
            return (
              <Panel className="health-card" key={metric.label}>
                <div className="health-card-head"><span>{metric.label}</span><span className="health-icon"><Icon size={16} /></span></div>
                <div className="health-value">{metric.value}<small>{metric.unit}</small></div>
                <div className="health-card-foot"><span className="trend-positive">{metric.change}</span><span>vs. previous run</span></div>
                {index < 3 && <div className={`sparkline sparkline-${index}`}><svg viewBox="0 0 180 34" preserveAspectRatio="none" aria-hidden="true"><path d={["M1 22 C17 20 21 24 35 18 S57 23 72 15 S92 18 105 13 S126 19 141 8 S163 12 179 4", "M1 25 C22 21 27 17 42 21 S66 10 82 15 S102 4 120 11 S151 5 179 2", "M1 12 C18 10 24 15 38 8 S61 13 74 9 S100 17 118 10 S149 13 179 5"][index]} /></svg></div>}
              </Panel>
            );
          })}
        </div>
      </section>

      <div className="overview-lower">
        <Panel className="topology-overview">
          <div className="panel-title-row"><div><h3>Topology snapshot</h3><p>Diamond · 5 switches · 4 hosts</p></div><button className="text-button" onClick={() => navigate("topology")}>Explore topology <ArrowRight size={14} /></button></div>
          <div className="topology-schematic" aria-label="Illustrative diamond network topology">
            <div className="schematic-host host-left">h1</div>
            <div className="schematic-switch switch-entry">s1</div>
            <div className="schematic-switch switch-top-a">s2</div>
            <div className="schematic-switch switch-bottom-a">s3</div>
            <div className="schematic-switch switch-top-b">s4</div>
            <div className="schematic-switch switch-bottom-b">s5</div>
            <div className="schematic-host host-right">h4</div>
            <i className="schematic-link line-h1" /><i className="schematic-link line-a" /><i className="schematic-link line-b" /><i className="schematic-link line-c" /><i className="schematic-link line-d" /><i className="schematic-link line-e" /><i className="schematic-link line-f" />
            <span className="schematic-label label-10-a">10 Mbps</span><span className="schematic-label label-50-a">50 Mbps</span><span className="schematic-label label-10-b">10 Mbps</span><span className="schematic-label label-50-b">50 Mbps</span>
          </div>
          <div className="legend-row"><span><i className="legend-dot green" /> Active link</span><span><i className="legend-dot blue" /> Selected path</span><span>Illustrative topology</span></div>
        </Panel>
        <Panel className="activity-panel">
          <div className="panel-title-row"><div><h3>Recent activity</h3><p>Latest network operations</p></div><button className="icon-button subtle-button" aria-label="Activity options"><ChevronRight size={17} /></button></div>
          <div className="activity-list">
            {activityItems.map((item, index) => {
              const Icon = activityIcons[index];
              return <div className="activity-item" key={item.label}><div className={`activity-icon activity-${index}`}><Icon size={14} /></div><div className="activity-content"><strong>{item.label}</strong><span>{item.detail}</span></div><time>{item.time}</time></div>;
            })}
          </div>
          <button className="activity-footer" onClick={() => navigate("executions")}>View execution history <ArrowRight size={14} /></button>
        </Panel>
      </div>

      <div className="quick-actions">
        <div><strong>What would you like to do?</strong><span>Submit a network requirement or inspect current paths.</span></div>
        <Button variant="primary" className="button-primary" onClick={() => navigate("intents")}><Send size={15} /> Create an intent</Button>
        <Button variant="secondary" className="button-secondary" onClick={() => navigate("planning")}><Route size={15} /> View path planning</Button>
      </div>
    </div>
  );
}
