import { Link } from "react-router-dom";
import { ArrowRight, BarChart3, CheckCircle2, Database, FileSpreadsheet, GitBranch, Globe, LayoutDashboard, ShieldCheck, Sparkles, Table2, UploadCloud, Warehouse, Wrench } from "lucide-react";
import { useFetch } from "../hooks";
import { useAuth } from "../auth";
import type { Dataset, ETLRun } from "../types";
import { Badge, Card, Empty, PageHeader, SourceIcon, Spinner, Stat, StatusBadge } from "../components/ui";
import { compact, timeAgo } from "../format";

type Overview = {
  datasets: number; dashboards: number; total_rows: number; total_columns: number; avg_quality: number | null; avg_quality_before: number | null;
  etl_runs: number; etl_success_rate: number | null; issues_fixed: number; by_source: Record<string, number>;
  recent_runs: ETLRun[]; scheduled: number;
};

function Flow() {
  const steps = [
    { icon: FileSpreadsheet, t: "Sources", d: "Files · SQL · APIs" },
    { icon: Wrench, t: "ETL", d: "Clean · type · validate" },
    { icon: Warehouse, t: "Warehouse", d: "Staging · core · marts" },
    { icon: Sparkles, t: "Analytics", d: "Stats · ML · forecasts" },
    { icon: LayoutDashboard, t: "Decisions", d: "Dashboards · insights" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.t} className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-line bg-surface2 px-3 py-2">
            <s.icon className="h-4 w-4 text-accent" />
            <div>
              <div className="text-xs font-medium">{s.t}</div>
              <div className="text-[11px] text-muted">{s.d}</div>
            </div>
          </div>
          {i < steps.length - 1 && <ArrowRight className="h-4 w-4 text-muted" />}
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const { user } = useAuth();
  const ov = useFetch<Overview>("/api/warehouse/overview");
  const ds = useFetch<Dataset[]>("/api/datasets");
  if (ov.loading || ds.loading) return <Spinner />;
  const o = ov.data;
  const datasets = ds.data ?? [];
  const srcIcon: Record<string, any> = { file: FileSpreadsheet, sql: Database, api: Globe, join: GitBranch };

  return (
    <div>
      <PageHeader title={`Hello, ${user?.name?.split(" ")[0] ?? "there"}`} subtitle="Your data platform at a glance"
        actions={<Link to="/sources" className="inline-flex h-9 items-center gap-2 rounded-lg bg-accent px-3.5 text-sm font-medium text-white hover:opacity-90"><UploadCloud className="h-4 w-4" /> Add data</Link>} />

      <Card className="mb-5"><Flow /></Card>

      {o && (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Stat label="Datasets" value={o.datasets} sub={Object.entries(o.by_source).map(([k, v]) => `${v} ${k}`).join(" · ") || "none yet"} icon={<Table2 className="h-4 w-4" />} />
          <Stat label="Rows in warehouse" value={compact(o.total_rows)} sub={`${o.total_columns} columns`} icon={<Warehouse className="h-4 w-4" />} />
          <Stat label="Avg. data quality" value={o.avg_quality !== null ? `${o.avg_quality_before} → ${o.avg_quality}` : "–"} sub="raw → after ETL (of 100)" icon={<ShieldCheck className="h-4 w-4" />} />
          <Stat label="Issues auto-fixed" value={compact(o.issues_fixed)} sub="duplicates, formats, gaps" icon={<Wrench className="h-4 w-4" />} />
          <Stat label="ETL success rate" value={o.etl_success_rate !== null ? `${o.etl_success_rate}%` : "–"} sub={`${o.etl_runs} runs · ${o.scheduled} scheduled`} icon={<CheckCircle2 className="h-4 w-4" />} />
          <Stat label="Dashboards" value={o.dashboards} sub="auto + custom" icon={<BarChart3 className="h-4 w-4" />} />
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Datasets" actions={<Link to="/datasets" className="text-xs text-accent">View all</Link>}>
          {datasets.length === 0 ? (
            <Empty icon={<UploadCloud className="h-8 w-8" />} title="No data yet">Upload a CSV/Excel file or connect a database to get started. Dashboards and insights are generated automatically.</Empty>
          ) : (
            <div className="divide-y divide-[var(--border)]">
              {datasets.slice(0, 7).map((d) => {
                const Icon = srcIcon[d.source_type] ?? Table2;
                return (
                  <Link key={d.id} to={`/datasets/${d.id}`} className="flex items-center gap-3 py-2.5 hover:opacity-80">
                    <div className="rounded-lg bg-surface2 p-2 text-ink2"><Icon className="h-4 w-4" /></div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{d.name}</div>
                      <div className="truncate text-xs text-muted">{d.row_count.toLocaleString()} rows · {d.column_count} columns · refreshed {timeAgo(d.last_refreshed)}</div>
                    </div>
                    <SourceIcon type={d.source_type} />
                    {d.quality_score !== null && <Badge tone="good">Q {d.quality_before} → {d.quality_score}</Badge>}
                  </Link>
                );
              })}
            </div>
          )}
        </Card>
        <Card title="Recent ETL activity" actions={<Link to="/pipelines" className="text-xs text-accent">All runs</Link>}>
          {!o?.recent_runs.length ? <Empty title="No pipeline runs yet" /> : (
            <div className="space-y-2.5">
              {o.recent_runs.map((r) => (
                <div key={r.id} className="flex items-center gap-2 text-sm">
                  <StatusBadge status={r.status} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium">{r.dataset_name}</div>
                    <div className="text-[11px] text-muted">{r.trigger} · {r.rows_loaded.toLocaleString()} rows · {r.duration_s ?? "–"}s</div>
                  </div>
                  <span className="text-[11px] text-muted">{timeAgo(r.started_at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {[
          { to: "/dashboards", icon: LayoutDashboard, t: "Explore dashboards", d: "Interactive KPIs, trends & filters" },
          { to: "/ask", icon: Sparkles, t: "Ask a question", d: "Natural-language answers with charts" },
          { to: "/warehouse", icon: Warehouse, t: "Model the warehouse", d: "Relationships, joins & SQL" },
        ].map((q) => (
          <Link key={q.to} to={q.to} className="group flex items-center gap-3 rounded-xl border border-line bg-surface p-4 hover:border-accent">
            <q.icon className="h-5 w-5 text-accent" />
            <div className="flex-1">
              <div className="text-sm font-medium">{q.t}</div>
              <div className="text-xs text-muted">{q.d}</div>
            </div>
            <ArrowRight className="h-4 w-4 text-muted transition group-hover:translate-x-0.5" />
          </Link>
        ))}
      </div>
    </div>
  );
}
