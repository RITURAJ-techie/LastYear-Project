import numpy as np
import pandas as pd
import pytest

from app import warehouse as wh
from app.analytics import query as q
from app.analytics import trends
from app.analytics.sqlguard import SQLGuardError, validate_select
from app.etl.profile import profile_dataframe


@pytest.fixture(scope="module")
def table():
    rng = np.random.default_rng(1)
    n = 730
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    season = 1 + 0.4 * np.sin(2 * np.pi * dates.day_of_year.values / 365)
    df = pd.DataFrame({"day": dates, "region": rng.choice(["A", "B", "C"], n),
                       "sales": (100 + np.arange(n) * 0.2) * season + rng.normal(0, 5, n),
                       "units": rng.integers(1, 20, n)})
    wh.load_dataframe("dw_test_sales", df)
    return "dw_test_sales", profile_dataframe(df)


def test_chart_query_time_grain(table):
    t, p = table
    res = q.run_chart_query(t, p, {"x": "day", "y": [{"column": "sales", "agg": "sum"}], "time_grain": "month"})
    assert len(res["rows"]) == 24 and res["is_time"]


def test_chart_query_filters_and_series(table):
    t, p = table
    res = q.run_chart_query(t, p, {"x": "day", "series": "region", "y": [{"column": "units", "agg": "sum"}], "time_grain": "quarter",
                                   "filters": [{"column": "day", "op": "between", "value": ["2023-01-01", "2023-12-31"]}]})
    assert len(res["rows"]) == 4 and set(res["y"]) == {"A", "B", "C"}


def test_chart_query_rejects_unknown_column(table):
    t, p = table
    with pytest.raises(q.QueryError):
        q.run_chart_query(t, p, {"x": "nope", "y": [{"column": "sales", "agg": "sum"}]})


def test_trend_and_forecast(table):
    t, p = table
    res = trends.analyze(t, p, measure="sales", grain="month")
    assert res["available"]
    assert res["trend"]["direction"].startswith("upward")
    assert res["forecast"]["horizon"] == 6
    assert sum(1 for pt in res["points"] if "forecast" in pt) == 6


def test_sql_guard():
    allowed = {"dw_test_sales"}
    assert validate_select("SELECT * FROM dw_test_sales;", allowed)
    for bad in ["DROP TABLE dw_test_sales", "select 1; select 2", "select * from dw_other",
                "select * from read_csv('/etc/passwd')", "COPY dw_test_sales TO 'x.csv'"]:
        with pytest.raises(SQLGuardError):
            validate_select(bad, allowed)


def test_warehouse_blocks_file_access():
    with pytest.raises(Exception):
        wh.query_df("SELECT * FROM read_csv('/etc/passwd')")
