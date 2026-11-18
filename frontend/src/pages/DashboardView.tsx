import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, Pencil, Plus, Printer, RotateCcw, Save, Wand2, X } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dashboard, Dataset, Filter, Widget } from "../types";
import { Button, Empty, ErrorBox, Input, PageHeader, Spinner } from "../components/ui";
import WidgetCard from "../components/Widget";
import FilterBar from "../components/FilterBar";
import ChartBuilder from "../components/ChartBuilder";

export default function DashboardView() {
  const id = Number(useParams().id);
  const dash = useFetch<Dashboard>(`/api/dashboards/${id}`);
  const [ds, setDs] = useState<Dataset | null>(null);
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [builder, setBuilder] = useState<{ open: boolean; edit: Widget | null }>({ open: false, edit: null });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!dash.data) return;
    setWidgets(dash.data.widgets);
    setFilters(dash.data.filters ?? []);
    setName(dash.data.name);
    api.get(`/api/datasets/${dash.data.dataset_id}`).then((r) => setDs(r.data));
  }, [dash.data]);

  if (dash.loading || !ds) return <Spinner />;
  if (dash.error || !dash.data) return <ErrorBox>{dash.error}</ErrorBox>;

  const change = (w: Widget[]) => { setWidgets(w); setDirty(true); };
  const save = async () => {
    setBusy(true); setErr(null);
    try { await api.patch(`/api/dashboards/${id}`, { name, widgets, filters }); setDirty(false); setEditing(false); dash.reload(); }
    catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  const regenerate = async () => {
    if (!confirm("Replace all widgets with a freshly generated layout?")) return;
    const r = await api.post(`/api/dashboards/${id}/regenerate`);
    setWidgets(r.data.widgets); setFilters([]); setDirty(false);
  };
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= widgets.length) return;
    const w = [...widgets];
    [w[i], w[j]] = [w[j], w[i]];
    change(w);
  };

  return (
    <div>
      <PageHeader
        title={editing ? <Input value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }} className="h-9 text-lg font-semibold" /> : name}
        subtitle={<>Dataset: <Link to={`/datasets/${ds.id}`} className="text-accent">{ds.name}</Link> · {ds.row_count.toLocaleString()} rows · {widgets.length} widgets</>}
        actions={editing ? (
          <>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setBuilder({ open: true, edit: null })}>Add chart</Button>
            <Button icon={<Wand2 className="h-4 w-4" />} onClick={regenerate}>Regenerate</Button>
            <Button icon={<X className="h-4 w-4" />} onClick={() => { setWidgets(dash.data!.widgets); setName(dash.data!.name); setEditing(false); setDirty(false); }}>Cancel</Button>
            <Button variant="primary" icon={<Check className="h-4 w-4" />} loading={busy} onClick={save}>Done</Button>
          </>
        ) : (
          <>
            {dirty && <Button variant="primary" icon={<Save className="h-4 w-4" />} loading={busy} onClick={save}>Save filters</Button>}
            {filters.length > 0 && <Button icon={<RotateCcw className="h-4 w-4" />} onClick={() => setFilters([])}>Reset</Button>}
            <Button icon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Print / PDF</Button>
            <Button variant="primary" icon={<Pencil className="h-4 w-4" />} onClick={() => setEditing(true)}>Edit</Button>
          </>
        )}
      />
      {err && <div className="mb-3"><ErrorBox>{err}</ErrorBox></div>}
      <FilterBar datasetId={ds.id} profile={ds.profile!} filters={filters} onChange={(f) => { setFilters(f); setDirty(true); }} />
      {widgets.length === 0 ? (
        <Empty title="This dashboard is empty">Click <b>Edit → Add chart</b> to build your first visualization.</Empty>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {widgets.map((w, i) => (
            <WidgetCard key={w.id} datasetId={ds.id} widget={w} filters={filters} editing={editing}
              onRemove={() => change(widgets.filter((x) => x.id !== w.id))}
              onEdit={() => setBuilder({ open: true, edit: w })}
              onResize={(nw) => change(widgets.map((x) => (x.id === w.id ? { ...x, w: nw } : x)))}
              onMove={(d) => move(i, d)} />
          ))}
        </div>
      )}
      <ChartBuilder open={builder.open} initial={builder.edit} datasetId={ds.id} profile={ds.profile!}
        onClose={() => setBuilder({ open: false, edit: null })}
        onSave={(w) => {
          change(builder.edit ? widgets.map((x) => (x.id === w.id ? w : x)) : [...widgets, w]);
          setBuilder({ open: false, edit: null });
          setEditing(true);
        }} />
    </div>
  );
}
