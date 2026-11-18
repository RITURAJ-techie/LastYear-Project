import { useState } from "react";
import { label } from "../../format";

/** Correlation matrix: diverging red <-> gray <-> blue, value labels on strong cells. */
export default function Heatmap({ data }: { data: { columns: string[]; matrix: (number | null)[][] } }) {
  const [hover, setHover] = useState<{ a: string; b: string; r: number | null } | null>(null);
  const cols = data.columns ?? [];
  if (cols.length < 2) return <div className="py-8 text-center text-sm text-muted">Need at least two numeric columns</div>;
  const color = (r: number | null) => {
    if (r === null) return "var(--surface-2)";
    const pct = Math.round(Math.min(1, Math.abs(r)) * 100);
    return `color-mix(in srgb, ${r >= 0 ? "var(--div-pos)" : "var(--div-neg)"} ${pct}%, var(--div-mid))`;
  };
  return (
    <div>
      <div className="overflow-x-auto">
        <div className="grid gap-[2px]" style={{ gridTemplateColumns: `minmax(90px,auto) repeat(${cols.length}, minmax(30px,1fr))` }}>
          <div />
          {cols.map((c) => (
            <div key={c} className="truncate px-0.5 pb-1 text-center text-[10px] text-muted" title={label(c)}>{label(c)}</div>
          ))}
          {cols.map((a, i) => (
            <div key={a} className="contents">
              <div className="truncate pr-2 text-right text-[11px] leading-7 text-ink2" title={label(a)}>{label(a)}</div>
              {cols.map((b, j) => {
                const r = data.matrix[i]?.[j] ?? null;
                return (
                  <div
                    key={b}
                    className="flex h-7 items-center justify-center rounded-[3px] text-[10px] tabular"
                    style={{ background: color(r), color: r !== null && Math.abs(r) > 0.55 ? "#fff" : "var(--text-secondary)" }}
                    onMouseEnter={() => setHover({ a, b, r })}
                    onMouseLeave={() => setHover(null)}
                  >
                    {r !== null && Math.abs(r) >= 0.3 && i !== j ? r.toFixed(2) : ""}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between text-[11px] text-muted">
        <span className="flex items-center gap-2">
          −1
          <span className="h-2 w-28 rounded" style={{ background: "linear-gradient(90deg, var(--div-neg), var(--div-mid), var(--div-pos))" }} />
          +1
        </span>
        <span className="tabular">{hover ? `${label(hover.a)} × ${label(hover.b)}: r = ${hover.r?.toFixed(3) ?? "–"}` : "Hover a cell for details"}</span>
      </div>
    </div>
  );
}
