import { useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Database, FileUp, Globe, Settings2, UploadCloud } from "lucide-react";
import { api, errMsg } from "../api";
import type { Dataset, ETLRun } from "../types";
import { Badge, Button, Card, ErrorBox, Field, Input, PageHeader, Select, Tabs, cx } from "../components/ui";

const OPTION_LABELS: Record<string, string> = {
  standardize_names: "Standardize column names",
  trim_whitespace: "Trim whitespace & null placeholders",
  fix_types: "Detect & convert data types",
  remove_duplicates: "Remove duplicate rows",
  normalize_categories: "Unify inconsistent category labels",
  impute_missing: "Fill missing values",
  drop_sparse_columns: "Drop near-empty columns",
  cap_outliers: "Cap extreme outliers",
};
const DEFAULTS: Record<string, boolean> = { standardize_names: true, trim_whitespace: true, fix_types: true, remove_duplicates: true,
  normalize_categories: true, impute_missing: true, drop_sparse_columns: true, cap_outliers: false };

function EtlOptions({ value, onChange }: { value: Record<string, boolean>; onChange: (v: Record<string, boolean>) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-line">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink2">
        <Settings2 className="h-4 w-4" /> ETL cleaning rules <span className="ml-auto text-xs text-muted">{Object.values(value).filter(Boolean).length} of {Object.keys(value).length} enabled</span>
      </button>
      {open && (
        <div className="grid gap-1.5 border-t border-line p-3 sm:grid-cols-2">
          {Object.keys(OPTION_LABELS).map((k) => (
            <label key={k} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={value[k]} onChange={(e) => onChange({ ...value, [k]: e.target.checked })} /> {OPTION_LABELS[k]}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function Result({ items }: { items: { dataset: Dataset; run: ETLRun }[] }) {
  const nav = useNavigate();
  return (
    <div className="mt-4 space-y-2">
      {items.map(({ dataset, run }) => (
        <div key={dataset.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface2 p-3">
          <CheckCircle2 className={cx("h-5 w-5", run.status === "success" ? "text-good" : "text-critical")} />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">{dataset.name}</div>
            <div className="text-xs text-muted">
              {run.status === "success"
                ? `${run.rows_extracted.toLocaleString()} rows extracted → ${run.rows_loaded.toLocaleString()} clean rows loaded · quality ${dataset.quality_before} → ${dataset.quality_score}`
                : run.error}
            </div>
          </div>
          {run.status === "success" && (
            <>
              <Button size="sm" onClick={() => nav(`/datasets/${dataset.id}`)}>Explore dataset</Button>
              <Button size="sm" variant="primary" onClick={() => nav(`/dashboards?dataset=${dataset.id}`)}>Open dashboard</Button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function FileUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [opts, setOpts] = useState(DEFAULTS);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any[] | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setName(f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
    setResult(null);
    setError(null);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    pick(e.dataTransfer.files?.[0]);
  };
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", name);
    fd.append("options", JSON.stringify(opts));
    try {
      const r = await api.post("/api/datasets/upload", fd, { onUploadProgress: (e) => setProgress(Math.round(((e.loaded ?? 0) / (e.total ?? 1)) * 100)) });
      setResult(r.data);
      setFile(null);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
      setProgress(0);
    }
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        className={cx("flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition", drag ? "border-accent bg-accentsoft" : "border-line hover:bg-surface2")}
      >
        <UploadCloud className="h-8 w-8 text-accent" />
        <div className="mt-2 text-sm font-medium">{file ? file.name : "Drop a file here or click to browse"}</div>
        <div className="mt-1 text-xs text-muted">{file ? `${(file.size / 1024).toFixed(1)} KB` : "CSV, TSV, Excel (.xlsx/.xls – every sheet becomes a dataset), JSON, Parquet"}</div>
        <input ref={input} type="file" className="hidden" accept=".csv,.tsv,.txt,.xlsx,.xls,.json,.parquet" onChange={(e) => pick(e.target.files?.[0])} />
      </div>
      {file && (
        <>
          <Field label="Dataset name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <EtlOptions value={opts} onChange={setOpts} />
          <Button variant="primary" onClick={upload} loading={busy} icon={<FileUp className="h-4 w-4" />}>
            {busy ? (progress < 100 ? `Uploading ${progress}%` : "Running ETL pipeline…") : "Upload & run ETL"}
          </Button>
        </>
      )}
      {error && <ErrorBox>{error}</ErrorBox>}
      {result && <Result items={result} />}
    </div>
  );
}

function SqlSource() {
  const [url, setUrl] = useState("demo");
  const [tables, setTables] = useState<string[] | null>(null);
  const [mode, setMode] = useState<"table" | "query">("table");
  const [table, setTable] = useState("");
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);

  const test = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.post("/api/datasets/sql/test", { connection_url: url });
      setTables(r.data.tables);
      setTable(r.data.tables[0] ?? "");
      if (!name && r.data.tables[0]) setName(r.data.tables[0]);
    } catch (e) { setError(errMsg(e)); setTables(null); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.post("/api/datasets/sql", { name, connection_url: url, table: mode === "table" ? table : null, query: mode === "query" ? query : null, refresh_interval_minutes: refresh });
      setResult(r.data);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <Field label="Connection URL (SQLAlchemy format)" hint="e.g. postgresql://user:pass@host:5432/db · mysql+pymysql://… · mssql+pyodbc://… · sqlite:///path.db — or type 'demo' for the bundled ERP database">
        <div className="flex gap-2">
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="postgresql://user:password@localhost:5432/sales" />
          <Button onClick={test} loading={busy && !tables}>Test connection</Button>
        </div>
      </Field>
      {tables && (
        <>
          <div className="flex items-center gap-2 text-sm"><Badge tone="good">Connected</Badge> <span className="text-muted">{tables.length} tables found</span></div>
          <div className="flex gap-2">
            {(["table", "query"] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)} className={cx("rounded-lg border px-3 py-1.5 text-xs", mode === m ? "border-accent bg-accentsoft text-accent" : "border-line text-ink2")}>
                {m === "table" ? "Import a table" : "Custom SQL query"}
              </button>
            ))}
          </div>
          {mode === "table" ? (
            <Field label="Table"><Select value={table} onChange={(e) => { setTable(e.target.value); setName(e.target.value); }} className="w-full">{tables.map((t) => <option key={t}>{t}</option>)}</Select></Field>
          ) : (
            <Field label="SELECT query"><textarea value={query} onChange={(e) => setQuery(e.target.value)} rows={4} className="w-full rounded-lg border border-line bg-surface p-2 font-mono text-xs text-ink outline-none focus:border-accent" placeholder="SELECT * FROM orders WHERE order_date >= '2024-01-01'" /></Field>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Dataset name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Automatic refresh">
              <Select value={refresh} onChange={(e) => setRefresh(Number(e.target.value))} className="w-full">
                <option value={0}>Manual only</option><option value={60}>Every hour</option><option value={360}>Every 6 hours</option><option value={1440}>Daily</option><option value={10080}>Weekly</option>
              </Select>
            </Field>
          </div>
          <Button variant="primary" onClick={save} loading={busy} disabled={!name}>Extract & load</Button>
        </>
      )}
      {error && <ErrorBox>{error}</ErrorBox>}
      {result && <Result items={[result]} />}
    </div>
  );
}

function ApiSource() {
  const [url, setUrl] = useState(`${location.origin}/api/demo-source/marketing`);
  const [path, setPath] = useState("data");
  const [name, setName] = useState("Marketing API");
  const [header, setHeader] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const save = async () => {
    setBusy(true); setError(null);
    const headers: Record<string, string> = {};
    if (header.includes(":")) headers[header.split(":")[0].trim()] = header.split(":").slice(1).join(":").trim();
    try {
      setResult((await api.post("/api/datasets/api", { name, url, record_path: path || null, headers, refresh_interval_minutes: refresh })).data);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <Field label="Endpoint URL" hint="Any HTTP(S) endpoint returning JSON records or CSV. The demo endpoint simulates a marketing platform."><Input value={url} onChange={(e) => setUrl(e.target.value)} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Records path (optional)" hint="Dot path to the array, e.g. data.items"><Input value={path} onChange={(e) => setPath(e.target.value)} /></Field>
        <Field label="Auth header (optional)" hint="Format → Header-Name: value"><Input value={header} onChange={(e) => setHeader(e.target.value)} placeholder="Authorization: Bearer …" /></Field>
        <Field label="Dataset name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Automatic refresh">
          <Select value={refresh} onChange={(e) => setRefresh(Number(e.target.value))} className="w-full">
            <option value={0}>Manual only</option><option value={15}>Every 15 minutes</option><option value={60}>Every hour</option><option value={1440}>Daily</option>
          </Select>
        </Field>
      </div>
      <Button variant="primary" onClick={save} loading={busy}>Fetch & load</Button>
      {error && <ErrorBox>{error}</ErrorBox>}
      {result && <Result items={[result]} />}
    </div>
  );
}

export default function Sources() {
  const [tab, setTab] = useState<"file" | "sql" | "api">("file");
  return (
    <div>
      <PageHeader title="Data Sources" subtitle="Bring data from anywhere – every source runs through the same automated ETL pipeline into the warehouse" icon={<UploadCloud className="h-5 w-5" />} />
      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        <Card>
          <Tabs value={tab} onChange={setTab} tabs={[
            { id: "file", label: "Upload file", icon: <FileUp className="h-4 w-4" /> },
            { id: "sql", label: "SQL database", icon: <Database className="h-4 w-4" /> },
            { id: "api", label: "REST API", icon: <Globe className="h-4 w-4" /> },
          ]} />
          <div className="pt-5">{tab === "file" ? <FileUpload /> : tab === "sql" ? <SqlSource /> : <ApiSource />}</div>
        </Card>
        <Card title="What happens next">
          <ol className="space-y-3 text-sm">
            {[
              ["Extract", "Data is read from the source and stored as-is in a staging table."],
              ["Transform", "Column names, types, formats, duplicates, inconsistent labels and missing values are fixed automatically – every step is logged."],
              ["Understand", "Each column gets a semantic type and role (measure, dimension, time, identifier); quality is scored."],
              ["Load", "Clean data lands in the core warehouse table with pre-aggregated marts and a shared date dimension."],
              ["Analyse", "A dashboard, statistics, forecasts, anomalies and insights are generated – ready to explore."],
            ].map(([t, d], i) => (
              <li key={t} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accentsoft text-xs font-semibold text-accent">{i + 1}</span>
                <div><div className="font-medium">{t}</div><div className="text-xs text-muted">{d}</div></div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
