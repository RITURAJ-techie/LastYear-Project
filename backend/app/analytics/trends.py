"""Time-series trend analysis, seasonality detection and forecasting (Holt-Winters)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps

from .. import warehouse as wh

GRAIN_FREQ = {"day": "D", "week": "W-MON", "month": "MS", "quarter": "QS", "year": "YS"}
SEASON = {"day": 7, "week": 52, "month": 12, "quarter": 4, "year": 1}


def choose_grain(span_days: int) -> str:
    if span_days <= 92:
        return "day"
    if span_days <= 730:
        return "week" if span_days <= 200 else "month"
    if span_days <= 365 * 12:
        return "month"
    return "year"


def series(table: str, time_col: str, measure: str | None, agg: str, grain: str) -> pd.Series:
    t = wh.qi(time_col)
    expr = "count(*)" if not measure else f"{'avg' if agg == 'avg' else agg}({wh.qi(measure)})"
    df = wh.query_df(
        f"SELECT date_trunc('{grain}', {t}) AS p, {expr} AS v FROM {wh.safe_table(table)} WHERE {t} IS NOT NULL GROUP BY 1 ORDER BY 1"
    )
    if df.empty:
        return pd.Series(dtype=float)
    s = df.set_index(pd.to_datetime(df["p"]))["v"].astype(float)
    full = pd.date_range(s.index.min(), s.index.max(), freq=GRAIN_FREQ[grain])
    s = s.reindex(full)
    fill = 0.0 if agg in {"sum", "count"} else np.nan
    return s.fillna(fill).interpolate(limit_direction="both") if agg not in {"sum", "count"} else s.fillna(fill)


def holt_winters(y: np.ndarray, season: int, horizon: int, alpha=0.4, beta=0.1, gamma=0.3, phi=0.95) -> tuple[np.ndarray, np.ndarray]:
    """Additive damped Holt-Winters. Falls back to damped Holt (no season) for short series.

    Returns (fitted_in_sample, forecast)."""
    n = len(y)
    use_season = season > 1 and n >= 2 * season
    level = y[:season].mean() if use_season else y[0]
    trend = ((y[season:2 * season].mean() - y[:season].mean()) / season) if use_season else (y[min(1, n - 1)] - y[0])
    seas = list(y[:season] - level) if use_season else [0.0]
    fitted = np.zeros(n)
    for t in range(n):
        s_idx = t % season if use_season else 0
        s_t = seas[s_idx] if use_season else 0.0
        fitted[t] = level + phi * trend + s_t
        prev_level = level
        level = alpha * (y[t] - s_t) + (1 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend
        if use_season:
            seas[s_idx] = gamma * (y[t] - level) + (1 - gamma) * s_t
    fc = np.zeros(horizon)
    damp = 0.0
    for h in range(1, horizon + 1):
        damp += phi ** h
        s_t = seas[(n + h - 1) % season] if use_season else 0.0
        fc[h - 1] = level + damp * trend + s_t
    return fitted, fc


def _fit_best(y: np.ndarray, season: int, horizon: int) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """Small grid search on smoothing parameters minimising one-step-ahead SSE."""
    best = None
    for a in (0.2, 0.4, 0.6, 0.8):
        for b in (0.05, 0.15, 0.3):
            for g in ((0.1, 0.3, 0.5) if season > 1 and len(y) >= 2 * season else (0.0,)):
                fitted, fc = holt_winters(y, season, horizon, a, b, g)
                warm = min(season if season > 1 else 1, len(y) - 1)
                sse = float(np.sum((y[warm:] - fitted[warm:]) ** 2))
                if best is None or sse < best[0]:
                    best = (sse, fitted, fc, {"alpha": a, "beta": b, "gamma": g})
    _, fitted, fc, params = best
    return fitted, fc, params


def analyze(table: str, profile: dict[str, Any], measure: str | None = None, time_col: str | None = None,
            grain: str | None = None, horizon: int | None = None, agg: str | None = None) -> dict[str, Any]:
    time_col = time_col or profile.get("primary_time")
    if not time_col:
        return {"available": False, "reason": "No date/time column detected in this dataset"}
    cols = {c["name"]: c for c in profile["columns"]}
    measure = measure or profile.get("primary_measure")
    if measure and measure not in cols:
        raise ValueError(f"Unknown column {measure}")
    agg = agg or (cols[measure].get("default_agg", "sum") if measure else "count")
    span = (cols[time_col].get("stats") or {}).get("span_days", 365)
    grain = grain if grain in GRAIN_FREQ else choose_grain(span)
    s = series(table, time_col, measure, agg, grain)
    if len(s) < 3:
        return {"available": False, "reason": "Not enough time periods for trend analysis"}

    # the final period is frequently incomplete (data extracted mid-month) – exclude from trend stats
    last_partial = False
    if agg in {"sum", "count"} and len(s) >= 4 and s.iloc[-1] < 0.6 * s.iloc[-4:-1].mean():
        last_partial = True
    core = s.iloc[:-1] if last_partial else s
    y = core.values.astype(float)
    x = np.arange(len(y))
    lr = sps.linregress(x, y)
    mean = float(np.mean(y)) or 1.0
    slope_pct = float(lr.slope / abs(mean) * 100)
    direction = "upward" if lr.pvalue < 0.05 and lr.slope > 0 else "downward" if lr.pvalue < 0.05 and lr.slope < 0 else "flat / no significant trend"

    season = SEASON[grain]
    seasonality = None
    if season > 1 and len(y) >= 2 * season:
        idx = core.index
        key = {"day": idx.day_of_week, "week": idx.isocalendar().week.values, "month": idx.month, "quarter": idx.quarter}[grain]
        prof = pd.Series(y, index=key).groupby(level=0).mean()
        strength = float(prof.std() / abs(prof.mean())) if prof.mean() else 0.0
        names = {"day": lambda k: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][k],
                 "month": lambda k: pd.Timestamp(2000, int(k), 1).strftime("%b"),
                 "quarter": lambda k: f"Q{k}", "week": lambda k: f"W{k}"}[grain]
        seasonality = {
            "strength": round(strength, 4),
            "detected": strength > 0.08,
            "peak": names(prof.idxmax()), "trough": names(prof.idxmin()),
            "profile": [{"period": names(k), "value": round(float(v), 4)} for k, v in prof.items()],
        }

    horizon = horizon or {"day": 30, "week": 12, "month": 6, "quarter": 4, "year": 3}[grain]
    fitted, fc, params = _fit_best(y, season, horizon)
    warm = min(season if season > 1 else 1, len(y) - 1)
    resid = y[warm:] - fitted[warm:]
    sigma = float(np.std(resid)) if len(resid) > 1 else 0.0
    mape = float(np.mean(np.abs(resid / np.where(y[warm:] == 0, np.nan, y[warm:]))) * 100) if len(resid) else None
    future = pd.date_range(core.index[-1], periods=horizon + 1, freq=GRAIN_FREQ[grain])[1:]
    nonneg = bool((y >= 0).all())
    points = []
    for i, (ts, v) in enumerate(s.items()):
        p = {"period": ts.strftime("%Y-%m-%d"), "actual": round(float(v), 4)}
        if i < len(fitted):
            p["fitted"] = round(float(fitted[i]), 4)
        points.append(p)
    for h, (ts, v) in enumerate(zip(future, fc), start=1):
        band = 1.96 * sigma * np.sqrt(h)
        lo = v - band
        points.append({"period": ts.strftime("%Y-%m-%d"), "forecast": round(float(max(v, 0) if nonneg else v), 4),
                       "lower": round(float(max(lo, 0) if nonneg else lo), 4), "upper": round(float(v + band), 4)})

    first, last = float(y[0]), float(y[-1])
    prev = float(y[-2]) if len(y) > 1 else None
    # rolling anomalies on the series (robust z-score on residuals vs rolling median)
    roll = pd.Series(y).rolling(min(7, max(3, len(y) // 6)), center=True, min_periods=1).median()
    dev = pd.Series(y) - roll
    mad = float(np.median(np.abs(dev - np.median(dev)))) or (float(np.std(dev)) or 1.0)
    rz = 0.6745 * dev / mad
    ts_anoms = [{"period": core.index[i].strftime("%Y-%m-%d"), "value": round(float(y[i]), 4), "expected": round(float(roll[i]), 4),
                 "score": round(float(rz[i]), 2), "type": "spike" if rz[i] > 0 else "dip"}
                for i in np.where(np.abs(rz) > 3.5)[0]]

    return {
        "available": True,
        "time_column": time_col, "measure": measure or "records", "agg": agg, "grain": grain,
        "points": points,
        "last_period_partial": last_partial,
        "trend": {
            "direction": direction, "slope_per_period": round(float(lr.slope), 4), "slope_pct_of_mean": round(slope_pct, 3),
            "r2": round(float(lr.rvalue ** 2), 4), "p_value": float(lr.pvalue),
        },
        "growth": {
            "first": first, "last": last, "total_change_pct": round((last - first) / abs(first) * 100, 2) if first else None,
            "last_change_pct": round((last - prev) / abs(prev) * 100, 2) if prev else None,
            "peak_period": core.idxmax().strftime("%Y-%m-%d"), "peak_value": float(core.max()),
            "low_period": core.idxmin().strftime("%Y-%m-%d"), "low_value": float(core.min()),
        },
        "seasonality": seasonality,
        "forecast": {"horizon": horizon, "method": "Holt-Winters (additive, damped)" if season > 1 and len(y) >= 2 * season else "Holt (damped trend)",
                     "params": params, "mape": round(mape, 2) if mape is not None and not np.isnan(mape) else None,
                     "total_forecast": round(float(np.sum(np.maximum(fc, 0) if nonneg else fc)), 4)},
        "anomalies": ts_anoms,
    }
