export function compact(v: unknown, kind: string = "number"): string {
  if (v === null || v === undefined || v === "") return "–";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const a = Math.abs(n);
  let s: string;
  if (a >= 1e9) s = (n / 1e9).toFixed(2) + "B";
  else if (a >= 1e6) s = (n / 1e6).toFixed(2) + "M";
  else if (a >= 1e4) s = (n / 1e3).toFixed(1) + "K";
  else if (Number.isInteger(n)) s = n.toLocaleString();
  else s = n.toLocaleString(undefined, { maximumFractionDigits: a < 1 ? 3 : 2 });
  if (kind === "currency") return "$" + s;
  if (kind === "percent") return s + "%";
  return s;
}

export function full(v: unknown): string {
  if (v === null || v === undefined) return "–";
  const n = Number(v);
  if (typeof v === "number" && Number.isFinite(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(v);
}

export function label(name: string | null | undefined): string {
  if (!name) return "";
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function dateLabel(v: unknown, grain?: string): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  const d = new Date(s.length <= 10 ? s + "T00:00:00" : s);
  if (isNaN(d.getTime())) return s;
  if (grain === "year") return String(d.getFullYear());
  if (grain === "quarter") return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`;
  if (grain === "day" || grain === "week") return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });
  return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
