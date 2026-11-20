import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Code2, Maximize2, Minimize2, Pencil, Table2, Trash2 } from "lucide-react";
import { api, errMsg } from "../api";
import type { Filter, Widget } from "../types";
import ChartRenderer, { DataTable } from "./charts/ChartRenderer";
import { cx } from "./ui";

const HEIGHT: Record<string, number> = { kpi: 0, table: 0, heatmap: 0 };

export function useWidgetData(datasetId: number, widget: Widget, filters: Filter[], enabled = true) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const key = JSON.stringify([widget.type, widget.spec, filters]);
  useEffect(() => {
    if (widget.type === "section" || !enabled) {
      setLoading(widget.type !== "section");
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .post(`/api/datasets/${datasetId}/widget-data`, { widget, filters })
      .then((r) => alive && setData(r.data))
      .catch((e) => alive && setError(errMsg(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, key, enabled]);
  return { data, error, loading };
}

type Props = {
  datasetId: number;
  widget: Widget;
  filters: Filter[];
  editing?: boolean;
  onRemove?: () => void;
  onEdit?: () => void;
  onResize?: (w: number) => void;
  onMove?: (dir: -1 | 1) => void;
  /** combined dashboards: name of the dataset this chart reads from */
  sourceName?: string;
};

function Section({ widget, editing, onRemove, onMove, onEdit }: Props) {
  const iconBtn = "rounded p-1 text-muted hover:bg-surface2 hover:text-ink";
  return (
    <div className="col-span-1 mt-2 flex items-end justify-between gap-3 border-b border-line pb-2 sm:col-span-2 lg:col-span-4 break-inside-avoid">
      <div className="min-w-0">
        <h2 className="truncate text-base font-semibold text-ink">{widget.title}</h2>
        {widget.spec?.subtitle && <p className="text-xs text-muted">{widget.spec.subtitle}</p>}
      </div>
      {editing && (
        <div className="no-print flex shrink-0 items-center">
          <button className={iconBtn} title="Move up" onClick={() => onMove?.(-1)}><ChevronLeft className="h-3.5 w-3.5 rotate-90" /></button>
          <button className={iconBtn} title="Move down" onClick={() => onMove?.(1)}><ChevronRight className="h-3.5 w-3.5 rotate-90" /></button>
          <button className={iconBtn} title="Rename" onClick={onEdit}><Pencil className="h-3.5 w-3.5" /></button>
          <button className={cx(iconBtn, "hover:text-critical")} title="Remove section header" onClick={onRemove}><Trash2 className="h-3.5 w-3.5" /></button>
        </div>
      )}
    </div>
  );
}

export default function WidgetCard(props: Props) {
  if (props.widget.type === "section") return <Section {...props} />;
  return <ChartCard {...props} />;
}

function ChartCard({ datasetId, widget, filters, editing, onRemove, onEdit, onResize, onMove, sourceName }: Props) {
  const { data, error, loading } = useWidgetData(datasetId, widget, filters);
  const [showTable, setShowTable] = useState(false);
  const [showSql, setShowSql] = useState(false);
  const span = { 1: "lg:col-span-1", 2: "lg:col-span-2", 3: "lg:col-span-3", 4: "lg:col-span-4" }[Math.min(4, Math.max(1, widget.w))] ?? "lg:col-span-2";
  const isKpi = widget.type === "kpi";
  const height = HEIGHT[widget.type] ?? 260;
  const iconBtn = "rounded p-1 text-muted hover:bg-surface2 hover:text-ink";

  return (
    <div className={cx("group col-span-1 flex flex-col rounded-xl border border-line bg-surface break-inside-avoid sm:col-span-2", isKpi ? "sm:col-span-1" : "", span)}>
      <div className="flex items-start justify-between gap-2 px-4 pt-3">
        <div className="min-w-0">
          <h3 className={cx("truncate font-medium", isKpi ? "text-xs text-muted" : "text-sm text-ink")} title={widget.title}>{widget.title}</h3>
          {sourceName && <div className="truncate text-[10px] uppercase tracking-wide text-muted" title={sourceName}>{sourceName}</div>}
        </div>
        <div className={cx("no-print flex shrink-0 items-center", editing ? "opacity-100" : "opacity-0 transition group-hover:opacity-100")}>
          {!isKpi && data?.rows && (
            <button className={iconBtn} title="View as table" onClick={() => setShowTable((s) => !s)}><Table2 className="h-3.5 w-3.5" /></button>
          )}
          {data?.sql && <button className={iconBtn} title="Show SQL" onClick={() => setShowSql((s) => !s)}><Code2 className="h-3.5 w-3.5" /></button>}
          {editing && (
            <>
              <button className={iconBtn} title="Move left" onClick={() => onMove?.(-1)}><ChevronLeft className="h-3.5 w-3.5" /></button>
              <button className={iconBtn} title="Move right" onClick={() => onMove?.(1)}><ChevronRight className="h-3.5 w-3.5" /></button>
              <button className={iconBtn} title="Narrower" onClick={() => onResize?.(Math.max(1, widget.w - 1))}><Minimize2 className="h-3.5 w-3.5" /></button>
              <button className={iconBtn} title="Wider" onClick={() => onResize?.(Math.min(4, widget.w + 1))}><Maximize2 className="h-3.5 w-3.5" /></button>
              <button className={iconBtn} title="Edit" onClick={onEdit}><Pencil className="h-3.5 w-3.5" /></button>
              <button className={cx(iconBtn, "hover:text-critical")} title="Remove" onClick={onRemove}><Trash2 className="h-3.5 w-3.5" /></button>
            </>
          )}
        </div>
      </div>
      <div className="flex-1 px-4 pb-4 pt-2">
        {loading && !data ? (
          <div className="animate-pulse rounded-lg bg-surface2" style={{ height: isKpi ? 56 : height || 220 }} />
        ) : error ? (
          <div className="py-6 text-center text-xs text-critical">{error}</div>
        ) : showTable && data?.rows ? (
          <DataTable columns={Object.keys(data.rows[0] ?? {})} rows={data.rows} maxHeight={height || 300} />
        ) : (
          <div className={loading ? "opacity-60 transition" : "transition"}>
            <ChartRenderer type={widget.type} data={data} height={height} format={widget.spec?.format} grain={widget.spec?.time_grain} />
          </div>
        )}
        {data?.filters_ignored?.length > 0 && !isKpi && (
          <div className="mt-1 text-[10px] text-muted">Not filtered by: {data.filters_ignored.join(", ")} (not in this data)</div>
        )}
        {showSql && data?.sql && <pre className="mt-2 overflow-x-auto rounded-md bg-surface2 p-2 text-[11px] text-ink2">{data.sql}</pre>}
      </div>
    </div>
  );
}
