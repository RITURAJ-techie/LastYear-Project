"""Generate a realistic, deliberately *messy* multi-source retail dataset for demos.

Outputs (backend/sample_data/):
  orders.csv        – transactional fact data (CSV, with quality problems to clean)
  products.xlsx     – product master data (Excel)
  erp.db            – SQLite "ERP" database with a customers table (SQL source)
  marketing.json    – monthly marketing spend (served by the demo REST API)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "sample_data"
rng = np.random.default_rng(2024)


def products() -> pd.DataFrame:
    cats = {
        "Electronics": (["Laptops", "Phones", "Audio", "Accessories"], (40, 1600)),
        "Home & Kitchen": (["Appliances", "Cookware", "Decor"], (15, 450)),
        "Fashion": (["Men", "Women", "Footwear"], (10, 180)),
        "Sports": (["Fitness", "Outdoor", "Cycling"], (12, 900)),
        "Books": (["Fiction", "Business", "Education"], (6, 60)),
    }
    brands = ["Novix", "Lumen", "Arcadia", "Peak", "Orbit", "Vertex", "Kora", "Zenith"]
    rows = []
    pid = 1000
    for cat, (subs, (lo, hi)) in cats.items():
        for sub in subs:
            for _ in range(rng.integers(5, 9)):
                pid += 1
                rows.append({
                    "Product ID": f"P{pid}", "Product Name": f"{rng.choice(brands)} {sub[:-1] if sub.endswith('s') else sub} {rng.integers(100, 999)}",
                    "Category": cat, "Sub Category": sub, "Brand": rng.choice(brands),
                    "List Price": round(float(rng.uniform(lo, hi)), 2),
                    "Launch Date": (pd.Timestamp("2019-01-01") + pd.Timedelta(days=int(rng.integers(0, 1700)))).date(),
                })
    return pd.DataFrame(rows)


def customers(n: int = 900) -> pd.DataFrame:
    geo = {"North": ["Delhi", "Chandigarh", "Lucknow", "Jaipur"], "South": ["Bengaluru", "Chennai", "Hyderabad", "Kochi"],
           "East": ["Kolkata", "Bhubaneswar", "Patna", "Guwahati"], "West": ["Mumbai", "Pune", "Ahmedabad", "Goa"]}
    first = ["Aarav", "Diya", "Ishaan", "Ananya", "Kabir", "Meera", "Rohan", "Saanvi", "Vihaan", "Aditi", "Arjun", "Nisha", "Dev", "Priya", "Kunal", "Riya"]
    last = ["Sharma", "Iyer", "Patel", "Das", "Reddy", "Khan", "Singh", "Gupta", "Nair", "Mehta", "Bose", "Joshi"]
    rows = []
    for i in range(n):
        region = rng.choice(list(geo), p=[0.3, 0.28, 0.17, 0.25])
        rows.append({
            "customer_id": f"C{5000 + i}",
            "customer_name": f"{rng.choice(first)} {rng.choice(last)}",
            "segment": rng.choice(["Consumer", "Corporate", "Small Business"], p=[0.6, 0.25, 0.15]),
            "region": region, "city": rng.choice(geo[region]),
            "signup_date": str((pd.Timestamp("2021-01-01") + pd.Timedelta(days=int(rng.integers(0, 1500)))).date()),
            "age": int(np.clip(rng.normal(36, 11), 18, 75)),
            "loyalty_tier": rng.choice(["Bronze", "Silver", "Gold", "Platinum"], p=[0.45, 0.3, 0.18, 0.07]),
        })
    return pd.DataFrame(rows)


def orders(prod: pd.DataFrame, cust: pd.DataFrame, n: int = 6000) -> pd.DataFrame:
    start, end = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-10-31")
    days = (end - start).days
    # growth trend + Q4 seasonality + weekend lift
    d = np.arange(days + 1)
    dates = start + pd.to_timedelta(d, unit="D")
    weight = (1 + d / days * 0.6) * (1 + 0.45 * np.isin(dates.month, [10, 11, 12]) + 0.15 * np.isin(dates.month, [5, 6])) * (1 + 0.2 * (dates.day_of_week >= 5))
    weight /= weight.sum()
    od = start + pd.to_timedelta(rng.choice(d, size=n, p=weight), unit="D")
    p_idx = rng.integers(0, len(prod), size=n)
    c_idx = rng.integers(0, len(cust), size=n)
    channel = rng.choice(["Online", "Retail Store", "Marketplace", "Phone"], size=n, p=[0.45, 0.3, 0.2, 0.05])
    qty = rng.choice([1, 1, 1, 2, 2, 3, 4, 5], size=n)
    price = prod["List Price"].values[p_idx] * rng.uniform(0.9, 1.05, size=n)
    discount = np.round(rng.choice([0, 0, 0.05, 0.1, 0.15, 0.2, 0.3], size=n), 2)
    # "East" region and "Books" category decline in the most recent months (story for insights)
    recent = od >= pd.Timestamp("2025-05-01")
    east = cust["region"].values[c_idx] == "East"
    qty = np.where(recent & east & (rng.random(n) < 0.5), 1, qty)
    revenue = np.round(qty * price * (1 - discount), 2)
    cat = prod["Category"].values[p_idx]
    margin = np.select([cat == "Electronics", cat == "Fashion", cat == "Books"], [0.18, 0.42, 0.3], 0.28)
    cost = np.round(revenue * (1 - margin) + qty * price * discount * 0.6, 2)
    df = pd.DataFrame({
        "Order ID": [f"ORD-{100000 + i}" for i in range(n)],
        "Order Date": od.strftime("%Y-%m-%d"),
        "Customer ID": cust["customer_id"].values[c_idx],
        "Product ID": prod["Product ID"].values[p_idx],
        "Sales Channel": channel,
        "Region": cust["region"].values[c_idx],
        "Quantity": qty,
        "Unit Price": np.round(price, 2),
        "Discount": discount,
        "Revenue": revenue,
        "Cost": cost,
        "Delivery Days": np.clip(rng.poisson(4, size=n) + (channel == "Marketplace") * 2, 1, 20),
        "Customer Rating": np.clip(np.round(rng.normal(4.1, 0.7, size=n) - 0.08 * np.clip(rng.poisson(4, size=n) - 4, 0, None), 0), 1, 5),
    })
    df["Profit"] = np.round(df["Revenue"] - df["Cost"], 2)
    df = df.sort_values("Order Date").reset_index(drop=True)
    df["Order ID"] = [f"ORD-{100000 + i}" for i in range(len(df))]

    # ---- inject realistic data-quality problems ---------------------------
    m = len(df)
    idx = rng.choice(m, 25, replace=False)
    df.loc[idx, "Revenue"] = df.loc[idx, "Revenue"] * rng.uniform(8, 15, 25)  # spikes / anomalies
    df.loc[idx, "Profit"] = df.loc[idx, "Revenue"] - df.loc[idx, "Cost"]
    df = df.astype({"Region": object, "Revenue": object, "Customer Rating": object, "Sales Channel": object, "Order Date": object})
    df.loc[rng.choice(m, 120, replace=False), "Region"] = rng.choice(["north", "SOUTH ", " West", "east"], 120)
    df.loc[rng.choice(m, 60, replace=False), "Sales Channel"] = rng.choice(["online", "ONLINE", "retail store"], 60)
    df.loc[rng.choice(m, 90, replace=False), "Customer Rating"] = rng.choice(["", "N/A", "null"], 90)
    money_idx = rng.choice(m, 150, replace=False)
    df.loc[money_idx, "Revenue"] = [f"${float(v):,.2f}" for v in df.loc[money_idx, "Revenue"]]
    df.loc[rng.choice(m, 40, replace=False), "Revenue"] = ""
    alt = rng.choice(m, 100, replace=False)
    df.loc[alt, "Order Date"] = pd.to_datetime(df.loc[alt, "Order Date"]).dt.strftime("%Y/%m/%d")
    dups = df.sample(45, random_state=1)
    df = pd.concat([df, dups]).sort_index().reset_index(drop=True)
    return df


def marketing() -> list[dict]:
    rows = []
    for month in pd.date_range("2023-01-01", "2025-10-01", freq="MS"):
        for ch in ["Search Ads", "Social Media", "Email", "Affiliates"]:
            base = {"Search Ads": 42000, "Social Media": 30000, "Email": 8000, "Affiliates": 15000}[ch]
            season = 1.35 if month.month in (10, 11, 12) else 1.0
            spend = base * season * (1 + (month.year - 2023) * 0.12) * rng.uniform(0.85, 1.15)
            ctr = {"Search Ads": 0.035, "Social Media": 0.012, "Email": 0.06, "Affiliates": 0.02}[ch]
            imps = spend * rng.uniform(55, 80)
            clicks = imps * ctr * rng.uniform(0.85, 1.15)
            rows.append({"month": month.strftime("%Y-%m-%d"), "channel": ch, "spend": round(spend, 2),
                         "impressions": int(imps), "clicks": int(clicks), "leads": int(clicks * rng.uniform(0.04, 0.09)),
                         "conversions": int(clicks * rng.uniform(0.012, 0.03))})
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prod, cust = products(), customers()
    orders(prod, cust).to_csv(OUT / "orders.csv", index=False)
    with pd.ExcelWriter(OUT / "products.xlsx") as xw:
        prod.to_excel(xw, sheet_name="Products", index=False)
    db = OUT / "erp.db"
    db.unlink(missing_ok=True)
    with sqlite3.connect(db) as conn:
        cust.to_sql("customers", conn, index=False)
    (OUT / "marketing.json").write_text(json.dumps({"source": "Demo Marketing API", "data": marketing()}, indent=1))
    print(f"Sample data written to {OUT}")


if __name__ == "__main__":
    main()
