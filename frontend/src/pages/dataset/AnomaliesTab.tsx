import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useFetch } from "../../hooks";
import type { Dataset } from "../../types";
import { Card, Empty, Select, Spinner, Stat } from "../../components/ui";
import ChartRenderer from "../../components/charts/ChartRenderer";
import { full, label } from "../../format";

export default function AnomaliesTab({ ds }: { ds: Dataset }) {
  const [c, setC] = useState("0.02");
  const { data, loading } = useFetch<any>(`/api/datasets/${ds.id}/analysis/anomalies?contamination=${c}`);
  if (loading && !data) return <Spinner label="Training Isolation Forest…" />;
  if (!data?.available) return <Empty title="Anomaly detection unavailable">{data?.reason}</Empty>;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Records analysed" value={data.rows_analyzed.toLocaleString()} sub={`${data.features.length} numeric features`} />
        <Stat label="Anomalies found" value={data.anomaly_count.toLocaleString()} sub={`${data.anomaly_rate_pct}% of records`} icon={<AlertTriangle className="h-4 w-4" />} />
        <Stat label="Method" value={<span className="text-base">Isolation Forest</span>} sub="multivariate, unsupervised" />
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="text-xs text-muted">Sensitivity</div>
          <Select value={c} onChange={(e) => setC(e.target.value)} className="mt-2 w-full">
            <option value="0.01">Strict (1%)</option><option value="0.02">Balanced (2%)</option><option value="0.05">Sensitive (5%)</option><option value="0.1">Very sensitive (10%)</option>
          </Select>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <Card title="Most anomalous records" subtitle="Ranked by anomaly score, with the features that make each record unusual">
          <div className="max-h-[560px] space-y-2 overflow-y-auto">
            {data.top.map((a: any, i: number) => (
              <details key={i} className="rounded-lg border border-line px-3 py-2">
                <summary className="flex cursor-pointer list-none items-start gap-3">
                  <span className="tabular mt-0.5 w-12 shrink-0 rounded bg-[color-mix(in_srgb,var(--status-critical)_14%,transparent)] px-1.5 py-0.5 text-center text-[11px] font-medium text-critical">{a.score.toFixed(2)}</span>
                  <div className="text-sm">{a.reasons.map((r: string) => <div key={r}>{r}</div>)}</div>
                </summary>
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(a.record).map(([k, v]) => <span key={k} className="rounded bg-surface2 px-1.5 py-0.5 text-[11px]"><span className="text-muted">{label(k)}</span> {full(v)}</span>)}
                </div>
              </details>
            ))}
          </div>
        </Card>
        <Card title="Extreme values by column" subtitle="Count of values beyond 3σ">
          <ChartRenderer type="hbar" height={240} data={{ x: "column", y: ["extreme_values"], rows: data.by_column.map((b: any) => ({ ...b, column: label(b.column) })) }} />
        </Card>
      </div>
    </div>
  );
}
