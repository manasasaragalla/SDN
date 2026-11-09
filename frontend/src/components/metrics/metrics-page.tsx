"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, ArrowDownRight, ArrowUpRight, Gauge, Radio, TrendingUp } from "lucide-react";
import { DemoTag, Panel } from "@/components/ui/dashboard-ui";

const latencyData = [
  { time: "14:00", value: 2.8 }, { time: "14:10", value: 2.3 }, { time: "14:20", value: 2.5 },
  { time: "14:30", value: 1.9 }, { time: "14:40", value: 2.2 }, { time: "14:50", value: 1.8 },
  { time: "15:00", value: 2.1 }, { time: "15:10", value: 1.7 }, { time: "15:20", value: 2.0 },
];
const bandwidthData = [
  { time: "14:00", value: 37 }, { time: "14:10", value: 41 }, { time: "14:20", value: 38 },
  { time: "14:30", value: 44 }, { time: "14:40", value: 42 }, { time: "14:50", value: 47 },
  { time: "15:00", value: 43 }, { time: "15:10", value: 46 }, { time: "15:20", value: 45.5 },
];
const lossData = [
  { time: "14:00", value: 0.06 }, { time: "14:10", value: 0.02 }, { time: "14:20", value: 0.04 },
  { time: "14:30", value: 0 }, { time: "14:40", value: 0.03 }, { time: "14:50", value: 0.01 },
  { time: "15:00", value: 0.02 }, { time: "15:10", value: 0 }, { time: "15:20", value: 0.02 },
];
const throughputData = [
  { time: "14:00", inbound: 31, outbound: 25 }, { time: "14:10", inbound: 34, outbound: 29 },
  { time: "14:20", inbound: 30, outbound: 27 }, { time: "14:30", inbound: 39, outbound: 33 },
  { time: "14:40", inbound: 37, outbound: 34 }, { time: "14:50", inbound: 43, outbound: 36 },
  { time: "15:00", inbound: 40, outbound: 35 }, { time: "15:10", inbound: 46, outbound: 40 },
  { time: "15:20", inbound: 45.5, outbound: 41 },
];

function MetricChart({ title, description, data, color, unit, icon: Icon, domain }: {
  title: string; description: string; data: { time: string; value: number }[];
  color: string; unit: string; icon: typeof Gauge; domain?: [number, number];
}) {
  const gradientId = `gradient-${title.toLowerCase().replaceAll(" ", "-")}`;
  return (
    <Panel className="chart-panel">
      <div className="chart-heading"><div><div className="chart-title"><span className="chart-icon"><Icon size={15} /></span><h3>{title}</h3></div><p>{description}</p></div><button className="chart-menu" aria-label={`${title} chart options`}>•••</button></div>
      <div className="chart-stat"><strong>{data[data.length - 1].value}</strong><span>{unit}</span><small><ArrowDownRight size={13} /> Demo sample</small></div>
      <div className="chart-area">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 6, left: -20, bottom: 0 }}>
            <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.22} /><stop offset="95%" stopColor={color} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
            <XAxis dataKey="time" tick={{ fill: "var(--text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={20} />
            <YAxis domain={domain ?? ["auto", "auto"]} tick={{ fill: "var(--text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 5, color: "var(--text)", fontSize: 12, fontFamily: "var(--font-geist-mono)" }} formatter={(value) => [`${value} ${unit}`, title]} labelStyle={{ color: "var(--text-secondary)" }} />
            <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} activeDot={{ r: 4, fill: color, stroke: "var(--sidebar)", strokeWidth: 2 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-footer"><span>DEMO MEASUREMENT</span><span>Sample time window · 80 min</span></div>
    </Panel>
  );
}

export function MetricsPage() {
  return (
    <div className="page-stack">
      <div className="demo-banner"><div className="demo-banner-icon"><Activity size={17} /></div><div><strong>Sample metric series</strong><span>These charts are illustrative only; they are not live measurements or a telemetry feed.</span></div><DemoTag /></div>
      <div className="metrics-toolbar"><div className="metrics-scope"><span className="scope-dot" /> Demo diamond topology <span className="toolbar-sep">·</span> h1 → h4</div><div className="range-selector"><button>1h</button><button>6h</button><button className="range-active">24h</button><button>7d</button></div></div>
      <div className="metrics-summary-grid">
        <Panel className="metric-summary"><div className="metric-summary-icon summary-blue"><Gauge size={17} /></div><div><span>Average latency</span><strong>2.1 <small>ms</small></strong><em className="good-trend"><ArrowDownRight size={13} /> 14% lower</em></div><div className="metric-spark"><TrendingUp size={21} /></div></Panel>
        <Panel className="metric-summary"><div className="metric-summary-icon summary-violet"><Radio size={17} /></div><div><span>Receiver throughput</span><strong>45.5 <small>Mbps</small></strong><em className="good-trend"><ArrowUpRight size={13} /> 8% higher</em></div><div className="metric-spark"><TrendingUp size={21} /></div></Panel>
        <Panel className="metric-summary"><div className="metric-summary-icon summary-teal"><Activity size={17} /></div><div><span>Packet loss</span><strong>0.02 <small>%</small></strong><em className="good-trend"><ArrowDownRight size={13} /> 0.01% lower</em></div><div className="metric-spark"><TrendingUp size={21} /></div></Panel>
      </div>
      <div className="chart-grid">
        <MetricChart title="Latency over time" description="Average round-trip time · ICMP" data={latencyData} color="var(--accent)" unit="ms" icon={Gauge} />
        <MetricChart title="Bandwidth over time" description="Measured receiver throughput · iperf3" data={bandwidthData} color="var(--periwinkle)" unit="Mbps" icon={Radio} />
        <MetricChart title="Packet loss over time" description="Lost packets as a share of sent packets" data={lossData} color="var(--amber)" unit="%" icon={Activity} domain={[0, 0.1]} />
        <Panel className="chart-panel throughput-chart-panel">
          <div className="chart-heading"><div><div className="chart-title"><span className="chart-icon"><TrendingUp size={15} /></span><h3>Network throughput</h3></div><p>Demo ingress and egress sample series</p></div><button className="chart-menu" aria-label="Throughput chart options">•••</button></div>
          <div className="throughput-legend"><span><i className="throughput-dot blue-dot" /> Ingress</span><span><i className="throughput-dot purple-dot" /> Egress</span><span className="throughput-current">45.5 <small>Mbps</small></span></div>
          <div className="chart-area">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={throughputData} margin={{ top: 10, right: 7, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
                <XAxis dataKey="time" tick={{ fill: "var(--text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={20} />
                <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 5, color: "var(--text)", fontSize: 12, fontFamily: "var(--font-geist-mono)" }} />
                <Line type="monotone" dataKey="inbound" name="Ingress" stroke="var(--accent)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                <Line type="monotone" dataKey="outbound" name="Egress" stroke="var(--periwinkle)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-footer"><span>DEMO MEASUREMENT</span><span>Sample time window · 80 min</span></div>
        </Panel>
      </div>
      <div className="metrics-disclaimer"><Activity size={14} /><span>Sample series are provided to demonstrate dashboard visualizations. Connect a real metrics API before using this page for operational decisions.</span></div>
    </div>
  );
}
