import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { compact, dateLabel, full, label } from "../../format";
import type { ChartResult, WidgetType } from "../../types";
import Heatmap from "./Heatmap";

export const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);
const MUTED = "var(--text-muted)";

const axisProps = { stroke: "var(--axis)", tickLine: false, tick: { fill: "var(--text-muted)", fontSize: 11 } } as const;

function TooltipBox({ active, payload, label: lab, formatLabel, fmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      {lab !== undefined && lab !== null && <div className="mb-1 font-medium text-ink">{formatLabel ? formatLabel(lab) : String(lab)}</div>}
      {payload.map((p: any) => (
        <div key={p.dataKey ?? p.name} className="flex items-center gap-2 text-ink2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color ?? p.payload?.fill }} />
          <span>{label(String(p.name))}</span>
          <span className="tabular ml-auto pl-3 font-medium text-ink">{fmt ? fmt(p.value) : full(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

const legendStyle = { fontSize: 11, color: "var(--text-secondary)", paddingTop: 4 };
const legendFormatter = (v: string) => <span style={{ color: "var(--text-secondary)" }}>{label(v)}</span>;

export type ChartProps = {
  type: WidgetType;
  data: ChartResult | any;
  height?: number;
  format?: string;
  grain?: string;
};

export default function ChartRenderer({ type, data, height = 260, format = "number", grain }: ChartProps) {
  if (!data) return null;
  if (type === "heatmap") return <Heatmap data={data} />;
  if (type === "table") return <DataTable columns={data.columns ?? Object.keys(data.rows?.[0] ?? {})} rows={data.rows ?? []} />;
  if (type === "kpi") return <Kpi data={data} format={format} />;

  const rows: any[] = data.rows ?? [];
  if (!rows.length) return <div className="flex items-center justify-center text-sm text-muted" style={{ height }}>No data for the current filters</div>;
  const x: string = data.x ?? "x";
  const ys: string[] = data.y ?? [];
  const multi = ys.length > 1;
  const fmtX = (v: any) => (data.is_time ? dateLabel(v, grain) : String(v));
  const fmtY = (v: any) => compact(v);

  if (type === "line" || type === "area") {
    const Chart = type === "area" ? AreaChart : LineChart;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <Chart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            {ys.map((_, i) => (
              <linearGradient key={i} id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES[i % 8]} stopOpacity={0.28} />
                <stop offset="100%" stopColor={SERIES[i % 8]} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey={x} {...axisProps} tickFormatter={fmtX} minTickGap={24} />
          <YAxis {...axisProps} axisLine={false} tickFormatter={fmtY} width={52} />
          <Tooltip content={<TooltipBox formatLabel={fmtX} />} cursor={{ stroke: "var(--axis)", strokeWidth: 1 }} />
          {multi && <Legend wrapperStyle={legendStyle} formatter={legendFormatter} iconType="circle" iconSize={8} />}
          {ys.map((y, i) =>
            type === "area" ? (
              <Area key={y} type="monotone" dataKey={y} stroke={SERIES[i % 8]} strokeWidth={2} fill={`url(#grad-${i})`} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }} />
            ) : (
              <Line key={y} type="monotone" dataKey={y} stroke={SERIES[i % 8]} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }} />
            ),
          )}
        </Chart>
      </ResponsiveContainer>
    );
  }

  if (type === "bar" || type === "stacked_bar" || type === "histogram") {
    const stacked = type === "stacked_bar";
    const hist = type === "histogram";
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barCategoryGap={hist ? 1 : "22%"}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey={x} {...axisProps} tickFormatter={fmtX} minTickGap={8} interval="preserveStartEnd" />
          <YAxis {...axisProps} axisLine={false} tickFormatter={fmtY} width={52} />
          <Tooltip content={<TooltipBox formatLabel={fmtX} />} cursor={{ fill: "var(--surface-2)" }} />
          {multi && <Legend wrapperStyle={legendStyle} formatter={legendFormatter} iconType="circle" iconSize={8} />}
          {ys.map((y, i) => (
            <Bar
              key={y}
              dataKey={y}
              stackId={stacked ? "s" : undefined}
              fill={hist ? SERIES[0] : SERIES[i % 8]}
              radius={stacked ? (i === ys.length - 1 ? [4, 4, 0, 0] : 0) : hist ? [2, 2, 0, 0] : [4, 4, 0, 0]}
              maxBarSize={hist ? undefined : 48}
              stroke={stacked ? "var(--surface-1)" : undefined}
              strokeWidth={stacked ? 1 : 0}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (type === "hbar") {
    const h = Math.max(height, rows.length * 26 + 30);
    return (
      <ResponsiveContainer width="100%" height={h}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 40, left: 4, bottom: 0 }} barCategoryGap="22%">
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" {...axisProps} tickFormatter={fmtY} />
          <YAxis type="category" dataKey={x} {...axisProps} axisLine={false} width={110} tickFormatter={(v) => (String(v).length > 16 ? String(v).slice(0, 15) + "…" : String(v))} />
          <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--surface-2)" }} />
          {ys.map((y, i) => (
            <Bar key={y} dataKey={y} fill={SERIES[i % 8]} radius={[0, 4, 4, 0]} maxBarSize={22}
                 label={i === 0 ? { position: "right", fill: "var(--text-secondary)", fontSize: 11, formatter: (v: any) => compact(v) } : undefined} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (type === "pie" || type === "donut") {
    const y = ys[0];
    const total = rows.reduce((s, r) => s + (Number(r[y]) || 0), 0);
    return (
      <div className="flex flex-col items-center">
        <ResponsiveContainer width="100%" height={height - 50}>
          <PieChart>
            <Pie data={rows} dataKey={y} nameKey={x} innerRadius={type === "donut" ? "58%" : 0} outerRadius="88%" paddingAngle={1}
                 stroke="var(--surface-1)" strokeWidth={2} isAnimationActive={false}>
              {rows.map((_, i) => <Cell key={i} fill={i < 8 ? SERIES[i] : MUTED} />)}
            </Pie>
            <Tooltip content={({ active, payload }: any) =>
              active && payload?.length ? (
                <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
                  <div className="font-medium text-ink">{String(payload[0].name)}</div>
                  <div className="tabular text-ink2">{full(payload[0].value)} · {total ? ((payload[0].value / total) * 100).toFixed(1) : 0}%</div>
                </div>
              ) : null} />
          </PieChart>
        </ResponsiveContainer>
        <div className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-ink2">
          {rows.slice(0, 8).map((r, i) => (
            <span key={i} className="inline-flex items-center gap-1">
              <span className="h-2 w-2 rounded-full" style={{ background: SERIES[i] }} />
              {String(r[x])} <span className="tabular text-muted">{total ? ((Number(r[y]) / total) * 100).toFixed(0) : 0}%</span>
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (type === "scatter") {
    const yk = ys[0];
    const color: string | undefined = data.color;
    let groups: { name: string; points: any[]; fill: string }[];
    if (color) {
      const counts: Record<string, number> = {};
      rows.forEach((r) => (counts[String(r[color])] = (counts[String(r[color])] ?? 0) + 1));
      // scatter shows all colors at once: only the first three slots are safe all-pairs, fold the rest
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k]) => k);
      const keyOf = (r: any) => (top.includes(String(r[color])) ? String(r[color]) : "Other");
      const names = [...top, ...(Object.keys(counts).length > 3 ? ["Other"] : [])];
      groups = names.map((n, i) => ({ name: n, points: rows.filter((r) => keyOf(r) === n), fill: n === "Other" ? MUTED : SERIES[i] }));
    } else groups = [{ name: yk, points: rows, fill: SERIES[0] }];
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis type="number" dataKey={x} name={x} {...axisProps} tickFormatter={fmtY} domain={["auto", "auto"]} />
          <YAxis type="number" dataKey={yk} name={yk} {...axisProps} axisLine={false} tickFormatter={fmtY} width={52} domain={["auto", "auto"]} />
          <ZAxis range={[28, 28]} />
          <Tooltip cursor={{ strokeDasharray: "3 3", stroke: "var(--axis)" }} content={({ active, payload }: any) =>
            active && payload?.length ? (
              <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
                {color && <div className="mb-1 font-medium text-ink">{String(payload[0].payload[color])}</div>}
                <div className="text-ink2">{label(x)}: <b className="tabular text-ink">{full(payload[0].payload[x])}</b></div>
                <div className="text-ink2">{label(yk)}: <b className="tabular text-ink">{full(payload[0].payload[yk])}</b></div>
              </div>
            ) : null} />
          {groups.length > 1 && <Legend wrapperStyle={legendStyle} iconType="circle" iconSize={8} />}
          {groups.map((g) => <Scatter key={g.name} name={g.name} data={g.points} fill={g.fill} fillOpacity={0.7} stroke="var(--surface-1)" strokeWidth={1} />)}
        </ScatterChart>
      </ResponsiveContainer>
    );
  }
  return <div className="text-sm text-muted">Unsupported chart type: {type}</div>;
}

export function Kpi({ data, format }: { data: any; format: string }) {
  const chg: number | null | undefined = data.change_pct;
  const spark: (number | null)[] = data.sparkline ?? [];
  const up = (chg ?? 0) > 0;
  const good = up !== !!data.lower_is_better;
  return (
    <div className="flex h-full flex-col justify-between">
      <div className="text-[28px] font-semibold leading-tight tracking-tight text-ink" title={full(data.value)}>{compact(data.value, format)}</div>
      <div className="mt-2 flex items-end justify-between gap-2">
        {chg !== undefined && chg !== null ? (
          <div className="text-xs text-muted">
            <span className={"inline-flex items-center gap-0.5 font-medium " + (Math.abs(chg) < 0.05 ? "text-ink2" : good ? "text-[var(--delta-good)]" : "text-critical")}>
              {Math.abs(chg) < 0.05 ? <Minus className="h-3 w-3" /> : up ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
              {Math.abs(chg).toFixed(1)}%
            </span>{" "}
            vs prior month
          </div>
        ) : <span />}
        {spark.length > 2 && <Sparkline values={spark} />}
      </div>
    </div>
  );
}

export function Sparkline({ values, w = 84, h = 26 }: { values: (number | null)[]; w?: number; h?: number }) {
  const v = values.map((x) => x ?? 0);
  const min = Math.min(...v), max = Math.max(...v);
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - 2 - ((x - min) / (max - min || 1)) * (h - 4)}`).join(" ");
  return (
    <svg width={w} height={h} className="shrink-0" aria-hidden>
      <polyline points={pts} fill="none" stroke="var(--series-1)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function DataTable({ columns, rows, maxHeight = 340 }: { columns: string[]; rows: Record<string, any>[]; maxHeight?: number }) {
  return (
    <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-surface2">
          <tr>{columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 font-medium text-ink2">{label(c)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line hover:bg-surface2">
              {columns.map((c) => (
                <td key={c} className={"whitespace-nowrap px-3 py-1.5 " + (typeof r[c] === "number" ? "tabular text-right" : "")}>{full(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
