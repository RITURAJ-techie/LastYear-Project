import { useEffect, useMemo, useState } from "react";
import type { Profile, Source, Widget, WidgetType } from "../types";
import { label } from "../format";
import { Button, Field, Input, Modal, Select } from "./ui";
import ChartRenderer from "./charts/ChartRenderer";
import { useWidgetData } from "./Widget";

const TYPES: { id: WidgetType; name: string }[] = [
  { id: "kpi", name: "KPI card" }, { id: "line", name: "Line" }, { id: "area", name: "Area" }, { id: "bar", name: "Bar" },
  { id: "hbar", name: "Horizontal bar" }, { id: "stacked_bar", name: "Stacked bar" }, { id: "pie", name: "Pie" }, { id: "donut", name: "Donut" },
  { id: "scatter", name: "Scatter" }, { id: "histogram", name: "Histogram" }, { id: "heatmap", name: "Correlation heatmap" }, { id: "table", name: "Table" },
];
const AGGS = ["sum", "avg", "count", "count_distinct", "min", "max", "median"];

function uid() {
  return Math.random().toString(36).slice(2, 12);
}

export default function ChartBuilder({ open, onClose, onSave, sources, defaultDatasetId, initial }: {
  open: boolean; onClose: () => void; onSave: (w: Widget) => void; sources: Source[]; defaultDatasetId: number; initial?: Widget | null;
}) {
  const [datasetId, setDatasetId] = useState(defaultDatasetId);
  useEffect(() => {
    if (open) setDatasetId(initial?.dataset_id ?? defaultDatasetId);
  }, [open, initial, defaultDatasetId]);
  const source = sources.find((x) => x.datasetId === datasetId) ?? sources[0];
  const profile: Profile = source.profile;
  const multi = sources.length > 1;
  const cols = profile.columns;
  const measures = profile.measures;
  const groupable = cols.filter((c) => c.role !== "measure" || c.unique <= 30).map((c) => c.name);
  const [type, setType] = useState<WidgetType>("bar");
  const [title, setTitle] = useState("");
  const [x, setX] = useState<string>("");
  const [series, setSeries] = useState("");
  const [measure, setMeasure] = useState<string>(measures[0] ?? "*");
  const [agg, setAgg] = useState("sum");
  const [measure2, setMeasure2] = useState("");
  const [grain, setGrain] = useState("month");
  const [limit, setLimit] = useState(12);
  const [w, setW] = useState(2);
  const [fmt, setFmt] = useState("number");
  const [yScatter, setYScatter] = useState(measures[1] ?? measures[0] ?? "");
  const [tableCols, setTableCols] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    const same = !!initial && (initial.dataset_id ?? defaultDatasetId) === datasetId;
    const s = same ? initial!.spec : {};
    setType(initial?.type ?? "bar");
    setTitle(same ? initial!.title : "");
    setW(initial?.w ?? 2);
    setX(s.x ?? profile.dimensions[0] ?? profile.primary_time ?? "");
    setSeries(s.series ?? "");
    setMeasure(s.y?.[0]?.column ?? s.column ?? measures[0] ?? "*");
    const m0 = s.y?.[0]?.column ?? s.column ?? measures[0];
    setAgg(s.y?.[0]?.agg ?? s.agg ?? profile.columns.find((c) => c.name === m0)?.default_agg ?? "sum");
    setMeasure2(s.y?.[1]?.column ?? "");
    setGrain(s.time_grain ?? "month");
    setLimit(s.limit ?? 12);
    setFmt(s.format ?? "number");
    setYScatter(s.y && typeof s.y === "string" ? s.y : measures[1] ?? measures[0] ?? "");
    setTableCols(s.columns ?? cols.slice(0, 6).map((c) => c.name));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial, datasetId]);

  const isTimeX = x && x === profile.primary_time || cols.find((c) => c.name === x)?.semantic_type === "datetime";

  const widget: Widget = useMemo(() => {
    let spec: Record<string, any> = {};
    if (type === "kpi") spec = { column: measure, agg: measure === "*" ? "count" : agg, format: fmt };
    else if (type === "histogram") spec = { column: measure };
    else if (type === "scatter") spec = { x: measure, y: yScatter, color: series || null };
    else if (type === "table") spec = { columns: tableCols, order_by: measures[0], limit };
    else if (type === "heatmap") spec = {};
    else {
      const y = [{ column: measure, agg: measure === "*" ? "count" : agg }];
      if (measure2 && !["pie", "donut", "stacked_bar"].includes(type)) y.push({ column: measure2, agg });
      spec = { x, y, series: series || null, time_grain: isTimeX ? grain : null, limit: isTimeX ? undefined : limit };
    }
    const auto = type === "kpi" ? `${agg === "avg" ? "Average" : agg === "count" || measure === "*" ? "Count of" : "Total"} ${measure === "*" ? "records" : label(measure)}`
      : type === "histogram" ? `Distribution of ${label(measure)}`
      : type === "scatter" ? `${label(measure)} vs ${label(yScatter)}`
      : type === "heatmap" ? "Correlation Matrix" : type === "table" ? "Records"
      : `${measure === "*" ? "Records" : label(measure)} by ${label(x)}`;
    return { id: initial?.id ?? uid(), type, title: title || auto, w: type === "kpi" ? Math.min(w, 1) || 1 : w, spec,
             ...(multi ? { dataset_id: datasetId } : {}) };
  }, [type, title, x, series, measure, agg, measure2, grain, limit, w, fmt, yScatter, tableCols, isTimeX, initial, measures, multi, datasetId]);

  // only preview once every referenced column exists in the selected dataset (avoids a stale request
  // with the previous dataset's columns right after switching datasets)
  const known = new Set(cols.map((c) => c.name));
  const sp = widget.spec;
  const refs = [sp.x, sp.series, sp.column, sp.color, sp.order_by, ...(Array.isArray(sp.y) ? sp.y.map((y: any) => y.column) : [sp.y]), ...(sp.columns ?? [])];
  const valid = refs.every((c) => !c || c === "*" || known.has(c));
  const preview = useWidgetData(datasetId, widget, [], valid);
  const needsX = !["kpi", "histogram", "scatter", "table", "heatmap"].includes(type);

  return (
    <Modal open={open} onClose={onClose} title={initial ? "Edit chart" : "Add chart"} wide>
      <div className="grid gap-5 md:grid-cols-[300px_1fr]">
        <div className="space-y-3">
          {multi && (
            <Field label="Dataset">
              <Select value={datasetId} onChange={(e) => setDatasetId(Number(e.target.value))} className="w-full">
                {sources.map((x) => <option key={x.datasetId} value={x.datasetId}>{x.name}</option>)}
              </Select>
            </Field>
          )}
          <Field label="Chart type">
            <Select value={type} onChange={(e) => setType(e.target.value as WidgetType)} className="w-full">
              {TYPES.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </Select>
          </Field>
          <Field label="Title (optional)"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={widget.title} /></Field>
          {needsX && (
            <Field label="Group by (X axis)">
              <Select value={x} onChange={(e) => setX(e.target.value)} className="w-full">
                {groupable.map((c) => <option key={c} value={c}>{label(c)}</option>)}
              </Select>
            </Field>
          )}
          {needsX && isTimeX && (
            <Field label="Time grain">
              <Select value={grain} onChange={(e) => setGrain(e.target.value)} className="w-full">
                {["day", "week", "month", "quarter", "year"].map((g) => <option key={g}>{g}</option>)}
              </Select>
            </Field>
          )}
          {type !== "heatmap" && type !== "table" && (
            <div className="grid grid-cols-[1fr_110px] gap-2">
              <Field label={type === "scatter" ? "X measure" : "Measure"}>
                <Select value={measure} onChange={(e) => {
                  setMeasure(e.target.value);
                  const d = cols.find((c) => c.name === e.target.value)?.default_agg;
                  if (d) setAgg(d);  // e.g. average for age/price/rating, sum for revenue
                }} className="w-full">
                  {type !== "histogram" && type !== "scatter" && <option value="*">Record count</option>}
                  {measures.map((m) => <option key={m} value={m}>{label(m)}</option>)}
                </Select>
              </Field>
              {type !== "histogram" && type !== "scatter" && (
                <Field label="Aggregation">
                  <Select value={agg} onChange={(e) => setAgg(e.target.value)} className="w-full" disabled={measure === "*"}>
                    {AGGS.map((a) => <option key={a}>{a}</option>)}
                  </Select>
                </Field>
              )}
            </div>
          )}
          {type === "scatter" && (
            <Field label="Y measure">
              <Select value={yScatter} onChange={(e) => setYScatter(e.target.value)} className="w-full">
                {measures.map((m) => <option key={m} value={m}>{label(m)}</option>)}
              </Select>
            </Field>
          )}
          {["line", "area", "bar"].includes(type) && !series && (
            <Field label="Second measure (optional)">
              <Select value={measure2} onChange={(e) => setMeasure2(e.target.value)} className="w-full">
                <option value="">None</option>
                {measures.filter((m) => m !== measure).map((m) => <option key={m} value={m}>{label(m)}</option>)}
              </Select>
            </Field>
          )}
          {(["line", "area", "bar", "stacked_bar", "scatter"] as WidgetType[]).includes(type) && (
            <Field label={type === "scatter" ? "Color by (optional)" : "Split into series (optional)"}>
              <Select value={series} onChange={(e) => { setSeries(e.target.value); setMeasure2(""); }} className="w-full">
                <option value="">None</option>
                {profile.dimensions.map((d) => <option key={d} value={d}>{label(d)}</option>)}
              </Select>
            </Field>
          )}
          {type === "kpi" && (
            <Field label="Number format">
              <Select value={fmt} onChange={(e) => setFmt(e.target.value)} className="w-full">
                <option value="number">Number</option><option value="currency">Currency</option><option value="percent">Percent</option>
              </Select>
            </Field>
          )}
          {type === "table" && (
            <Field label="Columns">
              <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
                {cols.map((c) => (
                  <label key={c.name} className="flex items-center gap-2 text-xs">
                    <input type="checkbox" checked={tableCols.includes(c.name)}
                      onChange={(e) => setTableCols((s) => (e.target.checked ? [...s, c.name] : s.filter((x) => x !== c.name)))} />
                    {label(c.name)}
                  </label>
                ))}
              </div>
            </Field>
          )}
          <div className="grid grid-cols-2 gap-2">
            {needsX && !isTimeX && (
              <Field label="Max groups"><Input type="number" min={1} max={100} value={limit} onChange={(e) => setLimit(Number(e.target.value) || 10)} /></Field>
            )}
            <Field label="Width">
              <Select value={w} onChange={(e) => setW(Number(e.target.value))} className="w-full">
                <option value={1}>¼ width</option><option value={2}>½ width</option><option value={3}>¾ width</option><option value={4}>Full width</option>
              </Select>
            </Field>
          </div>
        </div>
        <div className="min-w-0">
          <div className="mb-2 text-xs font-medium text-muted">Live preview</div>
          <div className="rounded-xl border border-line p-4">
            <div className="mb-2 text-sm font-medium">{widget.title}</div>
            {preview.error ? <div className="py-10 text-center text-xs text-critical">{preview.error}</div>
              : preview.data ? <ChartRenderer type={widget.type} data={preview.data} height={280} format={widget.spec.format} grain={widget.spec.time_grain} />
              : <div className="h-[280px] animate-pulse rounded-lg bg-surface2" />}
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => onSave(widget)} disabled={!!preview.error}>{initial ? "Update chart" : "Add to dashboard"}</Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
