import { useState } from "react";
import { AlertTriangle, CheckCircle2, Info, Lightbulb, Sparkles, TrendingDown } from "lucide-react";
import { api, errMsg } from "../../api";
import { useFetch } from "../../hooks";
import type { Dataset, Insight } from "../../types";
import { Badge, Button, Card, ErrorBox, Spinner, cx } from "../../components/ui";
import Markdown from "../../components/Markdown";

const SEV = {
  positive: { icon: CheckCircle2, color: "var(--status-good)", label: "Opportunity" },
  negative: { icon: TrendingDown, color: "var(--status-critical)", label: "Risk" },
  warning: { icon: AlertTriangle, color: "var(--status-warning)", label: "Attention" },
  info: { icon: Info, color: "var(--series-1)", label: "Insight" },
} as const;

export default function InsightsTab({ ds }: { ds: Dataset }) {
  const { data, loading, error } = useFetch<{ insights: Insight[]; summary: string; recommendations: any[]; ai_available: boolean }>(`/api/datasets/${ds.id}/analysis/insights`);
  const [filter, setFilter] = useState<string>("all");
  const [ai, setAi] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState<string | null>(null);
  if (loading) return <Spinner label="Running statistical, ML and forecasting analyses…" />;
  if (error || !data) return <ErrorBox>{error}</ErrorBox>;
  const list = data.insights.filter((i) => filter === "all" || i.severity === filter);
  const askAi = async () => {
    setAiBusy(true); setAiErr(null);
    try { setAi((await api.get(`/api/datasets/${ds.id}/analysis/insights?ai=true`)).data.ai_narrative ?? "The AI service returned no narrative."); }
    catch (e) { setAiErr(errMsg(e)); } finally { setAiBusy(false); }
  };
  const counts = data.insights.reduce<Record<string, number>>((a, i) => ({ ...a, [i.severity]: (a[i.severity] ?? 0) + 1 }), {});

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
      <div className="space-y-4">
        <div className="rounded-xl border border-line bg-surface p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><Lightbulb className="h-4 w-4 text-accent" /> Executive summary</div>
          <p className="mt-2 text-sm leading-relaxed text-ink2">{data.summary}</p>
        </div>
        <div className="no-print flex flex-wrap gap-1.5">
          {["all", "negative", "warning", "positive", "info"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={cx("rounded-lg border px-2.5 py-1 text-xs", filter === f ? "border-accent bg-accentsoft text-accent" : "border-line text-ink2 hover:bg-surface2")}>
              {f === "all" ? `All (${data.insights.length})` : `${SEV[f as keyof typeof SEV].label} (${counts[f] ?? 0})`}
            </button>
          ))}
        </div>
        {list.map((i, idx) => {
          const s = SEV[i.severity];
          return (
            <div key={idx} className="rounded-xl border border-line bg-surface p-4" style={{ borderLeft: `3px solid ${s.color}` }}>
              <div className="flex items-start gap-2.5">
                <s.icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color: s.color }} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-sm font-semibold">{i.title}</h4>
                    <Badge>{s.label}</Badge>
                    <Badge>{i.type.replace("_", " ")}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-ink2">{i.description}</p>
                  <div className="mt-2 rounded-lg bg-surface2 px-3 py-2 text-sm"><span className="font-medium">Recommended action: </span><span className="text-ink2">{i.recommendation}</span></div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="space-y-5">
        <Card title="AI executive briefing" subtitle={data.ai_available ? "Sarvam AI writes a narrative from the computed findings (no raw rows are sent)" : "Optional – requires SARVAM_API_KEY on the server"}>
          {ai ? <Markdown text={ai} /> : (
            <>
              <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} onClick={askAi} loading={aiBusy} disabled={!data.ai_available} className="w-full">Generate briefing</Button>
              {!data.ai_available && <p className="mt-2 text-xs text-muted">All insights on this page are produced by the built-in statistical & machine-learning engine and work without any external AI service.</p>}
            </>
          )}
          {aiErr && <div className="mt-2"><ErrorBox>{aiErr}</ErrorBox></div>}
        </Card>
        <Card title="Action plan" subtitle="Top recommendations, highest priority first">
          <ol className="space-y-2.5">
            {data.recommendations.map((r, i) => (
              <li key={i} className="flex gap-2.5 text-sm">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accentsoft text-[11px] font-semibold text-accent">{i + 1}</span>
                <div><div className="font-medium">{r.title}</div><div className="text-xs text-ink2">{r.action}</div></div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
