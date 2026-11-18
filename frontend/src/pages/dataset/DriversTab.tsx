import { useState } from "react";
import { useFetch } from "../../hooks";
import type { Dataset } from "../../types";
import { Badge, Card, Empty, Select, Spinner } from "../../components/ui";
import ChartRenderer from "../../components/charts/ChartRenderer";
import { compact, label } from "../../format";

export default function DriversTab({ ds }: { ds: Dataset }) {
  const p = ds.profile!;
  const [target, setTarget] = useState(p.primary_measure ?? "");
  const drv = useFetch<any>(target ? `/api/datasets/${ds.id}/analysis/drivers?target=${target}` : null);
  const cl = useFetch<any>(`/api/datasets/${ds.id}/analysis/clusters`);
  return (
    <div className="space-y-5">
      <Card title="Key driver analysis" subtitle="Which factors explain the variation in a target metric (Random Forest feature importance)"
        actions={<Select value={target} onChange={(e) => setTarget(e.target.value)} className="h-8 text-xs">{p.measures.map((m) => <option key={m} value={m}>Target: {label(m)}</option>)}</Select>}>
        {!p.measures.length ? <Empty title="No numeric measures" /> : drv.loading ? <Spinner label="Training model…" /> : !drv.data?.available ? <Empty title="Unavailable">{drv.data?.reason}</Empty> : (
          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <ChartRenderer type="hbar" height={260} data={{ x: "feature", y: ["importance"], rows: drv.data.drivers.map((d: any) => ({ feature: label(d.feature.replace(":", " ")), importance: d.importance })) }} />
              <div className="mt-2 text-xs text-muted">Model fit R² = {drv.data.r2_in_sample} on {drv.data.rows_used.toLocaleString()} rows. Importance shown as % of explained variation.</div>
              {drv.data.co_moving?.length > 0 && (
                <div className="mt-2 text-xs text-muted">Excluded as components of {label(target)} (|r| ≥ 0.7): {drv.data.co_moving.map((c: any) => `${label(c.column)} (r=${c.r.toFixed(2)})`).join(", ")}</div>
              )}
            </div>
            <div className="space-y-2">
              {drv.data.drivers.slice(0, 7).map((d: any, i: number) => (
                <div key={d.feature} className="rounded-lg bg-surface2 px-3 py-2">
                  <div className="flex items-center gap-2 text-sm font-medium"><span className="text-muted">#{i + 1}</span>{label(d.feature.replace(":", " "))}<Badge>{d.kind}</Badge><span className="tabular ml-auto text-xs">{d.importance}%</span></div>
                  <div className="mt-0.5 text-xs text-ink2">{d.effect}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
      <Card title="Automatic segmentation" subtitle="K-Means clustering on standardised measures; k chosen by silhouette score">
        {cl.loading ? <Spinner /> : !cl.data?.available ? <Empty title="Segmentation unavailable">{cl.data?.reason}</Empty> : (
          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <ChartRenderer type="scatter" height={300} data={{ x: "x", y: ["y"], color: "segment", rows: cl.data.points.map((pt: any) => ({ x: pt.x, y: pt.y, segment: `Segment ${pt.cluster + 1}` })) }} />
              <div className="text-xs text-muted">2-D projection (principal components) · k = {cl.data.k} · silhouette {cl.data.silhouette}</div>
            </div>
            <div className="space-y-2">
              {cl.data.segments.map((s: any) => (
                <div key={s.cluster} className="rounded-lg border border-line px-3 py-2">
                  <div className="flex items-center justify-between text-sm font-medium"><span>Segment {s.cluster + 1}</span><span className="tabular text-xs text-muted">{s.size.toLocaleString()} records · {s.share_pct}%</span></div>
                  <div className="mt-0.5 text-xs text-ink2">vs average: {s.profile}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(s.means).slice(0, 6).map(([k, v]) => <span key={k} className="rounded bg-surface2 px-1.5 py-0.5 text-[11px]"><span className="text-muted">{label(k)}</span> {compact(v)}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
