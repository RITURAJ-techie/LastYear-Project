import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, CheckCircle2, Info, LayoutDashboard, Lightbulb, Link2, ShieldCheck, Sparkles, Table2, TrendingDown, UploadCloud, Wrench } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dataset, Insight } from "../types";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, SourceIcon, Spinner, Stat, cx } from "../components/ui";
import Markdown from "../components/Markdown";
import { compact } from "../format";

type TaggedInsight = Insight & { dataset_id: number; dataset_name: string; also_in?: string[] };
type DatasetSummary = {
  id: number; name: string; source_type: string; row_count: number; column_count: number;
  quality_before: number | null; quality_after: number | null; issues_fixed: number; summary: string;
  insight_count: number; severity_counts: Record<string, number>; top_insights: Insight[]; error: string | null;
};
type Combined = {
  totals: { datasets: number; rows: number; issues_fixed: number; insights: number; risks: number; warnings: number; opportunities: number; info: number };
  datasets: DatasetSummary[];
  top_insights: TaggedInsight[];
  action_plan: { title: string; action: string; severity: string; dataset_name: string }[];
  relationships: { from_dataset: string; from_column: string; to_dataset: string; to_column: string; cardinality: string; confidence: number }[];
  ai_available: boolean;
  ai_narrative?: string | null;
};

const SEV = {
  positive: { icon: CheckCircle2, color: "var(--status-good)", label: "Opportunity" },
  negative: { icon: TrendingDown, color: "var(--status-critical)", label: "Risk" },
  warning: { icon: AlertTriangle, color: "var(--status-warning)", label: "Attention" },
  info: { icon: Info, color: "var(--series-1)", label: "Insight" },
} as const;

export default function InsightsHub() {
  const [params, setParams] = useSearchParams();
  const all = useFetch<Dataset[]>("/api/datasets");
  const ready = (all.data ?? []).filter((d) => d.status === "ready");
  const urlIds = (params.get("ids") ?? "").split(",").map(Number).filter(Boolean);
  const [selected, setSelected] = useState<number[]>(urlIds);
  const [data, setData] = useState<Combined | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [dashBusy, setDashBusy] = useState(false);
  const nav = useNavigate();
  const openDashboard = async () => {
    setDashBusy(true);
    try { nav(`/dashboards/${(await api.post("/api/dashboards/combined", { dataset_ids: selected })).data.id}`); }
    catch (e) { setError(errMsg(e)); setDashBusy(false); }
  };

  // default selection: everything ready (when the URL names nothing)
  useEffect(() => {
    if (!selected.length && ready.length) setSelected(ready.map((d) => d.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all.data]);

  const key = [...selected].sort((a, b) => a - b).join(",");
  useEffect(() => {
    if (!key) return;
    let alive = true;
    setLoading(true);
    setError(null);
    setAi(null);
    api.get(`/api/insights/combined?ids=${key}`)
      .then((r) => alive && setData(r.data))
      .catch((e) => alive && setError(errMsg(e)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [key]);

  const toggle = (id: number) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    setSelected(next);
    setParams(next.length ? { ids: next.join(",") } : {}, { replace: true });
  };
  const briefing = async () => {
    setAiBusy(true);
    try { setAi((await api.get(`/api/insights/combined?ids=${key}&ai=true`)).data.ai_narrative ?? "The AI service returned no narrative."); }
    catch (e) { setAi(`**Could not generate briefing:** ${errMsg(e)}`); }
    finally { setAiBusy(false); }
  };

  if (all.loading) return <Spinner />;
  if (!ready.length) {
    return (
      <div>
        <PageHeader title="Insights Hub" icon={<Lightbulb className="h-5 w-5" />} />
        <Empty icon={<UploadCloud className="h-8 w-8" />} title="No datasets yet">
          <Link to="/sources" className="text-accent">Upload one or more files</Link> to see combined insights here.
        </Empty>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Insights Hub" subtitle="Ranked insights and recommended actions across several datasets at once" icon={<Lightbulb className="h-5 w-5" />}
        actions={<>
          <Link to="/sources"><Button icon={<UploadCloud className="h-4 w-4" />}>Upload more files</Button></Link>
          <Button variant="primary" icon={<LayoutDashboard className="h-4 w-4" />} loading={dashBusy} disabled={!selected.length} onClick={openDashboard}>
            {selected.length > 1 ? "Build combined dashboard" : "Build dashboard"}
          </Button>
        </>} />

      <div className="no-print mb-5 rounded-xl border border-line bg-surface p-3">
        <div className="mb-2 flex items-center justify-between text-xs text-muted">
          <span>Datasets included ({selected.length} of {ready.length})</span>
          <span className="flex gap-2">
            <button className="text-accent" onClick={() => { setSelected(ready.map((d) => d.id)); setParams({}, { replace: true }); }}>Select all</button>
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ready.map((d) => (
            <button key={d.id} onClick={() => toggle(d.id)}
              className={cx("rounded-full border px-3 py-1 text-xs transition", selected.includes(d.id) ? "border-accent bg-accentsoft font-medium text-accent" : "border-line text-ink2 hover:bg-surface2")}>
              {d.name}
            </button>
          ))}
        </div>
      </div>

      {!selected.length ? <Empty title="Select at least one dataset" /> : error ? <ErrorBox>{error}</ErrorBox> : !data || (loading && !data) ? (
        <Spinner label={`Analysing ${selected.length} dataset${selected.length > 1 ? "s" : ""} – statistics, forecasts, anomalies and drivers…`} />
      ) : (
        <div className={cx("space-y-5 transition", loading && "opacity-60")}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Datasets" value={data.totals.datasets} sub={`${data.relationships.length} links found`} icon={<Table2 className="h-4 w-4" />} />
            <Stat label="Rows analysed" value={compact(data.totals.rows)} />
            <Stat label="Issues auto-fixed" value={compact(data.totals.issues_fixed)} icon={<Wrench className="h-4 w-4" />} />
            <Stat label="Risks" value={data.totals.risks} sub="declines & negative trends" icon={<TrendingDown className="h-4 w-4 text-critical" />} />
            <Stat label="Needs attention" value={data.totals.warnings} sub="anomalies, concentration" icon={<AlertTriangle className="h-4 w-4" style={{ color: "var(--status-warning)" }} />} />
            <Stat label="Opportunities" value={data.totals.opportunities} sub="growth & strengths" icon={<CheckCircle2 className="h-4 w-4 text-good" />} />
          </div>

          <div className="grid gap-5 xl:grid-cols-[1fr_380px]">
            <Card title="Top insights across all datasets" subtitle="Highest-priority findings first (at most 4 per dataset)">
              <div className="space-y-3">
                {data.top_insights.map((i, idx) => {
                  const s = SEV[i.severity];
                  return (
                    <div key={idx} className="rounded-lg border border-line p-3" style={{ borderLeft: `3px solid ${s.color}` }}>
                      <div className="flex items-start gap-2.5">
                        <s.icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color: s.color }} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold">{i.title}</span>
                            <Badge>{s.label}</Badge>
                            <Link to={`/datasets/${i.dataset_id}`}><Badge tone="accent">{i.dataset_name}</Badge></Link>
                            {i.also_in?.map((n) => <Badge key={n} tone="accent">{n}</Badge>)}
                          </div>
                          <p className="mt-1 text-sm text-ink2">{i.description}</p>
                          <p className="mt-1.5 text-sm"><span className="font-medium">Action: </span><span className="text-ink2">{i.recommendation}</span></p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
            <div className="space-y-5">
              <Card title="AI briefing across datasets" subtitle={data.ai_available ? "Sarvam AI connects the findings into one narrative" : "Optional – requires SARVAM_API_KEY on the server"}>
                {ai ? <Markdown text={ai} /> : (
                  <Button variant="primary" className="w-full" icon={<Sparkles className="h-4 w-4" />} loading={aiBusy} disabled={!data.ai_available} onClick={briefing}>Generate combined briefing</Button>
                )}
              </Card>
              <Card title="Action plan">
                <ol className="space-y-2.5">
                  {data.action_plan.map((a, i) => (
                    <li key={i} className="flex gap-2.5 text-sm">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accentsoft text-[11px] font-semibold text-accent">{i + 1}</span>
                      <div><div className="font-medium">{a.title} <span className="text-xs font-normal text-muted">· {a.dataset_name}</span></div><div className="text-xs text-ink2">{a.action}</div></div>
                    </li>
                  ))}
                </ol>
              </Card>
              {data.relationships.length > 0 && (
                <Card title="How the datasets connect" subtitle="Shared keys discovered automatically">
                  <div className="space-y-1.5">
                    {data.relationships.map((r, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-xs text-ink2">
                        <Link2 className="h-3.5 w-3.5 shrink-0 text-muted" />
                        <span className="truncate">{r.from_dataset}<span className="font-mono text-muted">.{r.from_column}</span> → {r.to_dataset}<span className="font-mono text-muted">.{r.to_column}</span></span>
                        <span className="ml-auto shrink-0 text-muted">{Math.round(r.confidence * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </div>
          </div>

          <div>
            <h3 className="mb-3 text-sm font-semibold">Per-dataset summary</h3>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {data.datasets.map((d) => (
                <div key={d.id} className="flex flex-col rounded-xl border border-line bg-surface p-4">
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/datasets/${d.id}`} className="font-semibold hover:text-accent">{d.name}</Link>
                    <SourceIcon type={d.source_type} />
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5 text-xs">
                    <Badge>{d.row_count.toLocaleString()} rows</Badge>
                    <Badge tone="good"><ShieldCheck className="h-3 w-3" />{d.quality_before} → {d.quality_after}</Badge>
                    {d.issues_fixed > 0 && <Badge><Wrench className="h-3 w-3" />{d.issues_fixed} fixed</Badge>}
                    {(d.severity_counts.negative ?? 0) > 0 && <Badge tone="bad">{d.severity_counts.negative} risk</Badge>}
                    {(d.severity_counts.positive ?? 0) > 0 && <Badge tone="good">{d.severity_counts.positive} opportunity</Badge>}
                  </div>
                  {d.error ? <div className="mt-2 text-xs text-critical">{d.error}</div> : (
                    <ul className="mt-3 flex-1 space-y-1.5">
                      {d.top_insights.slice(0, 3).map((i, k) => {
                        const s = SEV[i.severity];
                        return <li key={k} className="flex gap-1.5 text-xs text-ink2"><s.icon className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: s.color }} />{i.title}</li>;
                      })}
                    </ul>
                  )}
                  <Link to={`/datasets/${d.id}`} className="mt-3 inline-flex items-center gap-1 text-xs text-accent">All {d.insight_count} insights <ArrowRight className="h-3 w-3" /></Link>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
