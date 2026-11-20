import { useEffect, useRef, useState } from "react";
import { Calendar, ChevronDown, FilterX } from "lucide-react";
import { api } from "../api";
import { label } from "../format";
import type { Filter, Source } from "../types";
import { cx } from "./ui";

function MultiSelect({ datasetId, column, value, onChange }: { datasetId: number; column: string; value: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<{ value: string; count: number }[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open && !options.length) api.get(`/api/datasets/${datasetId}/values/${column}`).then((r) => setOptions(r.data));
  }, [open, datasetId, column, options.length]);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)}
        className={cx("flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs", value.length ? "border-accent bg-accentsoft text-ink" : "border-line bg-surface text-ink2 hover:bg-surface2")}>
        <span className="text-muted">{label(column)}:</span>
        <span className="max-w-[140px] truncate font-medium">{value.length === 0 ? "All" : value.length === 1 ? value[0] : `${value.length} selected`}</span>
        <ChevronDown className="h-3 w-3 text-muted" />
      </button>
      {open && (
        <div className="absolute left-0 top-9 z-30 max-h-72 w-60 overflow-y-auto rounded-lg border border-line bg-surface p-1 shadow-xl">
          {value.length > 0 && <button className="mb-1 w-full rounded px-2 py-1 text-left text-xs text-accent hover:bg-surface2" onClick={() => onChange([])}>Clear selection</button>}
          {options.map((o) => (
            <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-surface2">
              <input type="checkbox" checked={value.includes(o.value)} onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))} />
              <span className="flex-1 truncate">{o.value}</span>
              <span className="tabular text-muted">{o.count.toLocaleString()}</span>
            </label>
          ))}
          {!options.length && <div className="p-2 text-xs text-muted">Loading…</div>}
        </div>
      )}
    </div>
  );
}

/** One row of global filters above the charts: date range + key dimensions.
 *  With several sources (combined dashboard) the date range targets each dataset's own primary
 *  date column ("__time__") and dimension filters apply wherever that column exists. */
export default function FilterBar({ sources, filters, onChange }: { sources: Source[]; filters: Filter[]; onChange: (f: Filter[]) => void }) {
  const multi = sources.length > 1;
  const timed = sources.filter((s) => s.profile.primary_time);
  const t = multi ? (timed.length ? "__time__" : null) : sources[0]?.profile.primary_time ?? null;
  const tstats = timed.map((s) => s.profile.columns.find((c) => c.name === s.profile.primary_time)?.stats as any).filter(Boolean);
  const tmin = tstats.map((x) => String(x.min).slice(0, 10)).sort()[0];
  const tmax = tstats.map((x) => String(x.max).slice(0, 10)).sort().slice(-1)[0];

  // dimensions: shared ones first (present in more datasets), then by chartable cardinality
  const dimMap = new Map<string, { count: number; datasetId: number; unique: number }>();
  sources.forEach((s) => s.profile.dimensions.forEach((d) => {
    const c = s.profile.columns.find((x) => x.name === d);
    if (!c || c.unique > 200) return;
    const prev = dimMap.get(d);
    dimMap.set(d, { count: (prev?.count ?? 0) + 1, datasetId: prev?.datasetId ?? s.datasetId, unique: c.unique });
  }));
  const dims = [...dimMap.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, multi ? 5 : 4);

  const get = (col: string) => filters.find((f) => f.column === col);
  const set = (col: string, f: Filter | null) => onChange([...filters.filter((x) => x.column !== col), ...(f ? [f] : [])]);
  const range = (get(t ?? "")?.value as string[]) ?? ["", ""];

  const preset = (months: number | "ytd") => {
    if (!t || !tmax) return;
    const end = new Date(tmax);
    const start = months === "ytd" ? new Date(end.getFullYear(), 0, 1) : new Date(end.getFullYear(), end.getMonth() - months + 1, 1);
    const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    set(t, { column: t, op: "between", value: [iso(start), iso(end)] });
  };

  return (
    <div className="no-print mb-4 rounded-xl border border-line bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        {t && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted" />
            <input type="date" className="h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink" value={range[0] ?? ""} min={tmin} max={tmax}
              onChange={(e) => set(t, e.target.value || range[1] ? { column: t, op: "between", value: [e.target.value, range[1] ?? ""] } : null)} />
            <span className="text-xs text-muted">to</span>
            <input type="date" className="h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink" value={range[1] ?? ""} min={tmin} max={tmax}
              onChange={(e) => set(t, e.target.value || range[0] ? { column: t, op: "between", value: [range[0] ?? "", e.target.value] } : null)} />
            {[["3M", 3], ["6M", 6], ["12M", 12], ["YTD", "ytd"]].map(([l, m]) => (
              <button key={l as string} onClick={() => preset(m as any)} className="h-8 rounded-lg px-2 text-xs text-ink2 hover:bg-surface2">{l}</button>
            ))}
            <span className="mx-1 h-5 w-px bg-[var(--border)]" />
          </div>
        )}
        {dims.map(([d, info]) => (
          <MultiSelect key={d} datasetId={info.datasetId} column={d} value={((get(d)?.value as string[]) ?? [])}
            onChange={(v) => set(d, v.length ? { column: d, op: "in", value: v } : null)} />
        ))}
        {filters.length > 0 && (
          <button onClick={() => onChange([])} className="ml-auto flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-muted hover:bg-surface2 hover:text-ink">
            <FilterX className="h-3.5 w-3.5" /> Reset filters
          </button>
        )}
      </div>
      {multi && filters.length > 0 && (
        <div className="mt-1.5 text-[11px] text-muted">Filters apply to every chart whose data has that column; the date range uses each dataset's own date column.</div>
      )}
    </div>
  );
}
