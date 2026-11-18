import { useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { useFetch } from "../../hooks";
import type { Dataset } from "../../types";
import { Card, Empty, ErrorBox, Select, Spinner, Stat } from "../../components/ui";
import ChartRenderer from "../../components/charts/ChartRenderer";
import { compact, dateLabel, full, label } from "../../format";

export default function TrendsTab({ ds }: { ds: Dataset }) {
  const p = ds.profile!;
  const [measure, setMeasure] = useState(p.primary_measure ?? "");
  const [grain, setGrain] = useState("");
  const [agg, setAgg] = useState("");
  const [horizon, setHorizon] = useState("");
  const [time, setTime] = useState(p.primary_time ?? "");
  const qs = new URLSearchParams();
  if (measure) qs.set("measure", measure);
  if (grain) qs.set("grain", grain);
  if (agg) qs.set("agg", agg);
  if (horizon) qs.set("horizon", horizon);
  if (time) qs.set("time_column", time);
  const { data: t, loading, error } = useFetch<any>(`/api/datasets/${ds.id}/analysis/trends?${qs}`);

  if (!p.primary_time) return <Empty title="No date column detected">Trend analysis and forecasting need a date/time column.</Empty>;
  const g = t?.grain;
  const rows = (t?.points ?? []).map((pt: any) => ({ ...pt, band: pt.lower !== undefined ? [pt.lower, pt.upper] : undefined }));
  const lastActual = [...rows].reverse().find((r: any) => r.actual !== undefined);
  if (lastActual) lastActual.forecast = lastActual.actual; // connect forecast line to the history
  const dir = t?.trend?.direction ?? "";
  const DirIcon = dir.startsWith("upward") ? TrendingUp : dir.startsWith("downward") ? TrendingDown : Minus;

  return (
    <div className="space-y-5">
      <div className="no-print flex flex-wrap gap-2">
        <Select value={measure} onChange={(e) => setMeasure(e.target.value)}><option value="">Record count</option>{p.measures.map((m) => <option key={m} value={m}>{label(m)}</option>)}</Select>
        <Select value={agg} onChange={(e) => setAgg(e.target.value)}><option value="">Auto aggregation</option>{["sum", "avg", "count", "min", "max"].map((a) => <option key={a}>{a}</option>)}</Select>
        <Select value={grain} onChange={(e) => setGrain(e.target.value)}><option value="">Auto grain</option>{["day", "week", "month", "quarter", "year"].map((a) => <option key={a}>{a}</option>)}</Select>
        <Select value={horizon} onChange={(e) => setHorizon(e.target.value)}><option value="">Default horizon</option>{[3, 6, 12, 24].map((h) => <option key={h} value={h}>{h} periods ahead</option>)}</Select>
        {p.time_columns.length > 1 && <Select value={time} onChange={(e) => setTime(e.target.value)}>{p.time_columns.map((c) => <option key={c} value={c}>{label(c)}</option>)}</Select>}
      </div>
      {loading && !t ? <Spinner /> : error ? <ErrorBox>{error}</ErrorBox> : !t?.available ? <Empty title="Trend unavailable">{t?.reason}</Empty> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Trend" value={<span className="flex items-center gap-1.5 text-lg"><DirIcon className="h-5 w-5" />{dir.split(" ")[0]}</span>} sub={`${t.trend.slope_pct_of_mean > 0 ? "+" : ""}${t.trend.slope_pct_of_mean}% of mean / ${g} · R² ${t.trend.r2}`} />
            <Stat label="Total change" value={t.growth.total_change_pct !== null ? `${t.growth.total_change_pct > 0 ? "+" : ""}${t.growth.total_change_pct}%` : "–"} sub={`${compact(t.growth.first)} → ${compact(t.growth.last)}`} />
            <Stat label={`Last ${g} vs previous`} value={t.growth.last_change_pct !== null ? `${t.growth.last_change_pct > 0 ? "+" : ""}${t.growth.last_change_pct}%` : "–"} sub={t.last_period_partial ? "latest partial period excluded" : "complete periods"} />
            <Stat label="Peak" value={compact(t.growth.peak_value)} sub={dateLabel(t.growth.peak_period, g)} />
            <Stat label="Forecast accuracy" value={t.forecast.mape !== null ? `${(100 - t.forecast.mape).toFixed(1)}%` : "–"} sub={`backtest MAPE ${t.forecast.mape ?? "–"}%`} />
          </div>
          <Card title={`${label(t.measure)} (${t.agg}) by ${g} with ${t.forecast.horizon}-${g} forecast`} subtitle={`${t.forecast.method} · shaded band = 95% prediction interval · dots = detected anomalies`}>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="period" stroke="var(--axis)" tickLine={false} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickFormatter={(v) => dateLabel(v, g)} minTickGap={24} />
                <YAxis stroke="var(--axis)" axisLine={false} tickLine={false} tick={{ fill: "var(--text-muted)", fontSize: 11 }} tickFormatter={(v) => compact(v)} width={56} />
                <Tooltip content={({ active, payload, label: l }: any) => active && payload?.length ? (
                  <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
                    <div className="mb-1 font-medium">{dateLabel(l, g)}</div>
                    {payload[0].payload.actual !== undefined && <div className="text-ink2">Actual: <b className="tabular text-ink">{full(payload[0].payload.actual)}</b></div>}
                    {payload[0].payload.fitted !== undefined && <div className="text-ink2">Model fit: <b className="tabular text-ink">{full(payload[0].payload.fitted)}</b></div>}
                    {payload[0].payload.lower !== undefined && <>
                      <div className="text-ink2">Forecast: <b className="tabular text-ink">{full(payload[0].payload.forecast)}</b></div>
                      <div className="text-muted">95% range {compact(payload[0].payload.lower)} – {compact(payload[0].payload.upper)}</div>
                    </>}
                  </div>) : null} />
                <Legend wrapperStyle={{ fontSize: 11 }} iconType="plainline" />
                <Area dataKey="band" name="Prediction interval" fill="var(--series-1)" fillOpacity={0.12} stroke="none" isAnimationActive={false} legendType="square" />
                <Line dataKey="fitted" name="Model fit" stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="2 3" dot={false} isAnimationActive={false} />
                <Line dataKey="actual" name="Actual" stroke="var(--series-1)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                <Line dataKey="forecast" name="Forecast" stroke="var(--series-1)" strokeWidth={2} strokeDasharray="6 4" dot={false} />
                {t.anomalies.map((a: any) => (
                  <ReferenceDot key={a.period} x={a.period} y={a.value} r={5} fill="var(--status-critical)" stroke="var(--surface-1)" strokeWidth={2} />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Seasonality profile" subtitle={t.seasonality ? (t.seasonality.detected ? `Detected – peak ${t.seasonality.peak}, trough ${t.seasonality.trough} (strength ${(t.seasonality.strength * 100).toFixed(0)}%)` : "No strong seasonal pattern") : "Needs at least two full cycles of data"}>
              {t.seasonality ? <ChartRenderer type="bar" height={220} data={{ x: "period", y: ["value"], rows: t.seasonality.profile }} /> : <Empty title="Not enough history" />}
            </Card>
            <Card title="Unusual periods" subtitle="Robust z-score > 3.5 versus rolling median">
              {t.anomalies.length === 0 ? <Empty title="No unusual periods detected" /> : (
                <div className="space-y-2">
                  {t.anomalies.map((a: any) => (
                    <div key={a.period} className="flex items-center justify-between rounded-lg bg-surface2 px-3 py-2 text-sm">
                      <span>{dateLabel(a.period, g)} <span className="text-xs text-muted">({a.type})</span></span>
                      <span className="tabular text-xs">{compact(a.value)} vs expected {compact(a.expected)} · z {a.score}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
