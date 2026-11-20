export type User = { id: number; name: string; email: string; created_at: string };

export type ColumnProfile = {
  name: string;
  dtype: string;
  semantic_type: string;
  role: "measure" | "dimension" | "time" | "identifier" | "text";
  missing: number;
  missing_pct: number;
  unique: number;
  unique_pct: number;
  sample_values: string[];
  stats?: Record<string, number | string | null>;
  top_values?: { value: string; count: number }[];
  default_agg?: string;
};

export type Profile = {
  columns: ColumnProfile[];
  measures: string[];
  dimensions: string[];
  time_columns: string[];
  identifiers: string[];
  primary_time: string | null;
  primary_measure: string | null;
  timings?: Record<string, number>;
};

export type Quality = {
  score_before: number;
  score_after: number;
  dimensions_before: Record<string, number>;
  dimensions_after: Record<string, number>;
  raw_rows: number;
  clean_rows: number;
  raw_missing_cells: number;
  clean_missing_cells: number;
  duplicate_rows: number;
  issues: Record<string, number>;
  per_column: { column: string; missing: number; missing_pct: number }[];
  grade: string;
};

export type Dataset = {
  id: number;
  name: string;
  description: string;
  table_name: string;
  source_type: "file" | "sql" | "api" | "join";
  source_config: Record<string, unknown>;
  status: string;
  row_count: number;
  column_count: number;
  quality_score: number | null;
  quality_before: number | null;
  refresh_interval_minutes: number;
  last_refreshed: string | null;
  created_at: string;
  primary_time: string | null;
  primary_measure: string | null;
  etl_options: Record<string, unknown>;
  profile?: Profile;
  quality?: Quality;
};

export type ETLStep = { step: string; description: string; affected: number; details: unknown };
export type ETLRun = {
  id: number;
  dataset_id: number;
  dataset_name?: string;
  trigger: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_s: number | null;
  rows_extracted: number;
  rows_loaded: number;
  error: string | null;
  steps?: ETLStep[];
};

export type Filter = { column: string; op: string; value: unknown };

export type WidgetType =
  | "kpi" | "line" | "area" | "bar" | "hbar" | "stacked_bar" | "pie" | "donut"
  | "scatter" | "histogram" | "heatmap" | "table" | "section";

export type Widget = {
  id: string;
  type: WidgetType;
  title: string;
  w: number;
  spec: Record<string, any>;
  /** combined dashboards: the dataset this widget reads from (defaults to the dashboard's dataset) */
  dataset_id?: number;
};

export type Source = { datasetId: number; name: string; profile: Profile };

export type Dashboard = {
  id: number;
  name: string;
  description: string;
  dataset_id: number;
  dataset_ids: number[];
  combined: boolean;
  dataset_name: string | null;
  widgets: Widget[];
  filters: Filter[];
  is_auto: boolean;
  created_at: string;
  updated_at: string;
};

export type ChartResult = {
  x: string | null;
  y: string[];
  series?: string | null;
  is_time?: boolean;
  rows: Record<string, any>[];
  sql?: string;
  columns?: string[];
};

export type Insight = {
  type: string;
  severity: "positive" | "negative" | "warning" | "info";
  title: string;
  description: string;
  recommendation: string;
  score: number;
  metric: string | null;
  value: unknown;
};
