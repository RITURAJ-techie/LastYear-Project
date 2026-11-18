import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Boxes, Code2, GitMerge, Link2, Play, Plus, Trash2, Warehouse as WarehouseIcon } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dataset } from "../types";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, Tabs, cx } from "../components/ui";
import { DataTable } from "../components/charts/ChartRenderer";
import { label } from "../format";

type Obj = { name: string; kind: string; layer: string; rows: number | null; columns: number | null; dataset?: string; columns_detail: { name: string; type: string }[]; sql?: string };
type Rel = { from_dataset_id: number; from_dataset: string; from_column: string; to_dataset_id: number; to_dataset: string; to_column: string; cardinality: string; containment_pct: number; confidence: number; matched_values: number; orphan_values: number };

const LAYERS = [
  { id: "staging", name: "Staging", desc: "Raw extracted data, as-is", color: "var(--series-4)" },
  { id: "core", name: "Core (dw_)", desc: "Cleaned, typed, conformed", color: "var(--series-1)" },
  { id: "dimension", name: "Dimensions", desc: "Shared conformed dims", color: "var(--series-3)" },
  { id: "mart", name: "Marts", desc: "Pre-aggregated views", color: "var(--series-7)" },
];

function ERDiagram({ rels, datasets }: { rels: Rel[]; datasets: Dataset[] }) {
  const ids = Array.from(new Set(rels.flatMap((r) => [r.from_dataset_id, r.to_dataset_id])));
  if (!ids.length) return null;
  const W = 760, boxW = 170, boxH = 44;
  const facts = ids.filter((id) => rels.some((r) => r.from_dataset_id === id));
  const dims = ids.filter((id) => !facts.includes(id));
  const pos: Record<number, { x: number; y: number }> = {};
  const place = (list: number[], y: number) => list.forEach((id, i) => (pos[id] = { x: ((i + 0.5) * W) / list.length - boxW / 2, y }));
  place(facts, 20);
  place(dims, 160);
  const name = (id: number) => datasets.find((d) => d.id === id)?.name ?? `#${id}`;
  return (
    <svg viewBox={`0 0 ${W} 220`} className="w-full" role="img" aria-label="Relationship diagram">
      {rels.map((r, i) => {
        const a = pos[r.from_dataset_id], b = pos[r.to_dataset_id];
        if (!a || !b) return null;
        const x1 = a.x + boxW / 2, y1 = a.y + boxH, x2 = b.x + boxW / 2, y2 = b.y;
        return (
          <g key={i}>
            <path d={`M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2}`} fill="none" stroke="var(--axis)" strokeWidth={1.5} />
            <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 + 3} textAnchor="middle" fontSize={10} fill="var(--text-secondary)" stroke="var(--surface-1)" strokeWidth={4} paintOrder="stroke">{r.from_column} → {r.to_column}</text>
          </g>
        );
      })}
      {ids.map((id) => (
        <g key={id} transform={`translate(${pos[id].x},${pos[id].y})`}>
          <rect width={boxW} height={boxH} rx={8} fill="var(--surface-2)" stroke={facts.includes(id) ? "var(--series-1)" : "var(--series-3)"} strokeWidth={1.5} />
          <text x={boxW / 2} y={19} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--text-primary)">{name(id).slice(0, 22)}</text>
          <text x={boxW / 2} y={34} textAnchor="middle" fontSize={10} fill="var(--text-muted)">{facts.includes(id) ? "fact" : "dimension"}</text>
        </g>
      ))}
    </svg>
  );
}

function JoinBuilder({ open, onClose, datasets, preset }: { open: boolean; onClose: () => void; datasets: Dataset[]; preset: Rel[] }) {
  const nav = useNavigate();
  const ready = datasets.filter((d) => d.status === "ready" && d.profile);
  const [base, setBase] = useState<number>(preset[0]?.from_dataset_id ?? ready[0]?.id ?? 0);
  const [joins, setJoins] = useState<{ dataset_id: number; left_column: string; right_column: string; how: string }[]>(
    preset.filter((r) => r.from_dataset_id === (preset[0]?.from_dataset_id)).map((r) => ({ dataset_id: r.to_dataset_id, left_column: r.from_column, right_column: r.to_column, how: "left" })),
  );
  const [name, setName] = useState("Integrated dataset");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const cols = (id: number) => datasets.find((d) => d.id === id)?.profile?.columns.map((c) => c.name) ?? [];
  const submit = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.post("/api/warehouse/join", { name, base_dataset_id: base, joins }); nav(`/datasets/${r.data.dataset.id}`); }
    catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Build an integrated dataset" wide>
      <div className="space-y-4">
        <p className="text-sm text-muted">Join a fact dataset with related datasets inside the warehouse. The result is a new, refreshable dataset with its own dashboard and insights.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="New dataset name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Base (fact) dataset"><Select value={base} onChange={(e) => { setBase(Number(e.target.value)); setJoins([]); }} className="w-full">{ready.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select></Field>
        </div>
        {joins.map((j, i) => (
          <div key={i} className="grid items-end gap-2 rounded-lg border border-line p-3 sm:grid-cols-[1fr_1fr_1fr_100px_auto]">
            <Field label="Join dataset"><Select value={j.dataset_id} onChange={(e) => setJoins(joins.map((x, k) => (k === i ? { ...x, dataset_id: Number(e.target.value), right_column: cols(Number(e.target.value))[0] } : x)))} className="w-full">{ready.filter((d) => d.id !== base).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select></Field>
            <Field label="Base column"><Select value={j.left_column} onChange={(e) => setJoins(joins.map((x, k) => (k === i ? { ...x, left_column: e.target.value } : x)))} className="w-full">{cols(base).map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label="Matches column"><Select value={j.right_column} onChange={(e) => setJoins(joins.map((x, k) => (k === i ? { ...x, right_column: e.target.value } : x)))} className="w-full">{cols(j.dataset_id).map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label="Type"><Select value={j.how} onChange={(e) => setJoins(joins.map((x, k) => (k === i ? { ...x, how: e.target.value } : x)))} className="w-full"><option value="left">Left</option><option value="inner">Inner</option></Select></Field>
            <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} onClick={() => setJoins(joins.filter((_, k) => k !== i))} />
          </div>
        ))}
        <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => {
          const other = ready.find((d) => d.id !== base);
          if (other) setJoins([...joins, { dataset_id: other.id, left_column: cols(base)[0], right_column: cols(other.id)[0], how: "left" }]);
        }}>Add join</Button>
        {err && <ErrorBox>{err}</ErrorBox>}
        <div className="flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!joins.length} onClick={submit}>Create dataset</Button></div>
      </div>
    </Modal>
  );
}

function SqlConsole({ objects }: { objects: Obj[] }) {
  const core = objects.find((o) => o.layer === "core")?.name ?? "dw_table";
  const [sql, setSql] = useState(`SELECT *\nFROM ${core}\nLIMIT 20`);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setErr(null);
    try { setRes((await api.post("/api/warehouse/sql", { sql })).data); } catch (e) { setErr(errMsg(e)); setRes(null); } finally { setBusy(false); }
  };
  const samples = [
    `SELECT d.year, d.quarter, count(*) AS records\nFROM ${core} f\nJOIN dim_date d ON CAST(f.${objects.find((o) => o.name === core)?.columns_detail.find((c) => c.type.includes("TIMESTAMP"))?.name ?? "date"} AS DATE) = CAST(d.date_key AS DATE)\nGROUP BY 1, 2 ORDER BY 1, 2`,
    ...objects.filter((o) => o.layer === "mart").slice(0, 2).map((m) => `SELECT * FROM ${m.name}`),
  ];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {samples.map((s, i) => <button key={i} onClick={() => setSql(s)} className="rounded-full border border-line px-2.5 py-1 font-mono text-[11px] text-ink2 hover:border-accent">{s.split("\n")[0].slice(0, 46)}…</button>)}
      </div>
      <textarea value={sql} onChange={(e) => setSql(e.target.value)} rows={7} spellCheck={false}
        onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run(); }}
        className="w-full rounded-lg border border-line bg-surface2 p-3 font-mono text-xs text-ink outline-none focus:border-accent" />
      <div className="flex items-center gap-2">
        <Button variant="primary" icon={<Play className="h-4 w-4" />} loading={busy} onClick={run}>Run query</Button>
        <span className="text-xs text-muted">Read-only · Ctrl/⌘ + Enter · only your own tables · max 5,000 rows</span>
      </div>
      {err && <ErrorBox>{err}</ErrorBox>}
      {res && <><div className="text-xs text-muted">{res.row_count} rows</div><DataTable columns={res.columns} rows={res.rows} maxHeight={400} /></>}
    </div>
  );
}

export default function WarehousePage() {
  const objs = useFetch<Obj[]>("/api/warehouse/objects");
  const rels = useFetch<Rel[]>("/api/warehouse/relationships");
  const ds = useFetch<Dataset[]>("/api/datasets");
  const [tab, setTab] = useState<"model" | "objects" | "sql">("model");
  const [sel, setSel] = useState<string | null>(null);
  const [join, setJoin] = useState<{ open: boolean; preset: Rel[] }>({ open: false, preset: [] });
  const [full, setFull] = useState<Record<number, Dataset>>({});

  const counts = useMemo(() => (objs.data ?? []).reduce<Record<string, number>>((a, o) => ({ ...a, [o.layer]: (a[o.layer] ?? 0) + 1 }), {}), [objs.data]);
  const openJoin = async (preset: Rel[]) => {
    const need = (ds.data ?? []).filter((d) => !full[d.id]);
    const loaded = await Promise.all(need.map((d) => api.get(`/api/datasets/${d.id}`).then((r) => r.data as Dataset)));
    const next = { ...full };
    loaded.forEach((d) => (next[d.id] = d));
    setFull(next);
    setJoin({ open: true, preset });
  };
  if (objs.loading || ds.loading) return <Spinner />;
  const objects = objs.data ?? [];
  const selected = objects.find((o) => o.name === sel);

  return (
    <div>
      <PageHeader title="Data Warehouse" subtitle="Centralised DuckDB columnar warehouse – layered, modelled and queryable" icon={<WarehouseIcon className="h-5 w-5" />}
        actions={<Button variant="primary" icon={<GitMerge className="h-4 w-4" />} onClick={() => openJoin(rels.data ?? [])}>Build integrated dataset</Button>} />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {LAYERS.map((l) => (
          <div key={l.id} className="rounded-xl border border-line bg-surface p-4" style={{ borderTop: `3px solid ${l.color}` }}>
            <div className="text-xs text-muted">{l.name}</div>
            <div className="mt-1 text-2xl font-semibold">{counts[l.id] ?? 0}</div>
            <div className="text-xs text-muted">{l.desc}</div>
          </div>
        ))}
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "model", label: "Relationships & model", icon: <Link2 className="h-4 w-4" /> },
        { id: "objects", label: "Tables & views", icon: <Boxes className="h-4 w-4" /> },
        { id: "sql", label: "SQL console", icon: <Code2 className="h-4 w-4" /> },
      ]} />
      <div className="pt-5">
        {tab === "model" && (
          rels.loading ? <Spinner label="Discovering relationships…" /> : !rels.data?.length ? <Empty title="No relationships detected">Add related datasets (e.g. orders + customers) and shared keys are discovered automatically.</Empty> : (
            <div className="space-y-5">
              <Card title="Automatically discovered relationships" subtitle="Detected by comparing key-like columns across datasets (value containment + name similarity)">
                <ERDiagram rels={rels.data} datasets={ds.data ?? []} />
              </Card>
              <div className="grid gap-3 md:grid-cols-2">
                {rels.data.map((r, i) => (
                  <div key={i} className="rounded-xl border border-line bg-surface p-4">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="font-medium">{r.from_dataset}</span><span className="font-mono text-xs text-muted">.{r.from_column}</span>
                      <ArrowRight className="h-4 w-4 text-muted" />
                      <span className="font-medium">{r.to_dataset}</span><span className="font-mono text-xs text-muted">.{r.to_column}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge tone="accent">{r.cardinality}</Badge>
                      <Badge tone={r.confidence > 0.85 ? "good" : "warn"}>confidence {(r.confidence * 100).toFixed(0)}%</Badge>
                      <Badge>{r.containment_pct}% keys matched</Badge>
                      {r.orphan_values > 0 && <Badge tone="warn">{r.orphan_values} orphan keys</Badge>}
                    </div>
                    <Button size="sm" className="mt-3" icon={<GitMerge className="h-3.5 w-3.5" />} onClick={() => openJoin([r])}>Join these</Button>
                  </div>
                ))}
              </div>
            </div>
          )
        )}
        {tab === "objects" && (
          <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
            <Card>
              {LAYERS.map((l) => {
                const items = objects.filter((o) => o.layer === l.id);
                if (!items.length) return null;
                return (
                  <div key={l.id} className="mb-3">
                    <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">{l.name}</div>
                    {items.map((o) => (
                      <button key={o.name} onClick={() => setSel(o.name)} className={cx("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-surface2", sel === o.name && "bg-surface2")}>
                        <span className="h-2 w-2 rounded-full" style={{ background: l.color }} />
                        <span className="flex-1 truncate font-mono">{o.name}</span>
                        {o.rows !== null && <span className="tabular text-muted">{o.rows.toLocaleString()}</span>}
                      </button>
                    ))}
                  </div>
                );
              })}
            </Card>
            <Card title={selected ? <span className="font-mono">{selected.name}</span> : "Select a table"} subtitle={selected ? `${selected.kind} · ${selected.layer} layer${selected.dataset ? ` · dataset “${selected.dataset}”` : ""}` : "Browse the warehouse catalog"}>
              {!selected ? <Empty title="Pick a table or view on the left" /> : selected.kind === "view" ? (
                <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-surface2 p-3 text-xs">{selected.sql}</pre>
              ) : (
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {selected.columns_detail.map((c) => (
                    <div key={c.name} className="flex justify-between rounded-lg bg-surface2 px-3 py-1.5 text-xs"><span>{label(c.name)} <span className="font-mono text-muted">{c.name}</span></span><span className="font-mono text-muted">{c.type}</span></div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
        {tab === "sql" && <Card><SqlConsole objects={objects} /></Card>}
      </div>
      {join.open && <JoinBuilder open onClose={() => setJoin({ open: false, preset: [] })} datasets={Object.values(full).length ? Object.values(full) : ds.data ?? []} preset={join.preset} />}
    </div>
  );
}
