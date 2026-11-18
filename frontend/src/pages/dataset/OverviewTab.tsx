import { Calendar, Hash, Key, Tag, Type } from "lucide-react";
import type { ColumnProfile, Dataset } from "../../types";
import { Badge, Card, Stat } from "../../components/ui";
import { compact, label } from "../../format";

const ROLE: Record<string, { icon: any; tone: any; text: string }> = {
  measure: { icon: Hash, tone: "info", text: "Measure" },
  dimension: { icon: Tag, tone: "accent", text: "Dimension" },
  time: { icon: Calendar, tone: "warn", text: "Time" },
  identifier: { icon: Key, tone: "neutral", text: "Identifier" },
  text: { icon: Type, tone: "neutral", text: "Text" },
};

function Summary({ c }: { c: ColumnProfile }) {
  const s = c.stats as any;
  if (c.role === "measure" && s) return <span className="tabular">min {compact(s.min)} · median {compact(s.median)} · max {compact(s.max)}</span>;
  if (c.role === "time" && s) return <span>{String(s.min).slice(0, 10)} → {String(s.max).slice(0, 10)}</span>;
  if (c.top_values?.length) return <span className="truncate">{c.top_values.slice(0, 3).map((t) => t.value).join(", ")}{c.unique > 3 ? "…" : ""}</span>;
  return <span>{c.sample_values.slice(0, 3).join(", ")}</span>;
}

export default function OverviewTab({ ds }: { ds: Dataset }) {
  const p = ds.profile!;
  const counts = p.columns.reduce<Record<string, number>>((a, c) => ({ ...a, [c.role]: (a[c.role] ?? 0) + 1 }), {});
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Measures" value={counts.measure ?? 0} sub="numeric, aggregatable" />
        <Stat label="Dimensions" value={counts.dimension ?? 0} sub="categories to slice by" />
        <Stat label="Time columns" value={counts.time ?? 0} sub={p.primary_time ? `primary: ${p.primary_time}` : "none detected"} />
        <Stat label="Identifiers" value={counts.identifier ?? 0} sub="keys & IDs" />
        <Stat label="ETL time" value={`${((p.timings?.extract_s ?? 0) + (p.timings?.transform_s ?? 0) + (p.timings?.load_s ?? 0)).toFixed(2)}s`} sub="extract + transform + load" />
      </div>
      <Card title="Automatically inferred schema" subtitle="Semantic types and analytical roles detected from names and values – these drive the auto-generated charts, KPIs and insights">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink2">
              <tr className="border-b border-line">{["Column", "Role", "Semantic type", "Storage", "Missing", "Unique", "Summary"].map((h) => <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {p.columns.map((c) => {
                const r = ROLE[c.role] ?? ROLE.text;
                return (
                  <tr key={c.name} className="border-b border-line last:border-0">
                    <td className="px-3 py-2 font-medium">{label(c.name)}<div className="font-mono text-[11px] font-normal text-muted">{c.name}</div></td>
                    <td className="px-3 py-2"><Badge tone={r.tone}><r.icon className="h-3 w-3" />{r.text}</Badge></td>
                    <td className="px-3 py-2 text-ink2">{c.semantic_type}{c.default_agg ? <span className="text-muted"> · {c.default_agg}</span> : null}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted">{c.dtype}</td>
                    <td className="tabular px-3 py-2">{c.missing_pct}%</td>
                    <td className="tabular px-3 py-2">{c.unique.toLocaleString()}</td>
                    <td className="max-w-[320px] truncate px-3 py-2 text-xs text-ink2"><Summary c={c} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
