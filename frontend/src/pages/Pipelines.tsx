import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Clock, GitBranch } from "lucide-react";
import { useFetch } from "../hooks";
import type { ETLRun } from "../types";
import { Badge, Card, Empty, PageHeader, Select, Spinner, Stat, StatusBadge } from "../components/ui";
import { timeAgo } from "../format";

export default function Pipelines() {
  const { data, loading } = useFetch<ETLRun[]>("/api/warehouse/runs");
  const [open, setOpen] = useState<number | null>(null);
  const [status, setStatus] = useState("");
  if (loading) return <Spinner />;
  const runs = (data ?? []).filter((r) => !status || r.status === status);
  const all = data ?? [];
  const ok = all.filter((r) => r.status === "success");
  const avg = ok.length ? ok.reduce((s, r) => s + (r.duration_s ?? 0), 0) / ok.length : 0;
  return (
    <div>
      <PageHeader title="ETL Pipelines" subtitle="Every extraction, transformation and load – manual, on upload, or on schedule" icon={<GitBranch className="h-5 w-5" />} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Total runs" value={all.length} />
        <Stat label="Success rate" value={all.length ? `${((ok.length / all.length) * 100).toFixed(1)}%` : "–"} />
        <Stat label="Rows loaded" value={ok.reduce((s, r) => s + r.rows_loaded, 0).toLocaleString()} />
        <Stat label="Avg. duration" value={`${avg.toFixed(2)}s`} icon={<Clock className="h-4 w-4" />} />
      </div>
      <Card title="Run history" actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 text-xs"><option value="">All statuses</option><option value="success">Success</option><option value="failed">Failed</option></Select>}>
        {!runs.length ? <Empty title="No runs" /> : (
          <div className="divide-y divide-[var(--border)]">
            {runs.map((r) => (
              <div key={r.id}>
                <button onClick={() => setOpen(open === r.id ? null : r.id)} className="flex w-full flex-wrap items-center gap-3 py-2.5 text-left text-sm">
                  {open === r.id ? <ChevronDown className="h-4 w-4 text-muted" /> : <ChevronRight className="h-4 w-4 text-muted" />}
                  <StatusBadge status={r.status} />
                  <span className="font-mono text-xs text-muted">#{r.id}</span>
                  <Link to={`/datasets/${r.dataset_id}`} onClick={(e) => e.stopPropagation()} className="font-medium hover:text-accent">{r.dataset_name}</Link>
                  <Badge>{r.trigger}</Badge>
                  <span className="ml-auto tabular text-xs text-muted">{r.rows_extracted.toLocaleString()} → {r.rows_loaded.toLocaleString()} rows · {r.duration_s ?? "–"}s · {timeAgo(r.started_at)}</span>
                </button>
                {open === r.id && (
                  <div className="mb-3 ml-7 space-y-1 rounded-lg bg-surface2 p-3">
                    {r.error && <div className="text-xs text-critical">{r.error}</div>}
                    {(r.steps ?? []).map((s, i) => (
                      <div key={i} className="flex gap-2 text-xs">
                        <span className="w-36 shrink-0 font-mono text-accent">{s.step}</span>
                        <span className="flex-1 text-ink2">{s.description}</span>
                        <span className="tabular text-muted">{s.affected ? s.affected.toLocaleString() : ""}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
