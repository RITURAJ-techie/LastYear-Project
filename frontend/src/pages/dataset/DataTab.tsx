import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { api } from "../../api";
import type { Dataset } from "../../types";
import { Button, Input, Spinner, cx } from "../../components/ui";
import { full, label } from "../../format";

export default function DataTab({ ds }: { ds: Dataset }) {
  const [layer, setLayer] = useState<"core" | "staging">("core");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<string | null>(null);
  const [desc, setDesc] = useState(false);
  const [page, setPage] = useState(0);
  const [data, setData] = useState<{ columns: string[]; rows: any[]; total: number; table: string } | null>(null);
  const size = 50;
  useEffect(() => {
    const t = setTimeout(() => { setQ(search); setPage(0); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    const params = new URLSearchParams({ limit: String(size), offset: String(page * size), layer, desc: String(desc) });
    if (q) params.set("search", q);
    if (sort) params.set("sort", sort);
    api.get(`/api/datasets/${ds.id}/preview?${params}`).then((r) => setData(r.data));
  }, [ds.id, layer, q, sort, desc, page]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" />
          <Input className="pl-9" placeholder="Search all columns" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="flex rounded-lg border border-line p-0.5 text-xs">
          {(["core", "staging"] as const).map((l) => (
            <button key={l} onClick={() => { setLayer(l); setPage(0); setSort(null); }} className={cx("rounded-md px-3 py-1.5", layer === l ? "bg-accentsoft font-medium text-accent" : "text-ink2")}>
              {l === "core" ? "Clean (core layer)" : "Raw (staging layer)"}
            </button>
          ))}
        </div>
        {data && <span className="text-xs text-muted">{data.total.toLocaleString()} rows · table <span className="font-mono">{data.table}</span></span>}
        <div className="ml-auto flex items-center gap-1">
          <Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)} icon={<ChevronLeft className="h-3.5 w-3.5" />} />
          <span className="px-2 text-xs text-muted">Page {page + 1} of {data ? Math.max(1, Math.ceil(data.total / size)) : "–"}</span>
          <Button size="sm" disabled={!data || (page + 1) * size >= data.total} onClick={() => setPage(page + 1)} icon={<ChevronRight className="h-3.5 w-3.5" />} />
        </div>
      </div>
      {!data ? <Spinner /> : (
        <div className="max-h-[65vh] overflow-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-surface2">
              <tr>
                {data.columns.map((c) => (
                  <th key={c} className="cursor-pointer whitespace-nowrap px-3 py-2 text-left font-medium text-ink2 hover:text-ink"
                    onClick={() => { if (sort === c) setDesc(!desc); else { setSort(c); setDesc(false); } }}>
                    <span className="inline-flex items-center gap-1">{label(c)}{sort === c && (desc ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={i} className="border-t border-line hover:bg-surface2">
                  {data.columns.map((c) => <td key={c} className={cx("whitespace-nowrap px-3 py-1.5", typeof r[c] === "number" && "tabular text-right", r[c] === null && "text-muted")}>{r[c] === null ? "null" : full(r[c])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
