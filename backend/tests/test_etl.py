import pandas as pd

from app.etl.profile import infer_semantic, profile_dataframe, quality_report
from app.etl.transform import standardize_name, transform


def test_standardize_name():
    assert standardize_name("Order Date", 0) == "order_date"
    assert standardize_name("customerID", 1) == "customer_id"
    assert standardize_name("2024 Sales ($)", 2) == "c_2024_sales"
    assert standardize_name("", 3) == "column_4"


def test_transform_cleans_messy_data():
    raw = pd.DataFrame({
        "Region": ["North", "north ", "NORTH", "South", "South", None],
        "Amount": ["$1,200.50", "300", "N/A", "(50)", "75%", "10"],
        "When": ["2024-01-01", "2024/01/02", "2024-01-03", "2024-01-04", "2024-01-04", "2024-01-05"],
        "Active": ["yes", "no", "Yes", "no", "no", "yes"],
    })
    raw = pd.concat([raw, raw.iloc[[3]]])  # one exact duplicate
    res = transform(raw)
    df = res.df
    assert list(df.columns) == ["region", "amount", "when", "active"]
    assert pd.api.types.is_datetime64_any_dtype(df["when"])
    assert pd.api.types.is_numeric_dtype(df["amount"])
    assert df["amount"].iloc[0] == 1200.5
    assert -50 in df["amount"].tolist()
    assert set(df["region"]) == {"North", "South", "Unknown"}
    assert pd.api.types.is_bool_dtype(df["active"])
    assert res.issues["duplicates_removed"] == 1
    assert res.issues["imputed_values"] >= 2
    assert df.isna().sum().sum() == 0
    steps = [s["step"] for s in res.log]
    assert steps[0] == "extract" and "fix_types" in steps and steps[-1] == "load_ready"


def test_semantic_inference():
    n = 100
    assert infer_semantic("order_id", pd.Series(range(n)))[1] == "identifier"
    assert infer_semantic("revenue", pd.Series([1.5] * 50 + [2.5] * 50)) == ("currency", "measure")
    assert infer_semantic("segment", pd.Series(["A", "B"] * 50, dtype="string")) == ("categorical", "dimension")
    assert infer_semantic("region", pd.Series(["A", "B"] * 50, dtype="string")) == ("geo", "dimension")
    assert infer_semantic("date", pd.Series(pd.date_range("2024-01-01", periods=n)))[0] == "datetime"
    assert infer_semantic("email", pd.Series([f"u{i}@x.com" for i in range(n)], dtype="string"))[0] == "email"


def test_profile_and_quality():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=40), "sales": range(40),
                       "region": ["A", "B", "C", "D"] * 10})
    p = profile_dataframe(df)
    assert p["primary_time"] == "date" and p["primary_measure"] == "sales" and "region" in p["dimensions"]
    q = quality_report(df, df, {})
    assert q["score_after"] == 100.0 and q["grade"] == "A"
