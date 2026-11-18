# InsightFlow AI: Architecture & Design

## 1. System overview

InsightFlow AI is a three-tier web application:

1. **Presentation tier**: a React single-page application (TypeScript, Tailwind, Recharts).
2. **Application tier**: a FastAPI service containing the ETL engine, the analytics/ML engine, the insight engine and the natural-language query engine.
3. **Data tier**:
   - **DuckDB** analytical warehouse (columnar, in-process OLAP) for the business data.
   - **SQLAlchemy metadata store** (SQLite by default, PostgreSQL-ready) for users, the dataset catalog, ETL run history and dashboards.
   - A file store for uploaded source files (`data/uploads`), so file-based sources can be refreshed later.

```
 Browser (React SPA) ──HTTPS/JSON──► FastAPI routers ──► services / ETL / analytics
                                          │                     │
                                          ▼                     ▼
                              Metadata DB (SQLAlchemy)   DuckDB warehouse
                              users · datasets ·         stg_* · dw_* · mart_* · dim_date
                              etl_runs · dashboards
```

## 2. Data warehouse design

| Layer | Naming | Content | Purpose |
|---|---|---|---|
| Staging | `stg_<dataset>` | Raw extracted data, every column as text, plus `_loaded_at` | Auditability: the exact source snapshot of the last load |
| Core | `dw_<dataset>` | Cleaned, typed, de-duplicated, conformed data | Single source of truth for all analytics |
| Marts | `mart_<dataset>_monthly`, `mart_<dataset>_by_<dim>` | Views with pre-defined aggregates (records, sum/avg of top measures) | Fast, reusable KPI queries |
| Dimension | `dim_date` | Conformed calendar (year, quarter, month, week, weekday, weekend flag, year-month) that grows to cover all loaded dates | Time intelligence across every dataset |
| Integrated | `dw_<name>` built with `source_type = join` | Denormalised fact + dimensions (for example *Sales 360* = orders ⋈ products ⋈ customers) | Cross-source analysis |

The join SQL of an integrated dataset is stored in its catalog entry, so refreshing it rebuilds it from the current core tables.

**Security of the warehouse connection**: after start-up the DuckDB database is configured with `enable_external_access = false` and `lock_configuration = true`, so SQL (from users or the AI) cannot read or write files on the server, even if it got past the SQL guard.

## 3. ETL pipeline

`app/etl/pipeline.py::run_etl` orchestrates each run. Every run creates an `ETLRun` record holding a step-by-step log.

| # | Step | Details |
|---|---|---|
| 1 | **Extract** | Files (CSV with delimiter sniffing and encoding fallback, Excel with one dataset per sheet, JSON records/envelopes/JSON-lines, Parquet), SQL (any SQLAlchemy URL; only SELECT queries or whole tables), REST (JSON with an optional dot-path to the records array, or CSV) |
| 2 | Standardise names | `Order Date` → `order_date`, `customerID` → `customer_id`, uniqueness enforced |
| 3 | Clean text | Trim and collapse whitespace; `NA`, `N/A`, `null`, `-`, `?`, `#N/A` … → missing |
| 4 | Drop empty | Fully empty rows and columns |
| 5 | Fix types | Booleans (`yes/no/true/false`); numbers including `$ € £ ₹ ¥`, thousands separators, `%`, `(123)` negatives; dates in mixed formats. A column is converted when ≥ 90 % of non-null values parse, and the remaining values are counted as invalid. Integers become nullable `Int64` |
| 6 | De-duplicate | Exact duplicate rows |
| 7 | Normalise categories | Groups case- and whitespace-insensitive variants and maps each group to its most frequent spelling |
| 8 | Drop sparse | Columns with more than 95 % missing values |
| 9 | Outliers | Flags (or optionally caps) values beyond Q1 − 3·IQR / Q3 + 3·IQR |
| 10 | Impute | Numeric → median; categorical → `Unknown`; boolean → mode. Dates are never invented |
| 11 | Profile | Semantic types, roles, statistics, quality score |
| 12 | **Load** | Staging table, core table, mart views, date dimension |

Each step can be switched on or off per dataset (`etl_options`).

### Data quality score
`score = 100 × (0.35·completeness + 0.25·uniqueness + 0.25·validity + 0.15·consistency)`. It is computed on the raw data (with null placeholders counted as missing) and again on the cleaned data, and both are shown side by side.

### Scheduling
`app/scheduler.py` runs a daemon thread that checks every 60 seconds for datasets whose `refresh_interval_minutes` has passed and re-runs their ETL (trigger = `schedule`).

## 4. Schema understanding

`app/etl/profile.py::infer_semantic` combines **name heuristics** with **value statistics**:

- datetime dtype → `datetime` / role `time`; integer columns named like a year, with values from 1900 to 2100 → `year`
- numeric + id-like name (`*_id`, `code`, `sku` …) + high cardinality → `identifier`
- numeric 0/1 → `boolean`; names containing rate/percent/margin → `percentage`; money names → `currency`; qty/count names → `count`; otherwise → `numeric` (role `measure`)
- text: email pattern → `email`; geographic names → `geo`; low cardinality → `categorical`; long values → `text`; near-unique short values → `identifier`

Each measure also gets a **default aggregation**: `avg` for rates, prices, scores and durations, `sum` otherwise. The primary measure is chosen by business-keyword priority (revenue, sales, profit …). The primary time column is the densest date column.

## 5. Relationship discovery

For every pair of key-like columns (A.x, B.y) in two datasets owned by the user:
1. B.y must look like a primary key (unique and complete in B).
2. Column names must be similar (SequenceMatcher ≥ 0.6), or both columns must be identifiers.
3. `containment = |distinct(A.x) ∩ distinct(B.y)| / |distinct(A.x)|` must be ≥ 0.5.
4. `confidence = 0.7·containment + 0.3·name_similarity`. Cardinality is one-to-one if A.x is also unique, otherwise many-to-one. Orphan keys are counted.

Links between a joined dataset and the datasets it was built from are excluded.

## 6. Analytics engine

| Module | Technique |
|---|---|
| `query.py` | Declarative chart spec `{x, y:[{column, agg}], series, time_grain, filters, sort, limit}` is validated against the schema and compiled to **parameterised** DuckDB SQL (`date_trunc` for time grains, positional GROUP BY, and a pivot for series, keeping the top 8 by total). KPIs compare the last two complete periods. |
| `stats.py` | Histograms (√n rule, 5–24 bins), categorical frequencies, Pearson/Spearman matrices with p-values and strength labels, scatter with OLS regression. Reservoir sampling above 200k rows. |
| `trends.py` | Automatic grain from the date span; gaps filled; a partial last period detected and excluded; linear regression trend with significance test (p < 0.05); seasonality profile and strength (coefficient of variation of the seasonal means); **additive damped Holt-Winters** whose α, β, γ are chosen by grid search on one-step-ahead SSE, with prediction intervals of ±1.96·σ·√h and in-sample MAPE; period anomalies from a robust z-score (MAD) against a rolling median. |
| `ml.py` | **Isolation Forest** (200 trees) on standardised measures, with per-record attribution from the top z-scores. **Random Forest** regressor key drivers, using numeric features, one-hot categories and calendar features, with importances grouped back to the original columns. Measures with \|r\| ≥ 0.7 to the target are excluded as likely components of it. **K-Means** with k from 2 to 6 chosen by silhouette score, segment profiles relative to the overall mean, and a 2-D PCA (SVD) projection. |
| `dashboard.py` | Rule-based chart selection: 4 KPI cards, an area trend of the primary measure, a share donut (only for additive measures), a secondary trend, a stacked bar by quarter, bar or horizontal bar charts for the top dimensions (horizontal when there are more than 6 categories), a histogram, a scatter of the most informative correlated pair (0.3 ≤ \|r\| < 0.95), a correlation heatmap and a top-N table. |
| `insights.py` | Turns findings into ranked insight objects `{type, severity, title, description, recommendation, score}`. Covers trend direction (with a lower-is-better rule for costs, delays and similar measures), large recent changes, seasonality, forecasts, period anomalies, concentration and Pareto share, segment movers (last 3 complete months vs the previous 3), significant correlations, the top key driver, record anomalies and data quality. Also produces an executive summary and action plan. |
| `nlq.py` | Rule-based semantic parser: aggregation words, time-grain phrases, top/bottom N, column mentions (exact, synonyms, fuzzy matching), "by/per/for each" grouping, literal category values and years used as filters. The parsed question goes through the same chart engine. When Sarvam AI is configured: schema + question → JSON `{sql, chart, x, y, explanation}` → SQL guard → run on DuckDB → narrated answer. It falls back to the rules engine on any failure. |

## 7. Generative AI integration (optional)

`app/ai/llm.py` wraps the official Sarvam AI SDK (`sarvamai`, model `sarvam-105b` via `POST /v1/chat/completions`, `api-subscription-key` header, low/medium `reasoning_effort`, temperature 0.2). Only the final answer (`message.content`) is used; the model's separate `reasoning_content` and any inline `<think>` blocks are discarded. Design principles:
- **Optional and fault-tolerant**: every call returns `None` on error, refusal or missing credentials, and callers fall back to the deterministic engine.
- **Data minimisation**: only computed findings or schema metadata (column names, types, three sample values) are sent. Full datasets are never sent.
- **No trust in model output**: generated SQL must pass `sqlguard.validate_select` and is then run on a connection with no file access, wrapped in `LIMIT 1000`.

## 8. Metadata schema

```
users(id, email UNIQUE, name, password_hash, created_at)
datasets(id, owner_id→users, name, description, table_name UNIQUE, source_type, source_config JSON,
         etl_options JSON, row_count, column_count, profile JSON, quality JSON, status,
         refresh_interval_minutes, last_refreshed, created_at, updated_at)
etl_runs(id, dataset_id→datasets, trigger, status, started_at, finished_at, rows_extracted,
         rows_loaded, steps JSON, error)
dashboards(id, owner_id→users, dataset_id→datasets, name, description, widgets JSON, filters JSON,
           is_auto, created_at, updated_at)
```

## 9. Security

- Passwords: PBKDF2-HMAC-SHA256 with 240,000 iterations and a per-user salt. Sessions use HS256 JWTs (24 h).
- Every dataset and dashboard endpoint checks ownership and returns 404 for other users' resources.
- All chart and filter queries are parameterised, and identifiers are validated against the profiled schema and quoted.
- The SQL console and AI SQL accept a single SELECT/WITH statement only. DDL/DML, `PRAGMA`, `COPY`, `ATTACH`, `INSTALL`, system catalogs, file functions and other users' tables are rejected, and file access is also blocked inside DuckDB itself.
- Database connection passwords and API headers are redacted in API responses.
- Uploads have a size limit and an extension whitelist, and are stored under random file names.

## 10. Frontend design

- The design tokens in `index.css` define one validated, colour-blind-safe categorical palette (8 fixed-order slots), a sequential ramp, a diverging red↔gray↔blue scale for correlations, status colours, and separately tuned light and dark modes.
- Charts follow consistent rules: 2 px lines, rounded bar ends, recessive grid, crosshair or hover tooltips everywhere, a legend whenever there are 2 or more series, at most three colours plus "Other" on scatter plots, a table view and SQL view for every widget, and no dual axes.
- Global dashboard filters (date range with presets plus multi-select dimensions) are sent with every widget request, so all charts update together.
