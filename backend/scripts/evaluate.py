"""Reproducible experimental evaluation of InsightFlow AI.

Runs eight experiments on synthetic data with *known ground truth* (plus the bundled
demo data) and writes:
  docs/evaluation/results.json   – machine-readable results
  docs/evaluation/RESULTS.md     – tables ready to paste into a paper/report

Usage (from backend/):  python scripts/evaluate.py [--quick]
Fixed random seeds make every run reproducible on the same library versions.
"""
from __future__ import annotations

import io
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

TMP = tempfile.mkdtemp(prefix="insightflow-eval-")
os.environ["INSIGHTFLOW_DATA_DIR"] = TMP
os.environ["INSIGHTFLOW_AI_DISABLED"] = "true"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import IsolationForest  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from app import warehouse as wh  # noqa: E402
from app.analytics import insights, ml, nlq, query, relationships, stats, trends  # noqa: E402
from app.etl import extract  # noqa: E402
from app.etl.profile import infer_semantic, profile_dataframe, quality_report  # noqa: E402
from app.etl.transform import transform  # noqa: E402

QUICK = "--quick" in sys.argv
OUT = ROOT.parent / "docs" / "evaluation"
RESULTS: dict = {}


def timed(fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    return r, time.perf_counter() - t


def prf(pred: set, truth: set) -> dict:
    tp = len(pred & truth)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(truth) if truth else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "fp": len(pred - truth), "fn": len(truth - pred)}


# ---------------------------------------------------------------------------
# E1. Data-cleaning accuracy with injected, recorded faults
# ---------------------------------------------------------------------------
def e1_cleaning():
    rng = np.random.default_rng(11)
    n = 5000
    clean = pd.DataFrame({
        "record_id": [f"R{i:05d}" for i in range(n)],
        "order_date": pd.date_range("2022-01-01", periods=n, freq="4h").normalize(),
        "region": rng.choice(["North", "South", "East", "West"], n),
        "channel": rng.choice(["Online", "Retail Store", "Partner"], n),
        "quantity": rng.integers(1, 20, n),
        "unit_price": rng.uniform(5, 500, n).round(2),
        "is_member": rng.choice([True, False], n),
    })
    clean["revenue"] = (clean["quantity"] * clean["unit_price"]).round(2)
    raw = clean.copy()
    raw["order_date"] = raw["order_date"].dt.strftime("%Y-%m-%d")
    raw["is_member"] = np.where(clean["is_member"], "yes", "no")
    raw = raw.astype(object)
    idx = rng.permutation(n)
    take = lambda k: [idx.pop(0) for _ in range(k)] if isinstance(idx, list) else None  # noqa: E731
    idx = list(idx)
    truth = {}
    cur = take(300); raw.loc[cur, "revenue"] = [f"${v:,.2f}" for v in clean.loc[cur, "revenue"]]; truth["currency_strings"] = cur
    dfmt = take(300); raw.loc[dfmt, "order_date"] = clean.loc[dfmt, "order_date"].dt.strftime("%Y/%m/%d"); truth["alt_date_format"] = dfmt
    lab = take(400)
    variants = lambda v: rng.choice([v.lower(), v.upper(), f" {v} ", f"{v}  ", v.lower() + " "])  # noqa: E731
    raw.loc[lab, "region"] = [variants(v) for v in clean.loc[lab, "region"]]; truth["inconsistent_labels"] = lab
    nul = take(250); raw.loc[nul, "unit_price"] = rng.choice(["N/A", "null", "-", "", "NA"], len(nul)); truth["null_tokens"] = nul
    bad = take(50); raw.loc[bad, "quantity"] = rng.choice(["abc", "??", "ten"], len(bad)); truth["invalid_numbers"] = bad
    dup_rows = raw.iloc[rng.choice(n, 120, replace=False)]
    raw_full = pd.concat([raw, dup_rows]).sample(frac=1, random_state=3).reset_index(drop=True)
    raw_csv = raw_full.to_csv(index=False).encode()
    p = Path(TMP) / "e1.csv"
    p.write_bytes(raw_csv)
    raw_read = extract.read_file(p)["data"]

    res, secs = timed(transform, raw_read)
    noimp = transform(raw_read, {"impute_missing": False}).df.set_index("record_id")
    out = res.df.set_index("record_id").sort_index()
    ref = clean.set_index("record_id").sort_index()
    expected_types = {"order_date": "datetime", "region": "text", "channel": "text", "quantity": "numeric",
                      "unit_price": "numeric", "is_member": "boolean", "revenue": "numeric"}

    def kind(s):
        if pd.api.types.is_datetime64_any_dtype(s):
            return "datetime"
        if pd.api.types.is_bool_dtype(s):
            return "boolean"
        if pd.api.types.is_numeric_dtype(s):
            return "numeric"
        return "text"

    type_ok = sum(kind(out[c]) == t for c, t in expected_types.items())
    ids = lambda rows: clean.loc[rows, "record_id"].tolist()  # noqa: E731

    def acc(col, rows, tol=1e-6):
        a, b = out.loc[ids(rows), col], ref.loc[ids(rows), col]
        if pd.api.types.is_numeric_dtype(b) and not pd.api.types.is_bool_dtype(b):
            return float((np.abs(a.astype(float) - b.astype(float)) <= tol).mean())
        return float((a.astype(str) == b.astype(str)).mean())

    untouched = [i for i in range(n) if i in set(idx)]
    overall_cols = ["order_date", "region", "channel", "revenue", "is_member"]
    raw_match = np.mean([(raw.set_index("record_id").loc[ref.index, c].astype(str).values == ref[c].astype(str).values).mean()
                         for c in ["region", "revenue"]])
    r = {
        "rows_raw": int(len(raw_full)), "rows_clean": int(len(out)), "rows_true": n,
        "duplicates_injected": 120, "duplicates_removed": int(res.issues["duplicates_removed"]),
        "column_type_accuracy": f"{type_ok}/{len(expected_types)}",
        "currency_parse_accuracy": acc("revenue", truth["currency_strings"], 0.005),
        "date_format_accuracy": acc("order_date", truth["alt_date_format"]),
        "label_normalisation_accuracy": acc("region", truth["inconsistent_labels"]),
        "null_placeholder_recall": float(noimp.loc[ids(truth["null_tokens"]), "unit_price"].isna().mean()),
        "null_placeholder_false_positives": int(noimp["unit_price"].isna().sum() - noimp.loc[ids(truth["null_tokens"]), "unit_price"].isna().sum()),
        "invalid_number_recall": float(noimp.loc[ids(truth["invalid_numbers"]), "quantity"].isna().mean()),
        "invalid_number_false_positives": int(noimp["quantity"].isna().sum() - noimp.loc[ids(truth["invalid_numbers"]), "quantity"].isna().sum()),
        "imputed_values": int(res.issues["imputed_values"]),
        "untouched_cells_preserved": float(np.mean([acc(c, untouched[:2000], 0.005) for c in overall_cols])),
        "region_revenue_cell_match_before": round(float(raw_match), 4),
        "region_revenue_cell_match_after": round(float(np.mean([acc("region", list(range(n))), acc("revenue", list(range(n)), 0.005)])), 4),
        "transform_seconds": round(secs, 3),
        "quality_score_before_after": [quality_report(raw_read, res.df, res.issues)[k] for k in ("score_before", "score_after")],
    }
    RESULTS["E1_cleaning"] = r
    return r


# ---------------------------------------------------------------------------
# E2. Semantic type / analytical role inference
# ---------------------------------------------------------------------------
def e2_semantics():
    rng = np.random.default_rng(5)
    n = 1000
    S = lambda vals: pd.Series(vals, dtype="string")  # noqa: E731
    cases = [
        ("order_id", pd.Series(np.arange(n)), "identifier"), ("customer_id", S([f"C{i % 300}" for i in range(n)]), "identifier"),
        ("sku", S([f"SKU-{i}" for i in range(n)]), "identifier"), ("transaction_uuid", S([f"{i:032x}" for i in range(n)]), "identifier"),
        ("email", S([f"user{i}@mail.com" for i in range(n)]), "identifier"), ("invoice_no", pd.Series(np.arange(10_000, 10_000 + n)), "identifier"),
        ("revenue", pd.Series(rng.gamma(2, 300, n)), "measure"), ("profit", pd.Series(rng.normal(50, 30, n)), "measure"),
        ("quantity", pd.Series(rng.integers(1, 30, n)), "measure"), ("unit_price", pd.Series(rng.uniform(1, 99, n)), "measure"),
        ("discount_rate", pd.Series(rng.uniform(0, 0.4, n)), "measure"), ("delivery_days", pd.Series(rng.integers(1, 15, n)), "measure"),
        ("rating", pd.Series(rng.integers(1, 6, n)), "measure"), ("temperature", pd.Series(rng.normal(25, 5, n)), "measure"),
        ("clicks", pd.Series(rng.poisson(40, n)), "measure"), ("salary", pd.Series(rng.normal(60000, 9000, n)), "measure"),
        ("region", S(rng.choice(["N", "S", "E", "W"], n)), "dimension"), ("country", S(rng.choice(["India", "USA", "UK"], n)), "dimension"),
        ("segment", S(rng.choice(["Consumer", "Corporate"], n)), "dimension"), ("product_category", S(rng.choice(list("ABCDEFG"), n)), "dimension"),
        ("payment_method", S(rng.choice(["UPI", "Card", "Cash"], n)), "dimension"), ("status", S(rng.choice(["open", "closed"], n)), "dimension"),
        ("is_active", pd.Series(rng.choice([True, False], n)), "dimension"), ("churned", pd.Series(rng.integers(0, 2, n)), "dimension"),
        ("city", S(rng.choice([f"City{i}" for i in range(40)], n)), "dimension"), ("department", S(rng.choice(["HR", "IT", "Ops"], n)), "dimension"),
        ("order_date", pd.Series(pd.date_range("2024-01-01", periods=n, freq="h")), "time"), ("signup_ts", pd.Series(pd.date_range("2020-01-01", periods=n, freq="D")), "time"),
        ("year", pd.Series(rng.integers(2015, 2025, n)), "time"),
        ("feedback", S([f"The service on day {i} was {'good' if i % 2 else 'slow'} and staff were helpful overall" for i in range(n)]), "text"),
        ("comments", S([f"Customer note number {i}: requested callback regarding delivery window change" for i in range(n)]), "text"),
    ]
    rows, ok = [], 0
    for name, s, exp in cases:
        sem, role = infer_semantic(name, s)
        ok += role == exp
        rows.append({"column": name, "expected_role": exp, "predicted_role": role, "semantic_type": sem, "correct": role == exp})
    labels = sorted({c[2] for c in cases})
    per_role = {lab: f"{sum(r['correct'] for r in rows if r['expected_role'] == lab)}/{sum(r['expected_role'] == lab for r in rows)}" for lab in labels}
    RESULTS["E2_semantic_inference"] = {"columns": len(cases), "role_accuracy": round(ok / len(cases), 4), "per_role": per_role,
                                        "errors": [r for r in rows if not r["correct"]], "detail": rows}
    return RESULTS["E2_semantic_inference"]


# ---------------------------------------------------------------------------
# E3. Cross-dataset relationship (foreign key) discovery
# ---------------------------------------------------------------------------
def e3_relationships():
    rng = np.random.default_rng(9)
    customers = pd.DataFrame({"customer_id": [f"C{i}" for i in range(400)], "segment": rng.choice(["A", "B", "C"], 400),
                              "city": rng.choice([f"City{i}" for i in range(12)], 400)})
    products = pd.DataFrame({"product_id": [f"P{i}" for i in range(120)], "category": rng.choice(list("XYZ"), 120),
                             "price": rng.uniform(5, 99, 120)})
    stores = pd.DataFrame({"code": [f"S{i:02d}" for i in range(15)], "store_region": rng.choice(["N", "S"], 15)})
    employees = pd.DataFrame({"employee_no": np.arange(1, 61), "dept": rng.choice(["HR", "Ops"], 60)})
    n = 5000
    orders = pd.DataFrame({"order_id": [f"O{i}" for i in range(n)], "customer_id": rng.choice(customers.customer_id, n),
                           "product_id": rng.choice(products.product_id, n), "store_code": rng.choice(stores.code, n),
                           "status": rng.choice(["open", "closed"], n), "quantity": rng.integers(1, 60, n),
                           "salesperson": rng.choice(employees.employee_no, n)})
    tables = {"orders": orders, "customers": customers, "products": products, "stores": stores, "employees": employees}
    ds = []
    for i, (name, df) in enumerate(tables.items(), start=1):
        clean = transform(df).df
        wh.load_dataframe(f"dw_rel_{name}", clean)
        ds.append(SimpleNamespace(id=i, name=name, table_name=f"dw_rel_{name}", row_count=len(clean),
                                  profile=profile_dataframe(clean), source_config={}))
    found, secs = timed(relationships.discover, ds)
    pred = {(r["from_dataset"], r["from_column"], r["to_dataset"], r["to_column"]) for r in found}
    truth = {("orders", "customer_id", "customers", "customer_id"), ("orders", "product_id", "products", "product_id"),
             ("orders", "store_code", "stores", "code"), ("orders", "salesperson", "employees", "employee_no")}
    RESULTS["E3_relationships"] = {**prf(pred, truth), "seconds": round(secs, 3), "found": sorted(map(list, pred)),
                                   "missed": sorted(map(list, truth - pred)),
                                   "note": "salesperson→employee_no is an integer key with dissimilar names (hard case)"}
    return RESULTS["E3_relationships"]


# ---------------------------------------------------------------------------
# E4. Anomaly detection vs. univariate baselines (point + contextual anomalies)
# ---------------------------------------------------------------------------
def e4_anomalies():
    out = {}
    for seed in (1, 2, 3):
        rng = np.random.default_rng(seed)
        n = 5000
        qty = rng.integers(1, 10, n).astype(float)
        price = rng.lognormal(3.5, 0.6, n)
        revenue = qty * price
        cost = revenue * rng.uniform(0.55, 0.75, n)
        days = rng.poisson(4, n).astype(float)
        df = pd.DataFrame({"quantity": qty, "unit_price": price, "revenue": revenue, "cost": cost, "delivery_days": days})
        idx = rng.permutation(n)
        point, ctx = idx[:50], idx[50:100]
        df.loc[point, ["revenue", "cost"]] *= rng.uniform(6, 12, (50, 1))          # extreme magnitude
        df.loc[ctx, "cost"] = df.loc[ctx, "revenue"] * rng.uniform(1.6, 2.2, 50)   # cost > revenue: broken relationship
        truth_p, truth_c = set(point.tolist()), set(ctx.tolist())
        Z = StandardScaler().fit_transform(df)
        iso = IsolationForest(n_estimators=200, contamination=0.02, random_state=42).fit(Z)
        pred_if = set(np.where(iso.predict(Z) == -1)[0].tolist())
        Xr, _ = ml.relationship_features(df)
        Zr = StandardScaler().fit_transform(Xr)
        pred_rif = set(np.where(IsolationForest(n_estimators=200, contamination=0.02, random_state=42).fit(Zr).predict(Zr) == -1)[0].tolist())
        z = np.abs(Z)
        pred_z = set(np.where((z > 3).any(axis=1))[0].tolist())
        q1, q3 = df.quantile(0.25), df.quantile(0.75)
        iqr = q3 - q1
        pred_iqr = set(np.where(((df < q1 - 3 * iqr) | (df > q3 + 3 * iqr)).any(axis=1))[0].tolist())
        for name, pred in (("relationship_aware_iforest (InsightFlow)", pred_rif), ("isolation_forest", pred_if), ("zscore_3", pred_z), ("iqr_3x", pred_iqr)):
            o = out.setdefault(name, {"all": [], "point_recall": [], "contextual_recall": []})
            o["all"].append(prf(pred, truth_p | truth_c))
            o["point_recall"].append(len(pred & truth_p) / 50)
            o["contextual_recall"].append(len(pred & truth_c) / 50)
    summary = {}
    for name, o in out.items():
        summary[name] = {k: round(float(np.mean([m[k] for m in o["all"]])), 4) for k in ("precision", "recall", "f1")}
        summary[name]["flagged_mean"] = round(float(np.mean([m["tp"] + m["fp"] for m in o["all"]])), 1)
        summary[name]["point_recall"] = round(float(np.mean(o["point_recall"])), 4)
        summary[name]["contextual_recall"] = round(float(np.mean(o["contextual_recall"])), 4)
    RESULTS["E4_anomalies"] = {"setup": "5,000 rows x 5 measures, 2% anomalies (1% extreme magnitude, 1% contextual cost>revenue); mean of 3 seeds",
                               "results": summary}
    return RESULTS["E4_anomalies"]


# ---------------------------------------------------------------------------
# E5. Forecasting accuracy vs. baselines (rolling-origin holdout)
# ---------------------------------------------------------------------------
def e5_forecast():
    def mape(a, f):
        a, f = np.asarray(a, float), np.asarray(f, float)
        return float(np.mean(np.abs((a - f) / a)) * 100)

    def mase(a, f, train, m=12):
        scale = np.mean(np.abs(train[m:] - train[:-m])) if len(train) > m else np.mean(np.abs(np.diff(train)))
        return float(np.mean(np.abs(np.asarray(a) - np.asarray(f))) / scale)

    methods = {
        "naive": lambda y, h: np.repeat(y[-1], h),
        "seasonal_naive": lambda y, h: np.array([y[-12 + (i % 12)] for i in range(h)]),
        "linear_trend": lambda y, h: np.polyval(np.polyfit(np.arange(len(y)), y, 1), np.arange(len(y), len(y) + h)),
        "holt_winters_insightflow": lambda y, h: trends._fit_best(y, 12, h)[1],
    }
    rng = np.random.default_rng(21)
    series = []
    for _ in range(10 if QUICK else 40):
        t = np.arange(48)
        level, slope = rng.uniform(100, 1000), rng.uniform(-0.004, 0.02)
        amp, noise = rng.uniform(0.05, 0.35), rng.uniform(0.02, 0.10)
        y = level * (1 + slope * t) * (1 + amp * np.sin(2 * np.pi * (t + rng.integers(0, 12)) / 12)) * (1 + rng.normal(0, noise, 48))
        series.append(("synthetic", np.maximum(y, 1)))
    orders = transform(extract.read_file(ROOT / "sample_data" / "orders.csv")["data"]).df
    real = orders.set_index("order_date")["revenue"].resample("MS").sum().values.astype(float)
    series.append(("demo_revenue", real))

    h = 6
    scores = {m: {"mape": [], "mase": []} for m in methods}
    wins = {m: 0 for m in methods}
    real_scores = {}
    for kind, y in series:
        train, test = y[:-h], y[-h:]
        per = {}
        for m, f in methods.items():
            fc = f(train, h)
            per[m] = mape(test, fc)
            scores[m]["mape"].append(per[m])
            scores[m]["mase"].append(mase(test, fc, train))
        wins[min(per, key=per.get)] += 1
        if kind == "demo_revenue":
            real_scores = {m: round(v, 2) for m, v in per.items()}
    RESULTS["E5_forecasting"] = {
        "setup": f"{len(series) - 1} synthetic monthly series (48 months: trend x seasonality x noise) + demo revenue; train on all but last 6, forecast 6",
        "mean_mape": {m: round(float(np.mean(v["mape"])), 2) for m, v in scores.items()},
        "median_mape": {m: round(float(np.median(v["mape"])), 2) for m, v in scores.items()},
        "mean_mase": {m: round(float(np.mean(v["mase"])), 3) for m, v in scores.items()},
        "best_method_count": wins, "demo_revenue_mape": real_scores,
    }
    return RESULTS["E5_forecasting"]


# ---------------------------------------------------------------------------
# E6. Natural-language question understanding (rule-based parser)
# ---------------------------------------------------------------------------
NLQ_CASES = [
    # question, measure, agg, x, grain, filters{col: value}, series
    ("total revenue", "revenue", "sum", None, None, {}, None),
    ("what is the total profit?", "profit", "sum", None, None, {}, None),
    ("average unit price", "unit_price", "avg", None, None, {}, None),
    ("how many orders are there?", "*", "count", None, None, {}, None),
    ("total revenue by region", "revenue", "sum", "region", None, {}, None),
    ("revenue per sales channel", "revenue", "sum", "sales_channel", None, {}, None),
    ("average customer rating by sales channel", "customer_rating", "avg", "sales_channel", None, {}, None),
    ("top 5 region by profit", "profit", "sum", "region", None, {}, None),
    ("which region has the highest revenue", "revenue", "sum", "region", None, {}, None),
    ("show monthly total revenue", "revenue", "sum", "order_date", "month", {}, None),
    ("profit trend", "profit", "sum", "order_date", "month", {}, None),
    ("quarterly revenue", "revenue", "sum", "order_date", "quarter", {}, None),
    ("yearly cost", "cost", "sum", "order_date", "year", {}, None),
    ("revenue by region per quarter", "revenue", "sum", "order_date", "quarter", {}, "region"),
    ("monthly profit by sales channel", "profit", "sum", "order_date", "month", {}, "sales_channel"),
    ("total profit in North", "profit", "sum", None, None, {"region": "North"}, None),
    ("how many orders in 2024?", "*", "count", None, None, {"order_date": "2024"}, None),
    ("revenue by sales channel in 2023", "revenue", "sum", "sales_channel", None, {"order_date": "2023"}, None),
    ("average delivery days by region", "delivery_days", "avg", "region", None, {}, None),
    ("total quantity sold online", "quantity", "sum", None, None, {"sales_channel": "Online"}, None),
    ("max revenue", "revenue", "max", None, None, {}, None),
    ("minimum unit price by region", "unit_price", "min", "region", None, {}, None),
    ("median profit by sales channel", "profit", "median", "sales_channel", None, {}, None),
    ("weekly orders", "*", "count", "order_date", "week", {}, None),
    ("total sales by region", "revenue", "sum", "region", None, {}, None),
    ("average discount per region", "discount", "avg", "region", None, {}, None),
    ("share of revenue by sales channel", "revenue", "sum", "sales_channel", None, {}, None),
    ("profit in West during 2025", "profit", "sum", None, None, {"region": "West", "order_date": "2025"}, None),
    ("number of orders per region", "*", "count", "region", None, {}, None),
    ("daily revenue", "revenue", "sum", "order_date", "day", {}, None),
    ("total cost for marketplace orders by region", "cost", "sum", "region", None, {"sales_channel": "Marketplace"}, None),
    ("how did revenue change over time", "revenue", "sum", "order_date", "month", {}, None),
]


# Written after development of the parser was frozen; never used for tuning.
NLQ_HELDOUT = [
    ("sum of profit by region", "profit", "sum", "region", None, {}, None),
    ("mean customer rating", "customer_rating", "avg", None, None, {}, None),
    ("count of orders by sales channel", "*", "count", "sales_channel", None, {}, None),
    ("revenue for each region in 2024", "revenue", "sum", "region", None, {"order_date": "2024"}, None),
    ("annual profit", "profit", "sum", "order_date", "year", {}, None),
    ("monthly revenue in South", "revenue", "sum", "order_date", "month", {"region": "South"}, None),
    ("lowest delivery days by sales channel", "delivery_days", "min", "sales_channel", None, {}, None),
    ("how many customers per region", "customer_id", "count_distinct", "region", None, {}, None),
    ("quarterly profit split by region", "profit", "sum", "order_date", "quarter", {}, "region"),
    ("average quantity per order by region", "quantity", "avg", "region", None, {}, None),
    ("bottom 3 sales channel by profit", "profit", "sum", "sales_channel", None, {}, None),
    ("total revenue from the retail store channel", "revenue", "sum", None, None, {"sales_channel": "Retail Store"}, None),
    ("what was the cost in 2023", "cost", "sum", None, None, {"order_date": "2023"}, None),
    ("unique products sold", "product_id", "count_distinct", None, None, {}, None),
    ("revenue over time by sales channel", "revenue", "sum", "order_date", "month", {}, "sales_channel"),
    ("highest unit price", "unit_price", "max", None, None, {}, None),
    ("phone orders count", "*", "count", None, None, {"sales_channel": "Phone"}, None),
    ("discount by sales channel", "discount", "avg", "sales_channel", None, {}, None),
    ("profit margin trend", "profit", "sum", "order_date", "month", {}, None),
    ("east region revenue per month", "revenue", "sum", "order_date", "month", {"region": "East"}, None),
]


def _eval_nlq(cases, prof):
    comp = {"measure": 0, "aggregation": 0, "grouping": 0, "time_grain": 0, "filters": 0, "series": 0}
    exact, rows = 0, []
    for q, m, agg, x, grain, filt, series in cases:
        spec = nlq.rules_parse(q, "dw_eval_orders", prof)["spec"]
        y = spec["y"][0]
        got_f = {f["column"]: (str(f["value"][0])[:4] if f["op"] == "between" else str(f["value"])) for f in spec.get("filters", [])}
        checks = {
            "measure": y["column"] == m, "aggregation": y["agg"] == agg, "grouping": spec.get("x") == x,
            "time_grain": (spec.get("time_grain") if spec.get("x") == prof["primary_time"] else None) == grain,
            "filters": got_f == filt, "series": spec.get("series") == series,
        }
        for k, v in checks.items():
            comp[k] += v
        exact += all(checks.values())
        rows.append({"question": q, "correct": all(checks.values()), "failed": [k for k, v in checks.items() if not v],
                     "parsed": {"measure": y["column"], "agg": y["agg"], "x": spec.get("x"), "grain": spec.get("time_grain"),
                                "series": spec.get("series"), "filters": got_f}})
        query.run_chart_query("dw_eval_orders", prof, spec)  # every parse must also execute
    n = len(cases)
    return {"questions": n, "exact_match_accuracy": round(exact / n, 4),
            "component_accuracy": {k: round(v / n, 4) for k, v in comp.items()},
            "failures": [r for r in rows if not r["correct"]]}


def e6_nlq():
    raw = extract.read_file(ROOT / "sample_data" / "orders.csv")["data"]
    clean = transform(raw).df
    wh.load_dataframe("dw_eval_orders", clean)
    prof = profile_dataframe(clean)
    RESULTS["E6_nlq"] = {"development_set": _eval_nlq(NLQ_CASES, prof), "heldout_set": _eval_nlq(NLQ_HELDOUT, prof)}
    return RESULTS["E6_nlq"]


# ---------------------------------------------------------------------------
# E7. Scalability: ETL throughput and analytics latency vs. data size
# ---------------------------------------------------------------------------
def make_big(n: int, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({
        "Order ID": np.arange(n), "Order Date": pd.Timestamp("2021-01-01") + pd.to_timedelta(rng.integers(0, 1460, n), "D"),
        "Region": rng.choice(["North", "South", "East", "West", "north "], n), "Channel": rng.choice(["Online", "Store", "Partner"], n),
        "Category": rng.choice([f"Cat {i}" for i in range(12)], n), "Customer ID": rng.integers(0, max(n // 10, 10), n),
        "Quantity": rng.integers(1, 20, n), "Unit Price": rng.uniform(1, 500, n).round(2), "Discount": rng.choice([0, 0.05, 0.1, 0.2], n),
        "Delivery Days": rng.poisson(4, n), "Rating": rng.integers(1, 6, n),
    })
    d["Revenue"] = (d["Quantity"] * d["Unit Price"] * (1 - d["Discount"])).round(2)
    d["Order Date"] = d["Order Date"].dt.strftime("%Y-%m-%d")
    return d.to_csv(index=False).encode()


def e7_scalability():
    sizes = [10_000, 50_000, 100_000] if QUICK else [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]
    rows = []
    for n in sizes:
        raw_bytes = make_big(n)
        p = Path(TMP) / f"big_{n}.csv"
        p.write_bytes(raw_bytes)
        raw, t_e = timed(lambda: extract.read_file(p)["data"])
        res, t_t = timed(transform, raw)
        prof, t_p = timed(profile_dataframe, res.df)
        _, t_l = timed(wh.load_dataframe, f"dw_big_{n}", res.df)
        table = f"dw_big_{n}"
        _, q_chart = timed(query.run_chart_query, table, prof, {"x": prof["primary_time"], "y": [{"column": "revenue", "agg": "sum"}], "time_grain": "month"})
        _, q_group = timed(query.run_chart_query, table, prof, {"x": "region", "series": "channel", "y": [{"column": "revenue", "agg": "sum"}]})
        _, q_corr = timed(stats.correlations, table, prof)
        _, q_trend = timed(trends.analyze, table, prof, "revenue")
        _, q_anom = timed(ml.anomalies, table, prof)
        _, q_ins = timed(insights.generate, table, prof, {})
        etl = t_e + t_t + t_p + t_l
        rows.append({"rows": n, "csv_mb": round(len(raw_bytes) / 1e6, 1), "extract_s": round(t_e, 2), "transform_s": round(t_t, 2),
                     "profile_s": round(t_p, 2), "load_s": round(t_l, 2), "etl_total_s": round(etl, 2),
                     "throughput_rows_per_s": int(n / etl), "chart_query_ms": round(q_chart * 1000, 1),
                     "grouped_series_query_ms": round(q_group * 1000, 1), "correlations_ms": round(q_corr * 1000, 1),
                     "trend_forecast_ms": round(q_trend * 1000, 1), "anomalies_ms": round(q_anom * 1000, 1),
                     "full_insights_s": round(q_ins, 2)})
        print("  scalability", rows[-1], flush=True)
    RESULTS["E7_scalability"] = rows
    return rows


# ---------------------------------------------------------------------------
# E8. End-to-end case study on the bundled multi-source demo warehouse
# ---------------------------------------------------------------------------
def e8_case_study():
    import json as _json
    import sqlite3

    sd = ROOT / "sample_data"
    srcs = {
        "Sales Orders (CSV)": extract.read_file(sd / "orders.csv")["data"],
        "Product Catalog (Excel)": extract.read_file(sd / "products.xlsx")["Products"],
        "Customers (SQL)": extract.read_sql(f"sqlite:///{sd / 'erp.db'}", table="customers"),
        "Marketing (REST/JSON)": pd.DataFrame(_json.loads((sd / "marketing.json").read_text())["data"]),
    }
    out = []
    profs = {}
    for name, raw in srcs.items():
        res, secs = timed(transform, raw)
        q = quality_report(raw, res.df, res.issues)
        tname = "dw_cs_" + name.split()[0].lower()
        wh.load_dataframe(tname, res.df)
        profs[name] = (tname, profile_dataframe(res.df), q)
        fixed = sum(v for k, v in res.issues.items() if k not in {"outliers_detected", "columns_dropped"})
        out.append({"source": name, "raw_rows": len(raw), "clean_rows": len(res.df), "columns": res.df.shape[1],
                    "issues_fixed": int(fixed), "quality_before": q["score_before"], "quality_after": q["score_after"],
                    "etl_seconds": round(secs, 3), "issues": {k: int(v) for k, v in res.issues.items() if v}})
    tname, prof, q = profs["Sales Orders (CSV)"]
    ins = insights.generate(tname, prof, q)
    tr = trends.analyze(tname, prof, "revenue")
    kd = ml.key_drivers(tname, prof)
    an = ml.anomalies(tname, prof)
    cl = ml.clusters(tname, prof)
    RESULTS["E8_case_study"] = {
        "sources": out,
        "insights_generated": len(ins["insights"]),
        "insights_by_severity": pd.Series([i["severity"] for i in ins["insights"]]).value_counts().to_dict(),
        "top_insights": [i["title"] for i in ins["insights"][:8]],
        "trend": {**tr["trend"], "seasonality_peak": (tr.get("seasonality") or {}).get("peak"), "forecast_method": tr["forecast"]["method"],
                  "in_sample_mape": tr["forecast"]["mape"]},
        "key_drivers": [(d["feature"], d["importance"]) for d in kd["drivers"][:5]], "drivers_r2": kd["r2_in_sample"],
        "excluded_components": kd.get("co_moving"),
        "anomalies": {"count": an["anomaly_count"], "rate_pct": an["anomaly_rate_pct"]},
        "segments": {"k": cl.get("k"), "silhouette": cl.get("silhouette")},
    }
    return RESULTS["E8_case_study"]


# ---------------------------------------------------------------------------
def to_markdown() -> str:
    R = RESULTS
    L = ["# InsightFlow AI – Experimental Results", "",
         f"_Generated by `backend/scripts/evaluate.py` on {time.strftime('%Y-%m-%d')} · Python {platform.python_version()} · "
         f"{platform.machine()} · {os.cpu_count()} vCPU. Seeds are fixed; re-run to reproduce._", ""]
    e1 = R["E1_cleaning"]
    L += ["## E1. Data-cleaning accuracy (injected faults with ground truth)", "",
          "| Metric | Result |", "|---|---|",
          f"| Duplicate rows removed | {e1['duplicates_removed']} / {e1['duplicates_injected']} injected |",
          f"| Rows after cleaning vs. true rows | {e1['rows_clean']} / {e1['rows_true']} |",
          f"| Column type detection | {e1['column_type_accuracy']} columns correct |",
          f"| Currency strings parsed to correct value | {e1['currency_parse_accuracy']:.2%} |",
          f"| Alternate date formats parsed correctly | {e1['date_format_accuracy']:.2%} |",
          f"| Inconsistent labels normalised to canonical | {e1['label_normalisation_accuracy']:.2%} |",
          f"| Null placeholders (N/A, null, -, empty) recognised as missing | {e1['null_placeholder_recall']:.2%} recall, {e1['null_placeholder_false_positives']} false positives |",
          f"| Invalid numeric strings (abc, ??) isolated as missing | {e1['invalid_number_recall']:.2%} recall, {e1['invalid_number_false_positives']} false positives |",
          f"| Untouched cells preserved unchanged | {e1['untouched_cells_preserved']:.2%} |",
          f"| Cell agreement with ground truth (region+revenue), before → after | {e1['region_revenue_cell_match_before']:.2%} → {e1['region_revenue_cell_match_after']:.2%} |",
          f"| Quality score before → after | {e1['quality_score_before_after'][0]} → {e1['quality_score_before_after'][1]} |",
          f"| Transform time (5,120 rows) | {e1['transform_seconds']} s |", ""]
    e2 = R["E2_semantic_inference"]
    L += ["## E2. Semantic role inference", "", f"Role accuracy: **{e2['role_accuracy']:.2%}** on {e2['columns']} columns.", "",
          "| Role | Correct |", "|---|---|"] + [f"| {k} | {v} |" for k, v in e2["per_role"].items()] + [""]
    if e2["errors"]:
        L += ["Misclassified: " + "; ".join(f"`{r['column']}` (expected {r['expected_role']}, got {r['predicted_role']})" for r in e2["errors"]), ""]
    e3 = R["E3_relationships"]
    L += ["## E3. Relationship (foreign-key) discovery", "",
          f"Precision **{e3['precision']:.2f}**, recall **{e3['recall']:.2f}**, F1 **{e3['f1']:.2f}** (TP {e3['tp']}, FP {e3['fp']}, FN {e3['fn']}); {e3['seconds']} s.", "",
          "Missed: " + (", ".join(f"{m[0]}.{m[1]}→{m[2]}.{m[3]}" for m in e3["missed"]) or "none") + f". _{e3['note']}_", ""]
    e4 = R["E4_anomalies"]
    L += ["## E4. Anomaly detection", "", e4["setup"], "", "| Method | Precision | Recall | F1 | Point-anomaly recall | Contextual-anomaly recall | Rows flagged |", "|---|---|---|---|---|---|---|"]
    for m, v in e4["results"].items():
        L.append(f"| {m} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['point_recall']:.2f} | {v['contextual_recall']:.2f} | {v['flagged_mean']} |")
    e5 = R["E5_forecasting"]
    L += ["", "## E5. Forecasting (6-month horizon)", "", e5["setup"], "", "| Method | Mean MAPE % | Median MAPE % | Mean MASE | Best on # series | Demo revenue MAPE % |", "|---|---|---|---|---|---|"]
    for m in e5["mean_mape"]:
        L.append(f"| {m} | {e5['mean_mape'][m]} | {e5['median_mape'][m]} | {e5['mean_mase'][m]} | {e5['best_method_count'][m]} | {e5['demo_revenue_mape'].get(m)} |")
    dev, ho = R["E6_nlq"]["development_set"], R["E6_nlq"]["heldout_set"]
    L += ["", "## E6. Natural-language question understanding (rule-based parser, no LLM)", "",
          "The development set was used while building the parser; the held-out set was written afterwards and never used for tuning.", "",
          "| Component | Development set | Held-out set |", "|---|---|---|",
          f"| **Exact match (all components)** | **{dev['exact_match_accuracy']:.2%}** ({dev['questions']} q) | **{ho['exact_match_accuracy']:.2%}** ({ho['questions']} q) |"]
    L += [f"| {k} | {dev['component_accuracy'][k]:.2%} | {ho['component_accuracy'][k]:.2%} |" for k in dev["component_accuracy"]]
    fails = [("dev", f) for f in dev["failures"]] + [("held-out", f) for f in ho["failures"]]
    if fails:
        L += ["", "Failed questions:", ""] + [f"- [{s}] “{f['question']}” – wrong {', '.join(f['failed'])}; parsed {f['parsed']}" for s, f in fails]
    L += ["", "## E7. Scalability", "", "| Rows | CSV MB | Extract s | Transform s | Profile s | Load s | ETL total s | Rows/s | Monthly chart ms | Grouped series ms | Correlations ms | Trend+forecast ms | Anomalies ms | Full insights s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in R["E7_scalability"]:
        L.append(f"| {r['rows']:,} | {r['csv_mb']} | {r['extract_s']} | {r['transform_s']} | {r['profile_s']} | {r['load_s']} | {r['etl_total_s']} | {r['throughput_rows_per_s']:,} | "
                 f"{r['chart_query_ms']} | {r['grouped_series_query_ms']} | {r['correlations_ms']} | {r['trend_forecast_ms']} | {r['anomalies_ms']} | {r['full_insights_s']} |")
    e8 = R["E8_case_study"]
    L += ["", "## E8. Case study – multi-source retail warehouse", "", "| Source | Raw rows | Clean rows | Cols | Issues fixed | Quality before → after | ETL s |", "|---|---|---|---|---|---|---|"]
    for s in e8["sources"]:
        L.append(f"| {s['source']} | {s['raw_rows']:,} | {s['clean_rows']:,} | {s['columns']} | {s['issues_fixed']} | {s['quality_before']} → {s['quality_after']} | {s['etl_seconds']} |")
    L += ["", f"Insights generated for Sales Orders: {e8['insights_generated']} ({e8['insights_by_severity']}).",
          f"Trend: {e8['trend']['direction']} (R² {e8['trend']['r2']}), seasonal peak {e8['trend']['seasonality_peak']}, {e8['trend']['forecast_method']} in-sample MAPE {e8['trend']['in_sample_mape']}%.",
          f"Key drivers of revenue: {e8['key_drivers']} (R² {e8['drivers_r2']}); excluded components {e8['excluded_components']}.",
          f"Anomalies: {e8['anomalies']}; segments: {e8['segments']}.", "", "Top insights:", ""] + [f"1. {t}" for t in e8["top_insights"]]
    return "\n".join(L) + "\n"


def main():
    wh.reset_connection(str(Path(TMP) / "eval.duckdb"))
    steps = [("E1 cleaning", e1_cleaning), ("E2 semantics", e2_semantics), ("E3 relationships", e3_relationships),
             ("E4 anomalies", e4_anomalies), ("E5 forecasting", e5_forecast), ("E6 NLQ", e6_nlq),
             ("E8 case study", e8_case_study), ("E7 scalability", e7_scalability)]
    for name, fn in steps:
        t = time.perf_counter()
        print(f"Running {name}...", flush=True)
        fn()
        print(f"  done in {time.perf_counter() - t:.1f}s", flush=True)
    RESULTS["environment"] = {"python": platform.python_version(), "platform": platform.platform(), "cpus": os.cpu_count(),
                              "pandas": pd.__version__, "numpy": np.__version__}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    (OUT / "RESULTS.md").write_text(to_markdown())
    print(f"Wrote {OUT / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
