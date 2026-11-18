import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, BarChart3, Download, FileText, Lightbulb, LayoutDashboard, LineChart, RefreshCw, ShieldCheck, Table2, Target, TableProperties } from "lucide-react";
import { api, download, errMsg, openHtml } from "../api";
import { useFetch } from "../hooks";
import type { Dataset } from "../types";
import { Button, ErrorBox, PageHeader, SourceIcon, Spinner, Tabs } from "../components/ui";
import { timeAgo } from "../format";
import OverviewTab from "./dataset/OverviewTab";
import DataTab from "./dataset/DataTab";
import QualityTab from "./dataset/QualityTab";
import ExploreTab from "./dataset/ExploreTab";
import TrendsTab from "./dataset/TrendsTab";
import AnomaliesTab from "./dataset/AnomaliesTab";
import DriversTab from "./dataset/DriversTab";
import InsightsTab from "./dataset/InsightsTab";

type TabId = "insights" | "overview" | "data" | "quality" | "explore" | "trends" | "anomalies" | "drivers";

export default function DatasetDetail() {
  const id = Number(useParams().id);
  const { data: ds, loading, error, reload } = useFetch<Dataset>(`/api/datasets/${id}`);
  const [tab, setTab] = useState<TabId>("insights");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (loading && !ds) return <Spinner />;
  if (error || !ds) return <ErrorBox>{error ?? "Not found"}</ErrorBox>;

  const refresh = async () => {
    setBusy(true); setErr(null);
    try { await api.post(`/api/datasets/${id}/refresh`); await reload(); } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  const ready = ds.status === "ready" && ds.profile;
  const safe = ds.name.replace(/[^\w-]+/g, "_");

  return (
    <div>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-2">{ds.name} <SourceIcon type={ds.source_type} /></span>}
        subtitle={`${ds.row_count.toLocaleString()} rows · ${ds.column_count} columns · warehouse table ${ds.table_name} · refreshed ${timeAgo(ds.last_refreshed)}`}
        actions={
          <>
            <Button onClick={refresh} loading={busy} icon={<RefreshCw className="h-4 w-4" />}>Refresh</Button>
            <Button onClick={() => download(`/api/datasets/${id}/export?format=csv`, `${safe}.csv`)} icon={<Download className="h-4 w-4" />}>CSV</Button>
            <Button onClick={() => download(`/api/datasets/${id}/export?format=xlsx`, `${safe}.xlsx`)} icon={<Download className="h-4 w-4" />}>Excel</Button>
            <Button onClick={() => openHtml(`/api/datasets/${id}/analysis/report`)} icon={<FileText className="h-4 w-4" />}>Report</Button>
            <Link to={`/dashboards?dataset=${id}`}><Button variant="primary" icon={<LayoutDashboard className="h-4 w-4" />}>Dashboard</Button></Link>
          </>
        }
      />
      {err && <div className="mb-3"><ErrorBox>{err}</ErrorBox></div>}
      {!ready ? <ErrorBox>This dataset is {ds.status}. Check the ETL log under Quality & ETL.</ErrorBox> : (
        <>
          <Tabs value={tab} onChange={setTab} tabs={[
            { id: "insights", label: "Insights", icon: <Lightbulb className="h-4 w-4" /> },
            { id: "overview", label: "Schema & Profile", icon: <TableProperties className="h-4 w-4" /> },
            { id: "data", label: "Data", icon: <Table2 className="h-4 w-4" /> },
            { id: "quality", label: "Quality & ETL", icon: <ShieldCheck className="h-4 w-4" /> },
            { id: "explore", label: "Explore", icon: <BarChart3 className="h-4 w-4" /> },
            { id: "trends", label: "Trends & Forecast", icon: <LineChart className="h-4 w-4" /> },
            { id: "anomalies", label: "Anomalies", icon: <AlertTriangle className="h-4 w-4" /> },
            { id: "drivers", label: "Drivers & Segments", icon: <Target className="h-4 w-4" /> },
          ]} />
          <div className="pt-5">
            {tab === "insights" && <InsightsTab ds={ds} />}
            {tab === "overview" && <OverviewTab ds={ds} />}
            {tab === "data" && <DataTab ds={ds} />}
            {tab === "quality" && <QualityTab ds={ds} onChange={reload} />}
            {tab === "explore" && <ExploreTab ds={ds} />}
            {tab === "trends" && <TrendsTab ds={ds} />}
            {tab === "anomalies" && <AnomaliesTab ds={ds} />}
            {tab === "drivers" && <DriversTab ds={ds} />}
          </div>
        </>
      )}
    </div>
  );
}
