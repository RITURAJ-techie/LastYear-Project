import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, Heading, Layers, Pencil, Plus, Printer, RotateCcw, Save, Wand2, X } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dashboard, Dataset, Filter, Source, Widget } from "../types";
import { Badge, Button, Empty, ErrorBox, Input, PageHeader, Spinner } from "../components/ui";
import WidgetCard from "../components/Widget";
import FilterBar from "../components/FilterBar";
import ChartBuilder from "../components/ChartBuilder";

export default function DashboardView() {
  const id = Number(useParams().id);
  const dash = useFetch<Dashboard>(`/api/dashboards/${id}`);
  const [sets, setSets] = useState<Record<number, Dataset>>({});
  const ds = dash.data ? sets[dash.data.dataset_id] ?? null : null;
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
    const ids = dash.data.dataset_ids?.length ? dash.data.dataset_ids : [dash.data.dataset_id];
    Promise.all(ids.map((i) => api.get<Dataset>(`/api/datasets/${i}`).then((r) => r.data).catch(() => null)))
      .then((list) => setSets(Object.fromEntries(list.filter(Boolean).map((d) => [d!.id, d!]))));
  }, [dash.data]);

  if (dash.error) return <ErrorBox>{dash.error}</ErrorBox>;
  if (dash.loading || !dash.data || !ds) return <Spinner />;

  const sources: Source[] = Object.values(sets).filter((d) => d.profile).map((d) => ({ datasetId: d.id, name: d.name, profile: d.profile! }));
  const combined = sources.length > 1;
  const widgetDs = (w: Widget) => w.dataset_id ?? ds.id;
  // label a chart with its dataset only when it differs from the section it sits in
  let sectionDs: number | null = null;
  const labels = widgets.map((w) => {
    if (w.type === "section") {
      sectionDs = w.dataset_id ?? null;
      return undefined;
    }
    return combined && widgetDs(w) !== sectionDs ? sets[widgetDs(w)]?.name : undefined;
  });

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
        subtitle={combined ? (
          <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <Badge tone="accent"><Layers className="h-3 w-3" />Combined · {sources.length} datasets</Badge>
            {sources.map((s, i) => <span key={s.datasetId}>{i > 0 && "· "}<Link to={`/datasets/${s.datasetId}`} className="text-accent">{s.name}</Link></span>)}
          </span>
        ) : <>Dataset: <Link to={`/datasets/${ds.id}`} className="text-accent">{ds.name}</Link> · {ds.row_count.toLocaleString()} rows · {widgets.length} widgets</>}
        actions={editing ? (
          <>
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setBuilder({ open: true, edit: null })}>Add chart</Button>
            {combined && <Button icon={<Heading className="h-4 w-4" />} onClick={() => {
              const t = prompt("Section title");
              if (t) change([...widgets, { id: Math.random().toString(36).slice(2, 12), type: "section", title: t, w: 4, spec: {} }]);
            }}>Add section</Button>}
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
      <FilterBar sources={sources} filters={filters} onChange={(f) => { setFilters(f); setDirty(true); }} />
      {widgets.length === 0 ? (
        <Empty title="This dashboard is empty">Click <b>Edit → Add chart</b> to build your first visualization.</Empty>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {widgets.map((w, i) => (
            <WidgetCard key={w.id} datasetId={widgetDs(w)} widget={w} filters={filters} editing={editing}
              sourceName={labels[i]}
              onRemove={() => change(widgets.filter((x) => x.id !== w.id))}
              onEdit={() => {
                if (w.type === "section") {
                  const t = prompt("Section title", w.title);
                  if (t) change(widgets.map((x) => (x.id === w.id ? { ...x, title: t } : x)));
                } else setBuilder({ open: true, edit: w });
              }}
              onResize={(nw) => change(widgets.map((x) => (x.id === w.id ? { ...x, w: nw } : x)))}
              onMove={(d) => move(i, d)} />
          ))}
        </div>
      )}
      <ChartBuilder open={builder.open} initial={builder.edit} sources={sources} defaultDatasetId={builder.edit ? widgetDs(builder.edit) : ds.id}
        onClose={() => setBuilder({ open: false, edit: null })}
        onSave={(w) => {
          change(builder.edit ? widgets.map((x) => (x.id === w.id ? w : x)) : [...widgets, w]);
          setBuilder({ open: false, edit: null });
          setEditing(true);
        }} />
    </div>
  );
}
