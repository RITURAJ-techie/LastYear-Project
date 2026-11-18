import { useEffect, useRef, useState, type FormEvent } from "react";
import { Bot, Code2, Pin, Send, Sparkles, Table2, User } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dashboard, Dataset, WidgetType } from "../types";
import { Badge, Button, Card, Empty, PageHeader, Select, Spinner } from "../components/ui";
import ChartRenderer, { DataTable } from "../components/charts/ChartRenderer";
import Markdown from "../components/Markdown";

type Answer = { mode: "ai" | "rules"; chart: string; answer: string; explanation: string; spec?: any; result: any };
type Turn = { q: string; a?: Answer; error?: string; datasetId: number };

function AnswerView({ turn, onPin }: { turn: Turn; onPin: (t: Turn) => void }) {
  const [view, setView] = useState<"chart" | "table" | "sql">("chart");
  const a = turn.a!;
  const r = a.result;
  const chart = (["line", "bar", "pie", "kpi", "table", "scatter", "area"].includes(a.chart) ? a.chart : "table") as WidgetType;
  const kpiData = chart === "kpi" ? { value: r.rows?.[0]?.[r.y?.[0]] } : r;
  return (
    <div className="space-y-3">
      <Markdown text={a.answer} />
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={a.mode === "ai" ? "accent" : "neutral"}>{a.mode === "ai" ? "Sarvam AI · text-to-SQL" : "Built-in semantic parser"}</Badge>
        <span>{a.explanation}</span>
      </div>
      <div className="rounded-xl border border-line bg-surface p-3">
        <div className="mb-2 flex gap-1">
          {(["chart", "table", "sql"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} className={"flex items-center gap-1 rounded-md px-2 py-1 text-xs " + (view === v ? "bg-accentsoft text-accent" : "text-muted hover:text-ink")}>
              {v === "chart" ? <Sparkles className="h-3 w-3" /> : v === "table" ? <Table2 className="h-3 w-3" /> : <Code2 className="h-3 w-3" />}{v}
            </button>
          ))}
          {a.spec && <button onClick={() => onPin(turn)} className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:text-ink"><Pin className="h-3 w-3" />Pin to dashboard</button>}
        </div>
        {view === "chart" ? (chart === "kpi" ? <div className="py-2"><ChartRenderer type="kpi" data={kpiData} /></div> : <ChartRenderer type={chart} data={r} height={280} grain={a.spec?.time_grain} />)
          : view === "table" ? <DataTable columns={r.columns ?? Object.keys(r.rows?.[0] ?? {})} rows={r.rows ?? []} maxHeight={300} />
          : <pre className="overflow-x-auto rounded-md bg-surface2 p-3 text-xs text-ink2">{r.sql}</pre>}
      </div>
    </div>
  );
}

export default function Ask() {
  const datasets = useFetch<Dataset[]>("/api/datasets");
  const [dsId, setDsId] = useState<number>(0);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const sugg = useFetch<string[]>(dsId ? `/api/ai/suggestions/${dsId}` : null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ready = (datasets.data ?? []).filter((d) => d.status === "ready");
    if (!dsId && ready.length) setDsId((ready.find((d) => d.source_type === "join") ?? ready[0]).id);
  }, [datasets.data, dsId]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const ask = async (question: string, e?: FormEvent) => {
    e?.preventDefault();
    if (!question.trim() || !dsId) return;
    setQ("");
    setBusy(true);
    const t: Turn = { q: question, datasetId: dsId };
    setTurns((s) => [...s, t]);
    try {
      const r = await api.post("/api/ai/ask", { dataset_id: dsId, question });
      t.a = r.data;
    } catch (err) {
      t.error = errMsg(err);
    }
    setTurns((s) => [...s.slice(0, -1), { ...t }]);
    setBusy(false);
  };

  const pin = async (t: Turn) => {
    const dashes = (await api.get<Dashboard[]>(`/api/dashboards?dataset_id=${t.datasetId}`)).data;
    const type: WidgetType = t.a!.chart === "kpi" ? "kpi" : (t.a!.chart as WidgetType);
    const spec = type === "kpi" ? { column: t.a!.spec.y[0].column, agg: t.a!.spec.y[0].agg, filters: t.a!.spec.filters } : t.a!.spec;
    const widget = { id: Math.random().toString(36).slice(2, 12), type, title: t.q.charAt(0).toUpperCase() + t.q.slice(1), w: type === "kpi" ? 1 : 2, spec };
    try {
      if (dashes.length) await api.patch(`/api/dashboards/${dashes[0].id}`, { widgets: [...dashes[0].widgets, widget] });
      else await api.post("/api/dashboards", { dataset_id: t.datasetId, name: "My questions", auto: false }).then((r) => api.patch(`/api/dashboards/${r.data.id}`, { widgets: [widget] }));
      setNote(`Pinned to "${dashes[0]?.name ?? "My questions"}"`);
    } catch (e) { setNote(errMsg(e)); }
    setTimeout(() => setNote(null), 3000);
  };

  if (datasets.loading) return <Spinner />;
  return (
    <div className="flex h-[calc(100vh-6rem)] flex-col">
      <PageHeader title="Ask Your Data" subtitle="Ask questions in plain English – get answers, charts and the SQL behind them" icon={<Sparkles className="h-5 w-5" />}
        actions={<Select value={dsId} onChange={(e) => { setDsId(Number(e.target.value)); }}>{(datasets.data ?? []).filter((d) => d.status === "ready").map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select>} />
      <div className="flex-1 space-y-5 overflow-y-auto pb-4">
        {turns.length === 0 && (
          <Card>
            <Empty icon={<Bot className="h-8 w-8" />} title="What would you like to know?">
              Try questions like “total revenue by region”, “monthly profit trend”, “top 5 products by quantity”, “average rating per channel in 2024”.
            </Empty>
          </Card>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <div className="flex max-w-[80%] items-start gap-2 rounded-xl bg-accent px-3.5 py-2 text-sm text-white"><span>{t.q}</span><User className="mt-0.5 h-4 w-4 shrink-0 opacity-70" /></div>
            </div>
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-accentsoft p-1.5 text-accent"><Bot className="h-4 w-4" /></div>
              <div className="min-w-0 flex-1">
                {t.a ? <AnswerView turn={t} onPin={pin} /> : t.error ? <div className="text-sm text-critical">{t.error}</div> : <Spinner label="Analysing…" />}
              </div>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      {note && <div className="mb-2 text-center text-xs text-accent">{note}</div>}
      <div className="border-t border-line pt-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {(sugg.data ?? []).map((s) => <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-3 py-1 text-xs text-ink2 hover:border-accent hover:text-accent">{s}</button>)}
        </div>
        <form onSubmit={(e) => ask(q, e)} className="flex gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question about your data…" className="h-11 flex-1 rounded-xl border border-line bg-surface px-4 text-sm outline-none focus:border-accent" />
          <Button variant="primary" className="h-11 px-4" loading={busy} icon={<Send className="h-4 w-4" />} type="submit">Ask</Button>
        </form>
      </div>
    </div>
  );
}
