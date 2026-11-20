import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Database, GitBranch, Home, LayoutDashboard, Lightbulb, LogOut, Menu, Monitor, Moon, Sparkles, Sun, Table2, UploadCloud, Warehouse } from "lucide-react";
import { useAuth } from "../auth";
import { useTheme } from "../theme";
import { api } from "../api";
import { cx } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: Home, end: true },
  { to: "/sources", label: "Data Sources", icon: UploadCloud },
  { to: "/datasets", label: "Datasets", icon: Table2 },
  { to: "/dashboards", label: "Dashboards", icon: LayoutDashboard },
  { to: "/insights", label: "Insights Hub", icon: Lightbulb },
  { to: "/ask", label: "Ask Your Data", icon: Sparkles },
  { to: "/warehouse", label: "Data Warehouse", icon: Warehouse },
  { to: "/pipelines", label: "ETL Pipelines", icon: GitBranch },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [ai, setAi] = useState<{ generative_ai: boolean; model: string | null } | null>(null);
  const loc = useLocation();
  useEffect(() => {
    setOpen(false);
  }, [loc.pathname]);
  useEffect(() => {
    api.get("/api/ai/status").then((r) => setAi(r.data)).catch(() => undefined);
  }, []);
  const nextTheme = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;

  return (
    <div className="flex min-h-full">
      <aside className={cx("no-print fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-line bg-surface transition-transform lg:translate-x-0", open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center gap-2.5 px-5 py-5">
          <img src="/logo.svg" className="h-8 w-8" alt="" />
          <div>
            <div className="text-[15px] font-semibold leading-tight">InsightFlow AI</div>
            <div className="text-[11px] text-muted">Analytics & decision support</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => cx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition", isActive ? "bg-accentsoft font-medium text-accent" : "text-ink2 hover:bg-surface2 hover:text-ink")}>
              <n.icon className="h-4 w-4" /> {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mx-3 mb-3 rounded-lg border border-line p-3 text-xs">
          <div className="flex items-center gap-1.5 font-medium text-ink"><Database className="h-3.5 w-3.5" /> Analytics engines</div>
          <div className="mt-1 text-muted">Statistics · ML · NLP{ai?.generative_ai ? " · Sarvam AI" : ""}</div>
          {ai && !ai.generative_ai && <div className="mt-1 text-[11px] text-muted">Set SARVAM_API_KEY to add Sarvam AI narratives.</div>}
        </div>
        <div className="flex items-center gap-2 border-t border-line px-4 py-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accentsoft text-xs font-semibold text-accent">{user?.name?.[0]?.toUpperCase()}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{user?.name}</div>
            <div className="truncate text-[11px] text-muted">{user?.email}</div>
          </div>
          <button onClick={() => setTheme(nextTheme)} className="rounded p-1.5 text-muted hover:bg-surface2 hover:text-ink" title={`Theme: ${theme}`}><ThemeIcon className="h-4 w-4" /></button>
          <button onClick={logout} className="rounded p-1.5 text-muted hover:bg-surface2 hover:text-ink" title="Sign out"><LogOut className="h-4 w-4" /></button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
        <header className="no-print sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface px-4 py-2.5 lg:hidden">
          <button onClick={() => setOpen(true)} className="rounded p-1 text-ink2" aria-label="Open menu"><Menu className="h-5 w-5" /></button>
          <img src="/logo.svg" className="h-6 w-6" alt="" />
          <span className="font-semibold">InsightFlow AI</span>
        </header>
        <main className="print-full mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
