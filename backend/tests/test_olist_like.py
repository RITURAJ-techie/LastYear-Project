"""Olist-shaped batch: multi-hop integration without row inflation."""
import numpy as np
import pandas as pd


def _olist(seed=7):
    rng = np.random.default_rng(seed)
    n_cust, n_ord, n_prod, n_sell = 300, 1200, 80, 40
    cats = ["beleza_saude", "informatica_acessorios", "esporte_lazer", "moveis_decoracao"]
    customers = pd.DataFrame({"customer_id": [f"cu{i}" for i in range(n_cust)],
                              "customer_zip_code_prefix": rng.integers(1000, 1100, n_cust),
                              "customer_state": rng.choice(["SP", "RJ", "MG", "RS"], n_cust)})
    orders = pd.DataFrame({"order_id": [f"o{i}" for i in range(n_ord)], "customer_id": rng.choice(customers.customer_id, n_ord),
                           "order_status": rng.choice(["delivered", "shipped", "canceled"], n_ord, p=[.9, .07, .03]),
                           "order_purchase_timestamp": (pd.Timestamp("2017-01-01") + pd.to_timedelta(rng.integers(0, 600, n_ord), "D")).astype(str)})
    products = pd.DataFrame({"product_id": [f"p{i}" for i in range(n_prod)], "product_category_name": rng.choice(cats, n_prod),
                             "product_weight_g": rng.integers(100, 5000, n_prod), "product_length_cm": rng.integers(10, 80, n_prod)})
    translation = pd.DataFrame({"product_category_name": cats,
                                "product_category_name_english": ["health_beauty", "computers_accessories", "sports_leisure", "furniture_decor"]})
    sellers = pd.DataFrame({"seller_id": [f"s{i}" for i in range(n_sell)], "seller_state": rng.choice(["SP", "PR"], n_sell)})
    k = 1800
    items = pd.DataFrame({"order_id": rng.choice(orders.order_id, k), "order_item_id": rng.integers(1, 4, k),
                          "product_id": rng.choice(products.product_id, k), "seller_id": rng.choice(sellers.seller_id, k),
                          "price": rng.gamma(2, 60, k).round(2), "freight_value": rng.gamma(2, 8, k).round(2)})
    reviewed = orders.order_id.sample(frac=0.97, random_state=1).tolist()
    reviewed += reviewed[:12]  # 12 orders with two reviews (as in the real Olist data)
    reviews = pd.DataFrame({"review_id": [f"r{i}" for i in range(len(reviewed))], "order_id": reviewed,
                            "review_score": rng.integers(1, 6, len(reviewed))})
    geo = pd.DataFrame({"geolocation_zip_code_prefix": rng.integers(1000, 1100, 3000),
                        "geolocation_lat": rng.uniform(-30, -10, 3000), "geolocation_state": rng.choice(["SP", "RJ"], 3000)})
    files = {"olist_order_items_dataset": items, "olist_orders_dataset": orders, "olist_customers_dataset": customers,
             "olist_products_dataset": products, "product_category_name_translation": translation,
             "olist_sellers_dataset": sellers, "olist_order_reviews_dataset": reviews, "olist_geolocation_dataset": geo}
    return files, len(items)


def test_olist_like_integration(client, auth):
    files, n_items = _olist()
    payload = [("files", (f"{k}.csv", v.to_csv(index=False).encode(), "text/csv")) for k, v in files.items()]
    body = client.post("/api/datasets/upload-batch", headers=auth, files=payload).json()
    assert len(body["datasets"]) == 8 and not body["failed"]
    integ = body["integrated"]
    assert integ and integ["run"]["status"] == "success"
    # no fan-out: exactly one row per order item even though 12 orders have two reviews
    assert integ["dataset"]["row_count"] == n_items
    detail = client.get(f"/api/datasets/{integ['dataset']['id']}", headers=auth).json()
    cols = {c["name"]: c for c in detail["profile"]["columns"]}
    # multi-hop: customers (via orders) and the English category name (via products) are present
    for c in ["order_status", "customer_state", "product_category_name_english", "seller_state", "review_score"]:
        assert c in cols, c
    assert not any(c.startswith("geolocation") for c in cols)  # non-unique zip table is not a lookup
    # physical attributes are averaged, money is summed
    assert cols["product_weight_g"]["default_agg"] == "avg" and cols["product_length_cm"]["default_agg"] == "avg"
    assert cols["price"]["default_agg"] == "avg" and cols["freight_value"]["default_agg"] == "sum"
    # the integrated data answers cross-file questions
    r = client.post("/api/ai/ask", headers=auth, json={"dataset_id": integ["dataset"]["id"], "question": "total freight value by customer state"})
    assert r.status_code == 200 and r.json()["result"]["x"] == "customer_state"
