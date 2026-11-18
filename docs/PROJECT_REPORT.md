# Project Report

## InsightFlow AI: A Modern Data Warehouse–Driven Decision Support and Analytics Framework

---

### Abstract

Organisations generate large volumes of data in databases, spreadsheets and external applications. Because this data is fragmented, processed by hand, of inconsistent quality and served by limited reporting tools, timely and reliable insight is hard to get. Commercial BI tools such as Power BI help with visualisation, but they expect users to model data, write measures and design every report themselves.

This project presents **InsightFlow AI**, an integrated, automated analytics platform. It collects data from multiple sources (files, SQL databases and REST APIs), runs a fully logged ETL pipeline that cleans and standardises the data, and maintains a layered central data warehouse (staging, core, marts and a conformed date dimension). It then **understands the data on its own**: it infers semantic types, analytical roles and cross-dataset relationships. Finally it **generates** interactive dashboards, KPIs, trend analyses, forecasts, anomaly reports, key-driver analyses and ranked, plain-language recommendations. Users can also ask questions in natural language. An optional large-language-model layer (Anthropic Claude) adds executive narratives and free-form text-to-SQL, but every core feature works with the built-in statistical and machine-learning engine alone.

---

### 1. Introduction

Decision makers need consolidated, trustworthy and current information. In practice, data is copied between Excel files, quality problems (duplicates, inconsistent labels, wrongly typed values, missing data) are fixed by hand, and dashboards depend on a few specialists. InsightFlow AI automates the whole chain from raw source to recommended action, so that people without technical or analytical training can turn raw data into actionable information.

### 2. Problem statement

> Organizations generate large volumes of data across multiple sources, including databases, Excel/CSV files, and external applications. However, fragmented data, manual processing, inconsistent data quality, and limited reporting capabilities make it difficult to obtain timely and reliable business insights. The challenge is to develop an integrated, automated data analytics platform that collects data from multiple sources, performs ETL (Extract, Transform, Load), maintains a centralized data warehouse, and provides interactive dashboards, KPIs, trend analysis, and actionable insights to support faster and more informed business decisions.

### 3. Objectives

1. Ingest data from heterogeneous sources: CSV/Excel/JSON/Parquet files, relational databases and REST APIs.
2. Automate ETL with auditable cleaning, type conversion, de-duplication, standardisation and imputation, run on demand or on a schedule.
3. Maintain a centralised, layered data warehouse with a conformed date dimension and pre-aggregated marts.
4. Infer data structure (semantic types, roles) and relationships between datasets automatically.
5. Measure and report data quality before and after processing.
6. Generate interactive dashboards and KPIs automatically, and let users build their own (custom dashboards instead of Power BI).
7. Provide statistical analysis, trend detection, seasonality, forecasting, anomaly detection, key-driver analysis and segmentation.
8. Turn the analytical results into ranked, plain-language insights with recommended actions.
9. Answer natural-language questions with charts and transparent SQL.
10. Make the platform secure, multi-user, responsive and easy to deploy.

### 4. Existing systems and their limitations

| System | Limitations addressed by this project |
|---|---|
| Spreadsheets (Excel) | Manual consolidation, no automated cleaning, poor scalability, error-prone |
| Traditional BI (Power BI, Tableau) | Licensing cost; users must model data, write DAX or calculations and design every visual; insights are not generated for them; separate ETL tooling needed |
| Standalone ETL tools | No analytics or decision support layer |
| Notebook-based analysis (Python/R) | Requires programming skills; results are not interactive or shareable for business users |

### 5. Proposed system

InsightFlow AI combines ETL, data warehousing, analytics, machine learning and decision support in one web application:

- **Ingestion layer**: file upload, SQL connector, REST connector, all using the same pipeline.
- **ETL layer**: a 12-step logged pipeline, configurable per dataset, with scheduled refresh.
- **Warehouse layer**: DuckDB columnar engine with staging, core, mart and dimension layers, plus integrated (joined) datasets.
- **Intelligence layer**: schema inference, relationship discovery, quality scoring, statistics, forecasting, ML, an insight engine and a natural-language query engine.
- **Presentation layer**: React application with auto and custom dashboards, global filters, analysis tabs, an NL chat, a warehouse explorer, a SQL console and a pipeline monitor.

### 6. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Recharts, React Router |
| Backend API | Python, FastAPI, Uvicorn, Pydantic |
| Data warehouse | DuckDB (columnar OLAP) |
| Metadata store | SQLAlchemy ORM on SQLite (PostgreSQL-compatible) |
| Data processing | pandas, NumPy, SciPy |
| Machine learning | scikit-learn (Isolation Forest, Random Forest, K-Means), custom Holt-Winters |
| Connectors | SQLAlchemy, requests, openpyxl, pyarrow |
| Generative AI (optional) | Anthropic Claude via the official SDK |
| Security | JWT (PyJWT), PBKDF2 password hashing |
| Testing / DevOps | pytest, FastAPI TestClient, Docker, docker-compose |

### 7. System modules

1. **Authentication & user management**: registration, login, JWT sessions, per-user isolation.
2. **Data source management**: file upload (multi-sheet Excel), database connector (connection test, table or query import), REST API connector (records path, auth header), refresh schedules.
3. **ETL engine**: extract, transform (12 logged steps), profile, load. Records run history.
4. **Data warehouse management**: layered storage, mart views, date dimension, catalog browser, relationship ER diagram, join builder, read-only SQL console.
5. **Data profiling & quality**: semantic type and role inference, column statistics, a 4-dimension quality score before and after ETL.
6. **Dashboard module**: automatic generation, a chart builder with 12 widget types and live preview, layout editing, global filters, table/SQL view of every chart, print/PDF.
7. **Analytics module**: summary statistics, distributions, correlations, scatter/regression.
8. **Trend & forecast module**: trend significance, growth, seasonality, Holt-Winters forecast with confidence band, anomalous periods.
9. **Machine-learning module**: anomaly detection, key-driver analysis, segmentation.
10. **Insight & recommendation module**: ranked findings, recommendations, executive summary, action plan, HTML report.
11. **Natural-language query module**: semantic parser plus optional LLM text-to-SQL, with answers as chart, table and SQL, and pinning to dashboards.
12. **Monitoring**: overview KPIs, ETL pipeline monitor.

### 8. Key algorithms

**8.1 Type inference.** For each text column, try to parse it as boolean, then numeric (after removing currency symbols, separators and `%`, and handling parenthesised negatives), then date. Accept a type when at least 90 % of non-null values parse. Values that fail are counted as invalid and set to missing.

**8.2 Category normalisation.** Group values by `lower(collapse_whitespace(v))`. Each group is mapped to its most frequent original spelling.

**8.3 Data quality index.** `Q = 100·(0.35·C + 0.25·U + 0.25·V + 0.15·K)`, where C = completeness, U = row uniqueness, V = validity and K = consistency (1 − (inconsistent + reformatted values) / cells).

**8.4 Relationship discovery.** For key-like column pairs where the target column is unique, compute value containment and name similarity, then `confidence = 0.7·containment + 0.3·similarity`.

**8.5 Trend significance.** OLS slope over the period index, with H₀: slope = 0 rejected at p < 0.05. The slope is reported as a percentage of the mean per period.

**8.6 Seasonality strength.** The coefficient of variation of the per-season means (for example the 12 monthly means). A value above 0.08 counts as seasonal.

**8.7 Holt-Winters forecasting (additive, damped).**
```
ℓₜ = α(yₜ − sₜ₋ₘ) + (1 − α)(ℓₜ₋₁ + φbₜ₋₁)
bₜ = β(ℓₜ − ℓₜ₋₁) + (1 − β)φbₜ₋₁
sₜ = γ(yₜ − ℓₜ) + (1 − γ)sₜ₋ₘ
ŷₜ₊ₕ = ℓₜ + (φ + φ² + … + φʰ)bₜ + sₜ₊ₕ₋ₘ
```
α, β, γ are chosen by grid search to minimise one-step-ahead SSE (φ = 0.95). The 95 % interval is ±1.96·σ·√h. Accuracy is reported as MAPE.

**8.8 Anomaly detection.** An Isolation Forest isolates observations through random partitioning, and anomalies need fewer splits. The score is `s(x) = 2^(−E[h(x)]/c(n))`. Each flagged record is explained by its features with the largest absolute z-scores. Time-series anomalies use a robust z-score, `0.6745·(y − rolling_median)/MAD`, with a threshold of 3.5.

**8.9 Key-driver analysis.** A Random Forest regressor on numeric, one-hot categorical and calendar features. Impurity importances are summed back to the original columns. Measures with |r| ≥ 0.7 to the target are reported as components rather than drivers.

**8.10 Segmentation.** Standardise the measures and run K-Means for k = 2…6, choosing the k with the best silhouette score. Segments are described by their percentage deviation from the overall mean.

**8.11 Insight ranking.** Each rule produces an insight with a priority score: base weight × measure importance × magnitude. The top insights form the executive summary and action plan.

**8.12 Natural-language parsing.** Pattern lexicons cover aggregations and time grains. Columns are matched exactly, through a synonym table, and by fuzzy matching (difflib ratio ≥ 0.85). Grouping comes from "by/per/for each" phrases. Literal category values and years in the question become filters. The result is a chart spec that runs through the same safe query engine.

### 9. Database design

See [ARCHITECTURE.md §8](ARCHITECTURE.md#8-metadata-schema) for the metadata ER schema and §2 for the warehouse layer design.

### 10. Implementation highlights

- **One query engine for everything**: dashboards, the chart builder, KPIs and NL answers all compile through `analytics/query.py`, so behaviour and security checks are the same everywhere.
- **Same path for every source**: files, databases, APIs and warehouse joins produce a DataFrame that goes through the same transform, profile and load steps.
- **Caching**: expensive analytics are memoised per dataset version and invalidated automatically on each refresh.
- **Accessible visual design**: a validated colour-blind-safe palette, a light and a dark theme, table views of every chart and responsive layouts.

### 11. Testing

| Test area | Cases | Result |
|---|---|---|
| ETL cleaning | Name standardisation; currency, percent, negative and date parsing; boolean detection; de-duplication; category unification; imputation; step log | Pass |
| Profiling | Identifier, currency, categorical, geo, datetime and email inference; primary measure/time; quality score | Pass |
| Query engine | Monthly grain over 2 years (24 rows); quarterly series with a date filter; unknown-column rejection | Pass |
| Forecasting | Upward trend detected on synthetic seasonal data; 6-period horizon | Pass |
| Security | SQL guard blocks DROP, multiple statements, other tables, `read_csv`, `COPY`; DuckDB blocks file access; cross-user isolation (404 and SQL denial) | Pass |
| API end-to-end | Register → upload → ETL → 8 analyses → dashboard widgets with filters → NLQ → SQL → export → report → refresh → run history | Pass |
| SQL connector | SQLite source: list tables, import table | Pass |

The suite is run with `cd backend && pytest -q` (15 tests). The UI was also checked by hand across all pages in light mode, dark mode and at mobile width.

### 12. Results

On the bundled demo warehouse (four sources plus one integrated dataset, about 13,000 rows):
- ETL fixed **641 data issues**: 45 duplicates, 147 inconsistent labels, 255 badly formatted values, 64 null placeholders, 130 missing values and others. A full load of 6,000 orders takes about 1 second.
- Relationships `orders.customer_id → customers` and `orders.product_id → products` were discovered with 100 % confidence.
- Generated insights included statistically significant revenue growth (+130 %), an October seasonal peak, a July 2024 revenue dip (z = −4.1), declining segments (for example the Retail Store channel, −31 % quarter-on-quarter), unit price and quantity as the main revenue drivers, and a 6-month Holt-Winters forecast with 13 % backtest MAPE.
- All analysis endpoints respond in under 2 seconds.

### 13. Advantages

- No-code, end-to-end: from raw files to recommended actions.
- Transparent: every ETL step, chart query and NL answer shows what was done (logs and SQL).
- Low cost and self-hosted: open-source stack in a single container.
- Works fully offline from external AI. A generative AI layer can be added.

### 14. Limitations

- DuckDB runs in-process, so the API runs as a single worker. Very large multi-user deployments would move the warehouse to a server engine such as PostgreSQL, ClickHouse or Snowflake.
- The rule-based NL parser handles common business questions. Complex multi-step questions need the optional LLM.
- Forecasting is univariate (no external regressors).

### 15. Future enhancements

- Incremental (CDC) loads and slowly changing dimensions.
- Role-based sharing of dashboards and row-level security.
- Scheduled e-mail/Slack reports and KPI threshold alerts.
- More connectors (Google Sheets, Salesforce, S3/Azure Blob).
- Multivariate forecasting (Prophet/ARIMAX) and what-if simulation.
- Drag-and-drop dashboard layout and dashboard templates.

### 16. Conclusion

InsightFlow AI meets the problem statement in full. It consolidates data from multiple sources through an automated, auditable ETL pipeline into a centralised, layered data warehouse, and it turns that data into interactive dashboards, KPIs, trends, forecasts and actionable recommendations without manual modelling or report design. Built-in machine learning, an insight engine and natural-language querying make data-driven decisions available to non-technical users, which supports faster and more informed business decisions.

### References

1. Kimball, R., & Ross, M. *The Data Warehouse Toolkit* (3rd ed.). Wiley.
2. Hyndman, R. J., & Athanasopoulos, G. *Forecasting: Principles and Practice* (3rd ed.). OTexts.
3. Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation Forest. *IEEE ICDM*.
4. Breiman, L. (2001). Random Forests. *Machine Learning*, 45(1).
5. Raasveldt, M., & Mühleisen, H. (2019). DuckDB: an Embeddable Analytical Database. *SIGMOD*.
6. Pedregosa, F. et al. (2011). Scikit-learn: Machine Learning in Python. *JMLR* 12.
7. FastAPI documentation: https://fastapi.tiangolo.com
