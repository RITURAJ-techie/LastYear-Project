import { useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, Search, Table2, Trash2, UploadCloud } from "lucide-react";
import { api, errMsg } from "../api";
import { useFetch } from "../hooks";
import type { Dataset } from "../types";
import { Badge, Button, Empty, ErrorBox, Input, PageHeader, SourceIcon, Spinner, StatusBadge } from "../components/ui";
import { timeAgo } from "../format";

export default function Datasets() {
  const { data, loading, error, reload } = useFetch<Dataset[]>("/api/datasets");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = async (id: number, kind: "refresh" | "delete") => {
    if (kind === "delete" && !confirm("Delete this dataset, its warehouse tables and dashboards?")) return;
    setBusy(id); setErr(null);
    try {
      if (kind === "refresh") await api.post(`/api/datasets/${id}/refresh`);
      else await api.delete(`/api/datasets/${id}`);
      await reload();
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(null); }
  };
  const list = (data ?? []).filter((d) => d.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <PageHeader title="Datasets" subtitle="Every dataset is a cleaned, profiled table in the warehouse" icon={<Table2 className="h-5 w-5" />}
        actions={<Link to="/sources"><Button variant="primary" icon={<UploadCloud className="h-4 w-4" />}>Add data</Button></Link>} />
      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" />
        <Input className="pl-9" placeholder="Search datasets" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {err && <div className="mb-3"><ErrorBox>{err}</ErrorBox></div>}
      {loading ? <Spinner /> : error ? <ErrorBox>{error}</ErrorBox> : !list.length ? (
        <Empty icon={<Table2 className="h-8 w-8" />} title="No datasets">Upload a file or connect a source to create your first dataset.</Empty>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-surface2 text-left text-xs text-ink2">
              <tr>
                {["Dataset", "Source", "Rows", "Columns", "Quality", "Status", "Refreshed", ""].map((h) => <th key={h} className="whitespace-nowrap px-4 py-2.5 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {list.map((d) => (
                <tr key={d.id} className="border-t border-line hover:bg-surface2">
                  <td className="px-4 py-3">
                    <Link to={`/datasets/${d.id}`} className="font-medium text-ink hover:text-accent">{d.name}</Link>
                    <div className="max-w-xs truncate text-xs text-muted">{d.description || d.table_name}</div>
                  </td>
                  <td className="px-4 py-3"><SourceIcon type={d.source_type} /></td>
                  <td className="tabular px-4 py-3">{d.row_count.toLocaleString()}</td>
                  <td className="tabular px-4 py-3">{d.column_count}</td>
                  <td className="px-4 py-3">{d.quality_score !== null ? <Badge tone={d.quality_score >= 90 ? "good" : "warn"}>{d.quality_before} → {d.quality_score}</Badge> : "–"}</td>
                  <td className="px-4 py-3"><StatusBadge status={d.status} /></td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-muted">{timeAgo(d.last_refreshed)}{d.refresh_interval_minutes ? " · auto" : ""}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <Button size="sm" variant="ghost" loading={busy === d.id} onClick={() => act(d.id, "refresh")} icon={<RefreshCw className="h-3.5 w-3.5" />} title="Re-run ETL" />
                    <Button size="sm" variant="ghost" onClick={() => act(d.id, "delete")} icon={<Trash2 className="h-3.5 w-3.5" />} title="Delete" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
