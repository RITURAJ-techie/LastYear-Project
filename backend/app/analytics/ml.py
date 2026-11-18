"""Machine-learning analytics: multivariate anomaly detection, key-driver analysis and clustering."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .. import warehouse as wh
from .stats import load


def anomalies(table: str, profile: dict[str, Any], contamination: float = 0.02, top: int = 25) -> dict[str, Any]:
    measures = profile["measures"][:12]
    if not measures:
        return {"available": False, "reason": "No numeric measures to analyse"}
    ident = profile["identifiers"][:1] + profile["time_columns"][:1] + profile["dimensions"][:2]
    df = load(table, list(dict.fromkeys(ident + measures)), sample=50_000)
    X = df[measures].astype(float)
    X = X.fillna(X.median())
    X = X.loc[:, X.std() > 0]
    if X.shape[1] == 0 or len(X) < 20:
        return {"available": False, "reason": "Not enough varied numeric data for anomaly detection"}
    scaler = StandardScaler()
    Z = scaler.fit_transform(X)
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=42)
    labels = model.fit_predict(Z)
    scores = -model.score_samples(Z)  # higher = more anomalous
    df = df.assign(_score=scores, _anomaly=labels == -1)
    zdf = pd.DataFrame(Z, columns=X.columns, index=df.index)
    flagged = df[df["_anomaly"]].sort_values("_score", ascending=False).head(top)
    rows = []
    for idx, r in flagged.iterrows():
        z = zdf.loc[idx]
        drivers = z.abs().sort_values(ascending=False).head(3)
        reasons = [f"{c} is {'unusually high' if z[c] > 0 else 'unusually low'} ({X.loc[idx, c]:,.2f}, {abs(z[c]):.1f}σ from mean)"
                   for c in drivers.index if abs(z[c]) >= 1.5]
        rec = wh.to_records(pd.DataFrame([r.drop(["_score", "_anomaly"])]))[0]
        rows.append({"score": round(float(r["_score"]), 4), "record": rec, "reasons": reasons or ["Unusual combination of values"]})
    per_col = []
    for c in X.columns:
        z = np.abs(zdf[c])
        per_col.append({"column": c, "extreme_values": int((z > 3).sum()), "max_z": round(float(z.max()), 2)})
    per_col.sort(key=lambda d: -d["extreme_values"])
    return {
        "available": True, "method": "Isolation Forest (multivariate) + z-score attribution",
        "rows_analyzed": int(len(df)), "anomaly_count": int(df["_anomaly"].sum()),
        "anomaly_rate_pct": round(float(df["_anomaly"].mean() * 100), 2),
        "features": list(X.columns), "top": rows, "by_column": per_col,
    }


def key_drivers(table: str, profile: dict[str, Any], target: str | None = None) -> dict[str, Any]:
    """Which columns best explain variation in a target measure (RandomForest + univariate effect size)."""
    target = target or profile.get("primary_measure")
    if not target:
        return {"available": False, "reason": "No numeric target available"}
    cols = {c["name"]: c for c in profile["columns"]}
    if target not in cols:
        raise ValueError(f"Unknown column {target}")
    num_candidates = [m for m in profile["measures"] if m != target][:15]
    cat_features = [d for d in profile["dimensions"] if 2 <= cols[d]["unique"] <= 40][:8]
    if profile.get("primary_time"):
        cat_features_time = profile["primary_time"]
    else:
        cat_features_time = None
    use = [target] + num_candidates + cat_features + ([cat_features_time] if cat_features_time else [])
    df = load(table, list(dict.fromkeys(use)), sample=20_000).dropna(subset=[target])
    if len(df) < 30:
        return {"available": False, "reason": "Need at least 30 rows for driver analysis"}
    y = df[target].astype(float)
    # measures that move almost 1:1 with the target are usually components of it (e.g. cost
    # inside revenue); they are reported separately instead of being called "drivers"
    co_moving, num_features = [], []
    for c in num_candidates:
        x = df[c].astype(float)
        r = float(np.corrcoef(x.fillna(x.median()), y)[0, 1]) if x.std() > 0 else 0.0
        (co_moving if abs(r) >= 0.7 else num_features).append({"column": c, "r": round(r, 4)} if abs(r) >= 0.7 else c)
    parts = [df[num_features].astype(float).fillna(df[num_features].astype(float).median())] if num_features else []
    origin: dict[str, str] = {c: c for c in num_features}
    for c in cat_features:
        d = pd.get_dummies(df[c].astype(str), prefix=c, prefix_sep="=").astype(float)
        parts.append(d)
        origin.update({k: c for k in d.columns})
    if cat_features_time:
        t = pd.to_datetime(df[cat_features_time])
        tf = pd.DataFrame({f"{cat_features_time}:month": t.dt.month, f"{cat_features_time}:dayofweek": t.dt.day_of_week}, index=df.index).fillna(0)
        parts.append(tf)
        origin.update({k: k for k in tf.columns})
    if not parts:
        return {"available": False, "reason": "No candidate driver columns"}
    X = pd.concat(parts, axis=1)
    model = RandomForestRegressor(n_estimators=150, max_depth=10, min_samples_leaf=5, random_state=42, n_jobs=-1)
    model.fit(X, y)
    r2 = float(model.score(X, y))
    imp = pd.Series(model.feature_importances_, index=X.columns).groupby(lambda k: origin[k]).sum().sort_values(ascending=False)
    drivers = []
    for feat, importance in imp.head(12).items():
        entry: dict[str, Any] = {"feature": feat, "importance": round(float(importance) * 100, 2)}
        if feat in num_features:
            r = float(np.corrcoef(df[feat].astype(float).fillna(df[feat].median()), y)[0, 1])
            entry.update(kind="numeric", correlation=round(r, 4),
                         effect=f"Higher {feat} is associated with {'higher' if r > 0 else 'lower'} {target} (r={r:.2f})")
        elif feat in cat_features:
            g = df.groupby(df[feat].astype(str))[target].mean().sort_values(ascending=False)
            entry.update(kind="categorical", best=g.index[0], best_value=round(float(g.iloc[0]), 4),
                         worst=g.index[-1], worst_value=round(float(g.iloc[-1]), 4),
                         effect=f"Average {target} ranges from {g.iloc[-1]:,.2f} ({g.index[-1]}) to {g.iloc[0]:,.2f} ({g.index[0]})")
        else:
            entry.update(kind="time", effect=f"Calendar effect ({feat.split(':')[1]}) on {target}")
        drivers.append(entry)
    return {"available": True, "target": target, "model": "Random Forest regressor", "r2_in_sample": round(r2, 4),
            "rows_used": int(len(df)), "drivers": drivers, "co_moving": co_moving}


def clusters(table: str, profile: dict[str, Any], k: int | None = None) -> dict[str, Any]:
    """K-Means segmentation of records on numeric measures, with automatic k (silhouette)."""
    measures = profile["measures"][:8]
    if len(measures) < 2:
        return {"available": False, "reason": "Need at least two numeric measures for segmentation"}
    df = load(table, measures, sample=20_000).astype(float)
    df = df.fillna(df.median())
    df = df.loc[:, df.std() > 0]
    if len(df) < 50 or df.shape[1] < 2:
        return {"available": False, "reason": "Not enough data for segmentation"}
    Z = StandardScaler().fit_transform(df)
    sample_idx = np.random.default_rng(0).choice(len(Z), size=min(3000, len(Z)), replace=False)
    best = None
    for kk in ([k] if k else range(2, 7)):
        km = KMeans(n_clusters=kk, n_init=5, random_state=42).fit(Z)
        sil = float(silhouette_score(Z[sample_idx], km.labels_[sample_idx]))
        if best is None or sil > best[0]:
            best = (sil, kk, km)
    sil, kk, km = best
    df["_cluster"] = km.labels_
    overall = df.drop(columns="_cluster").mean()
    segs = []
    for cid, g in df.groupby("_cluster"):
        means = g.drop(columns="_cluster").mean()
        rel = ((means - overall) / overall.abs().replace(0, np.nan) * 100).fillna(0)
        high = rel.sort_values(ascending=False)
        desc = [f"{c} {'+' if v >= 0 else ''}{v:.0f}%" for c, v in list(high.head(2).items()) + list(high.tail(1).items())]
        segs.append({"cluster": int(cid), "size": int(len(g)), "share_pct": round(len(g) / len(df) * 100, 2),
                     "means": {c: round(float(v), 4) for c, v in means.items()}, "profile": ", ".join(desc)})
    segs.sort(key=lambda s: -s["size"])
    # 2D projection for plotting (first two principal components)
    U, S, Vt = np.linalg.svd(Z[sample_idx[:800]] - Z.mean(0), full_matrices=False)
    proj = (Z[sample_idx[:800]] - Z.mean(0)) @ Vt[:2].T
    points = [{"x": round(float(p[0]), 4), "y": round(float(p[1]), 4), "cluster": int(km.labels_[i])}
              for p, i in zip(proj, sample_idx[:800])]
    return {"available": True, "k": kk, "silhouette": round(sil, 4), "features": list(df.columns.drop("_cluster")),
            "segments": segs, "points": points}
