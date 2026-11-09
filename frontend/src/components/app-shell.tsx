"use client";

import { useState } from "react";
import {
  Activity,
  Bell,
  ChevronDown,
  CircleHelp,
  Command,
  Cpu,
  Gauge,
  History,
  LayoutDashboard,
  Menu,
  Network,
  Route,
  Settings2,
  ShieldCheck,
  Waypoints,
  X,
} from "lucide-react";
import type { PageId } from "@/types/dashboard";
import { OverviewPage } from "@/components/dashboard/overview-page";
import { TopologyPage } from "@/components/topology/topology-page";
import { IntentPage } from "@/components/intents/intent-page";
import { PlanningPage } from "@/components/planning/planning-page";
import { MetricsPage } from "@/components/metrics/metrics-page";
import { ExecutionsPage } from "@/components/executions/executions-page";
import { SettingsPage } from "@/components/settings/settings-page";
import { useBackendHealth } from "@/hooks/use-backend-health";

const navigation: { id: PageId; label: string; icon: typeof LayoutDashboard; group: string }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, group: "Workspace" },
  { id: "topology", label: "Network topology", icon: Waypoints, group: "Workspace" },
  { id: "intents", label: "Intent management", icon: Command, group: "Workspace" },
  { id: "planning", label: "Path planning", icon: Route, group: "Workspace" },
  { id: "metrics", label: "Network metrics", icon: Activity, group: "Observe" },
  { id: "executions", label: "Execution history", icon: History, group: "Observe" },
  { id: "settings", label: "System configuration", icon: Settings2, group: "System" },
];

const pageTitles: Record<PageId, { title: string; subtitle: string }> = {
  overview: { title: "Network overview", subtitle: "Monitor your intent-driven network at a glance." },
  topology: { title: "Network topology", subtitle: "Explore physical connectivity and inspect network elements." },
  intents: { title: "Intent management", subtitle: "Translate network requirements into structured intent." },
  planning: { title: "Path planning", subtitle: "Evaluate candidates against constraints before optimization." },
  metrics: { title: "Network metrics", subtitle: "Review measurement trends across the demo network." },
  executions: { title: "Execution history", subtitle: "Review intent runs, decisions, and deployment evidence." },
  settings: { title: "System configuration", subtitle: "Configure the integration boundary for your control plane." },
};

function PageContent({ page, navigate }: { page: PageId; navigate: (id: PageId) => void }) {
  switch (page) {
    case "overview": return <OverviewPage navigate={navigate} />;
    case "topology": return <TopologyPage />;
    case "intents": return <IntentPage />;
    case "planning": return <PlanningPage />;
    case "metrics": return <MetricsPage />;
    case "executions": return <ExecutionsPage />;
    case "settings": return <SettingsPage />;
  }
}

export function AppShell() {
  const [activePage, setActivePage] = useState<PageId>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const connection = useBackendHealth();
  const current = pageTitles[activePage];
  const backendLabel = connection.state === "demo"
    ? "Demo mode"
    : connection.state === "checking"
      ? "Checking"
      : connection.state === "connected"
        ? "Connected"
        : "Disconnected";
  const controllerLabel = connection.state === "demo"
    ? "Demo status"
    : connection.state === "checking"
      ? "Checking"
      : connection.state === "connected"
        ? connection.health.ryu_status.toLowerCase()
        : "Unavailable";
  const connectionClass = connection.state === "demo"
    ? "status-demo"
    : connection.state === "connected"
      ? "status-connected"
      : connection.state === "disconnected"
        ? "status-disconnected"
        : "status-checking";

  const navigate = (id: PageId) => {
    setActivePage(id);
    setSidebarOpen(false);
  };

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <div className="brand-mark"><Network size={20} strokeWidth={2.2} /></div>
          <div className="brand-name">IntentFlow <span>SDN</span><small>NETWORK CONTROL PLANE</small></div>
          <button className="icon-button sidebar-close" aria-label="Close menu" onClick={() => setSidebarOpen(false)}><X size={18} /></button>
        </div>
        <div className="workspace-switcher">
          <div className="workspace-avatar"><Cpu size={16} /></div>
          <div><strong>Lab network</strong><small>Demo environment</small></div>
          <ChevronDown size={15} className="muted-icon" />
        </div>
        <nav className="main-nav" aria-label="Main navigation">
          {(["Workspace", "Observe", "System"] as const).map((group) => (
            <div className="nav-group" key={group}>
              <span className="nav-group-label">{group}</span>
              {navigation.filter((item) => item.group === group).map(({ id, label, icon: Icon }) => (
                <button key={id} onClick={() => navigate(id)} className={`nav-item ${activePage === id ? "nav-item-active" : ""}`}>
                  <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
                  {id === "executions" && <span className="nav-count">12</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="controller-card">
            <div className="controller-card-top"><span className="demo-controller-dot" /> Controller <span className="connected-label">{controllerLabel}</span></div>
            <div className="controller-version">Ryu · OpenFlow 1.3</div>
            <div className="controller-address">{connection.state === "connected" ? "REST API · 127.0.0.1:8080" : "sample · 127.0.0.1:6653"}</div>
          </div>
          <button className="help-link"><CircleHelp size={16} /> Documentation <span>↗</span></button>
          <div className="sidebar-user">
            <div className="user-avatar">OP</div>
            <div className="user-name"><strong>Network Operator</strong><small>Administrator</small></div>
            <ChevronDown size={15} className="muted-icon" />
          </div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={19} /></button>
            <div className="breadcrumb"><span>IntentFlow</span><span className="breadcrumb-sep">/</span><strong>{current.title}</strong></div>
          </div>
          <div className="topbar-right">
            <div className={`connection-indicator ${connectionClass}`} title={connection.state === "disconnected" ? connection.error : undefined}><span className="live-dot" /><span>Backend</span><strong>{backendLabel}</strong></div>
            <div className={`controller-indicator ${connectionClass}`}><ShieldCheck size={15} /><span>Ryu</span><strong>{controllerLabel}</strong></div>
            <span className="topbar-divider" />
            <button className="icon-button notification-button" aria-label="Notifications"><Bell size={18} /><i /></button>
            <button className="topbar-profile"><span className="user-avatar user-avatar-small">OP</span><ChevronDown size={14} /></button>
          </div>
        </header>
        <main className="main-content">
          <div className="page-intro">
            <div><div className="eyebrow"><Gauge size={13} /> SDN OPERATIONS</div><h1>{current.title}</h1><p>{current.subtitle}</p></div>
            <div className="page-intro-meta"><span className="environment-badge"><i /> DEMO ENVIRONMENT</span><span className="last-updated">Updated just now</span></div>
          </div>
          <PageContent page={activePage} navigate={navigate} />
          <footer className="page-footer"><span>IntentFlow SDN <span className="footer-dot">·</span> Illustrative sample data</span><span>{connection.state === "demo" ? "Backend integration not configured" : connection.state === "connected" ? "Backend connected · dashboard sample data remains illustrative" : connection.state === "checking" ? "Checking backend connection" : "Backend disconnected · dashboard sample data remains illustrative"}</span></footer>
        </main>
      </div>
    </div>
  );
}
