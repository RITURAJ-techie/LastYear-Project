import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { LayoutDashboard, Plus, Trash2, Wand2 } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dashboard, Dataset } from "../types";
import { Badge, Button, Empty, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner } from "../components/ui";
import { timeAgo } from "../format";

export default function Dashboards() {
  const [params] = useSearchParams();
  const dsFilter = params.get("dataset");
  const nav = useNavigate();
  const { data, loading, reload } = useFetch<Dashboard[]>(`/api/dashboards${dsFilter ? `?dataset_id=${dsFilter}` : ""}`);
  const datasets = useFetch<Dataset[]>("/api/datasets");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [dsId, setDsId] = useState<number>(Number(dsFilter) || 0);
  const [auto, setAuto] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // jump straight into the dataset's dashboard when arriving from a dataset
  useEffect(() => {
    if (dsFilter && data && data.length === 1) nav(`/dashboards/${data[0].id}`, { replace: true });
  }, [dsFilter, data, nav]);
  const create = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api.post("/api/dashboards", { dataset_id: dsId || datasets.data?.[0]?.id, name: name || "New dashboard", auto });
      nav(`/dashboards/${r.data.id}`);
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  const remove = async (id: number) => {
    if (!confirm("Delete this dashboard?")) return;
    await api.delete(`/api/dashboards/${id}`);
    reload();
  };

  return (
    <div>
      <PageHeader title="Dashboards" subtitle="Auto-generated and custom interactive dashboards" icon={<LayoutDashboard className="h-5 w-5" />}
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>New dashboard</Button>} />
      {dsFilter && <div className="mb-3 text-sm text-muted">Showing dashboards for one dataset · <Link to="/dashboards" className="text-accent">show all</Link></div>}
      {loading ? <Spinner /> : !data?.length ? <Empty icon={<LayoutDashboard className="h-8 w-8" />} title="No dashboards yet">Dashboards are generated automatically for each dataset you add.</Empty> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((d) => (
            <div key={d.id} className="group relative rounded-xl border border-line bg-surface p-4 transition hover:border-accent">
              <Link to={`/dashboards/${d.id}`} className="block">
                <div className="mb-3 grid h-20 grid-cols-4 gap-1">
                  {d.widgets.slice(0, 8).map((w, i) => (
                    <div key={i} className="rounded bg-surface2" style={{ gridColumn: `span ${Math.min(w.w, 4)}` }}>
                      <div className="h-full rounded" style={{ background: `color-mix(in srgb, var(--series-${(i % 3) + 1}) 18%, transparent)` }} />
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-2"><span className="truncate text-sm font-semibold">{d.name}</span>{d.is_auto && <Badge tone="accent"><Wand2 className="h-3 w-3" />auto</Badge>}</div>
                <div className="mt-0.5 text-xs text-muted">{d.dataset_name} · {d.widgets.length} widgets · updated {timeAgo(d.updated_at)}</div>
              </Link>
              <button onClick={() => remove(d.id)} className="absolute right-3 top-3 rounded p-1 text-muted opacity-0 hover:bg-surface2 hover:text-critical group-hover:opacity-100" title="Delete"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="New dashboard">
        <div className="space-y-3">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Sales performance" /></Field>
          <Field label="Dataset">
            <Select value={dsId} onChange={(e) => setDsId(Number(e.target.value))} className="w-full">
              {(datasets.data ?? []).filter((d) => d.status === "ready").map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Start with AI-recommended charts</label>
          {err && <ErrorBox>{err}</ErrorBox>}
          <div className="flex justify-end gap-2"><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={create}>Create</Button></div>
        </div>
      </Modal>
    </div>
  );
}
