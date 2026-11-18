import { useState } from "react";
import { useFetch } from "../../hooks";
import type { Dataset } from "../../types";
import { Badge, Card, Select, Spinner } from "../../components/ui";
import ChartRenderer from "../../components/charts/ChartRenderer";
import Heatmap from "../../components/charts/Heatmap";
import { label } from "../../format";

export default function ExploreTab({ ds }: { ds: Dataset }) {
  const p = ds.profile!;
  const dist = useFetch<any[]>(`/api/datasets/${ds.id}/analysis/distributions`);
  const [method, setMethod] = useState("pearson");
  const corr = useFetch<any>(`/api/datasets/${ds.id}/analysis/correlations?method=${method}`);
  const [sx, setSx] = useState(p.measures[0] ?? "");
  const [sy, setSy] = useState(p.measures[1] ?? p.measures[0] ?? "");
  const [sc, setSc] = useState("");
  const scatter = useFetch<any>(sx && sy ? `/api/datasets/${ds.id}/analysis/scatter?x=${sx}&y=${sy}${sc ? `&color=${sc}` : ""}` : null);

  return (
    <div className="space-y-5">
      {p.measures.length >= 2 && (
        <div className="grid gap-5 xl:grid-cols-2">
          <Card title="Correlation matrix" actions={
            <Select value={method} onChange={(e) => setMethod(e.target.value)} className="h-8 text-xs">
              <option value="pearson">Pearson (linear)</option><option value="spearman">Spearman (rank)</option>
            </Select>}>
            {corr.loading || !corr.data ? <Spinner /> : <Heatmap data={corr.data} />}
          </Card>
          <Card title="Strongest relationships" subtitle="Sorted by |r|; significance at p < 0.05">
            {corr.data && (
              <div className="max-h-[360px] space-y-1.5 overflow-y-auto">
                {corr.data.pairs.slice(0, 14).map((pr: any) => (
                  <button key={pr.a + pr.b} onClick={() => { setSx(pr.a); setSy(pr.b); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface2">
                    <span className="flex-1 truncate">{label(pr.a)} <span className="text-muted">×</span> {label(pr.b)}</span>
                    <span className="h-1.5 w-20 overflow-hidden rounded-full bg-surface2">
                      <span className="block h-full rounded-full" style={{ width: `${Math.abs(pr.r) * 100}%`, background: pr.r >= 0 ? "var(--div-pos)" : "var(--div-neg)" }} />
                    </span>
                    <span className="tabular w-12 text-right text-xs">{pr.r.toFixed(2)}</span>
                    <Badge tone={pr.significant ? "neutral" : "warn"}>{pr.strength}</Badge>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
      {p.measures.length >= 2 && (
        <Card title="Scatter explorer" subtitle={scatter.data?.regression ? `Linear fit: slope ${scatter.data.regression.slope?.toFixed(3)}, R² ${scatter.data.regression.r2?.toFixed(3)}` : undefined}
          actions={
            <div className="flex flex-wrap gap-1.5">
              <Select value={sx} onChange={(e) => setSx(e.target.value)} className="h-8 text-xs">{p.measures.map((m) => <option key={m} value={m}>X: {label(m)}</option>)}</Select>
              <Select value={sy} onChange={(e) => setSy(e.target.value)} className="h-8 text-xs">{p.measures.map((m) => <option key={m} value={m}>Y: {label(m)}</option>)}</Select>
              <Select value={sc} onChange={(e) => setSc(e.target.value)} className="h-8 text-xs"><option value="">No color</option>{p.dimensions.map((d) => <option key={d} value={d}>Color: {label(d)}</option>)}</Select>
            </div>}>
          {scatter.data ? <ChartRenderer type="scatter" height={320} data={{ x: sx, y: [sy], color: sc || null, rows: scatter.data.points }} /> : <Spinner />}
        </Card>
      )}
      <div>
        <h3 className="mb-3 text-sm font-semibold">Distributions</h3>
        {dist.loading ? <Spinner /> : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(dist.data ?? []).map((d) => (
              <Card key={d.column} title={label(d.column)} subtitle={d.kind === "histogram" ? `${d.shape} · skew ${d.skew?.toFixed(2)}` : `${d.unique} categories · top share ${d.dominant_share?.toFixed(1)}%`}>
                <ChartRenderer type={d.kind === "histogram" ? "histogram" : "hbar"} height={180}
                  data={{ x: "label", y: ["count"], rows: d.kind === "histogram" ? d.bins : d.bins.slice(0, 8) }} />
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
