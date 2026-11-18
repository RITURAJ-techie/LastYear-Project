import { useState } from "react";
import { CheckCircle2, Circle, XCircle } from "lucide-react";
import { api, errMsg } from "../../api";
import { useFetch } from "../../hooks";
import type { Dataset, ETLRun } from "../../types";
import { Badge, Button, Card, ErrorBox, Select, Spinner, StatusBadge, cx } from "../../components/ui";
import { label, timeAgo } from "../../format";

const ISSUE_LABEL: Record<string, string> = {
  duplicates_removed: "Duplicate rows removed", inconsistent_values: "Inconsistent labels unified", format_fixes: "Values re-formatted (currency, dates…)",
  null_tokens: "Null placeholders normalised", invalid_values: "Unparseable values set to missing", imputed_values: "Missing values imputed",
  empty_rows_removed: "Empty rows removed", columns_dropped: "Near-empty columns dropped", outliers_detected: "Extreme outliers flagged",
};

function Details({ d }: { d: unknown }) {
  if (d === null || d === undefined) return null;
  if (typeof d === "string") return <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-surface2 p-2 text-[11px] text-ink2">{d}</pre>;
  if (Array.isArray(d)) return d.length ? <div className="mt-1 text-[11px] text-muted">{d.join(", ")}</div> : null;
  if (typeof d === "object") {
    const e = Object.entries(d as Record<string, unknown>);
    if (!e.length) return null;
    return (
      <div className="mt-1 flex flex-wrap gap-1">
        {e.slice(0, 14).map(([k, v]) => <span key={k} className="rounded bg-surface2 px-1.5 py-0.5 text-[11px] text-ink2"><span className="text-muted">{k}</span> {Array.isArray(v) ? v.join(", ") : String(v)}</span>)}
        {e.length > 14 && <span className="text-[11px] text-muted">+{e.length - 14} more</span>}
      </div>
    );
  }
  return null;
}

export default function QualityTab({ ds, onChange }: { ds: Dataset; onChange: () => void }) {
  const q = ds.quality!;
  const runs = useFetch<ETLRun[]>(`/api/datasets/${ds.id}/runs`, [ds.last_refreshed]);
  const [interval, setIntervalV] = useState(ds.refresh_interval_minutes);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const run = runs.data?.find((r) => r.id === sel) ?? runs.data?.[0];

  const dimData = {
    x: "dimension", y: ["before", "after"],
    rows: Object.keys(q.dimensions_before).map((k) => ({ dimension: label(k), before: q.dimensions_before[k], after: q.dimensions_after[k] })),
  };
  const save = async () => {
    setBusy(true); setErr(null);
    try { await api.patch(`/api/datasets/${ds.id}`, { refresh_interval_minutes: interval }); onChange(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Data quality score" subtitle="Weighted: completeness 35%, uniqueness 25%, validity 25%, consistency 15%">
          <div className="flex items-end gap-6">
            <div><div className="text-xs text-muted">Raw source</div><div className="text-3xl font-semibold text-ink2">{q.score_before}</div></div>
            <div className="pb-1 text-muted">→</div>
            <div><div className="text-xs text-muted">After ETL</div><div className="text-4xl font-semibold">{q.score_after}</div></div>
            <Badge tone={q.grade === "A" ? "good" : "warn"}>Grade {q.grade}</Badge>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-surface2 p-2"><div className="text-muted">Rows</div><div className="tabular font-medium">{q.raw_rows.toLocaleString()} → {q.clean_rows.toLocaleString()}</div></div>
            <div className="rounded-lg bg-surface2 p-2"><div className="text-muted">Missing cells</div><div className="tabular font-medium">{q.raw_missing_cells.toLocaleString()} → {q.clean_missing_cells.toLocaleString()}</div></div>
          </div>
        </Card>
        <Card title="Quality dimensions" subtitle="Before vs after cleaning (0–100)">
          <div className="space-y-3">
            {dimData.rows.map((r) => (
              <div key={r.dimension}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="text-ink2">{r.dimension}</span>
                  <span className="tabular text-xs"><span className="text-muted">{r.before}%</span> → <b>{r.after}%</b></span>
                </div>
                <div className="relative mt-1 h-1.5 rounded-full bg-surface2">
                  <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--series-1)]" style={{ width: `${r.after}%` }} />
                  <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--axis)]" style={{ width: `${r.before}%`, opacity: r.before < r.after ? 1 : 0 }} />
                </div>
                {r.before < r.after && <div className="mt-0.5 text-[11px] text-muted">{(r.after - r.before).toFixed(1)} pts improved</div>}
              </div>
            ))}
          </div>
        </Card>
        <Card title="Issues fixed automatically">
          <div className="space-y-1.5">
            {Object.entries(q.issues).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between text-sm">
                <span className="text-ink2">{ISSUE_LABEL[k] ?? label(k)}</span>
                <span className="tabular font-medium">{v.toLocaleString()}</span>
              </div>
            ))}
            {!Object.values(q.issues).some((v) => v > 0) && <div className="text-sm text-muted">No issues found – source data was clean.</div>}
          </div>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <Card title="ETL pipeline log" subtitle={run ? `Run #${run.id} · ${run.trigger} · ${timeAgo(run.started_at)} · ${run.duration_s ?? "–"}s` : undefined}>
          {runs.loading ? <Spinner /> : !run ? <div className="text-sm text-muted">No runs</div> : (
            <ol className="relative space-y-3 border-l border-line pl-5">
              {(run.steps ?? []).map((s, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[27px] top-0.5 rounded-full bg-surface">
                    {s.step === "error" ? <XCircle className="h-4 w-4 text-critical" /> : s.affected > 0 ? <CheckCircle2 className="h-4 w-4 text-good" /> : <Circle className="h-4 w-4 text-muted" />}
                  </span>
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-mono text-xs text-accent">{s.step}</span>
                    <span className="text-sm">{s.description}</span>
                    {s.affected > 0 && <Badge>{s.affected.toLocaleString()}</Badge>}
                  </div>
                  <Details d={s.details} />
                </li>
              ))}
            </ol>
          )}
        </Card>
        <div className="space-y-5">
          <Card title="Refresh schedule" subtitle="The scheduler re-runs the full ETL automatically">
            <div className="flex gap-2">
              <Select value={interval} onChange={(e) => setIntervalV(Number(e.target.value))} className="flex-1">
                <option value={0}>Manual only</option><option value={15}>Every 15 minutes</option><option value={60}>Every hour</option>
                <option value={360}>Every 6 hours</option><option value={1440}>Daily</option><option value={10080}>Weekly</option>
              </Select>
              <Button onClick={save} loading={busy} disabled={interval === ds.refresh_interval_minutes}>Save</Button>
            </div>
            {err && <div className="mt-2"><ErrorBox>{err}</ErrorBox></div>}
          </Card>
          <Card title="Run history">
            <div className="max-h-80 space-y-1 overflow-y-auto">
              {(runs.data ?? []).map((r) => (
                <button key={r.id} onClick={() => setSel(r.id)} className={cx("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-surface2", run?.id === r.id && "bg-surface2")}>
                  <StatusBadge status={r.status} />
                  <span className="flex-1">#{r.id} · {r.trigger}</span>
                  <span className="tabular text-muted">{r.rows_loaded.toLocaleString()} rows</span>
                  <span className="text-muted">{timeAgo(r.started_at)}</span>
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
