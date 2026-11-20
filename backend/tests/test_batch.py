"""Batch upload of several related files -> relationships -> integrated dataset -> combined insights."""
import numpy as np
import pandas as pd


def _files():
    rng = np.random.default_rng(3)
    customers = pd.DataFrame({"customer_id": [f"C{i}" for i in range(80)], "segment": rng.choice(["Retail", "Corporate"], 80),
                              "city": rng.choice(["Pune", "Delhi", "Chennai"], 80)})
    products = pd.DataFrame({"product_id": [f"P{i}" for i in range(25)], "category": rng.choice(["Tech", "Home", "Books"], 25),
                             "list_price": rng.uniform(5, 200, 25).round(2)})
    n = 900
    orders = pd.DataFrame({"order_id": [f"O{i}" for i in range(n)],
                           "order_date": pd.date_range("2023-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
                           "customer_id": rng.choice(customers.customer_id, n), "product_id": rng.choice(products.product_id, n),
                           "quantity": rng.integers(1, 6, n), "revenue": rng.gamma(2, 80, n).round(2)})
    enc = lambda df: df.to_csv(index=False).encode()  # noqa: E731
    return [("files", ("orders.csv", enc(orders), "text/csv")), ("files", ("customers.csv", enc(customers), "text/csv")),
            ("files", ("products.csv", enc(products), "text/csv")), ("files", ("notes.pdf", b"%PDF-1.4", "application/pdf"))]


def test_batch_upload_and_combined_insights(client, auth):
    r = client.post("/api/datasets/upload-batch", headers=auth, files=_files(), data={"auto_integrate": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["datasets"]) == 3
    assert [f["file"] for f in body["failed"]] == ["notes.pdf"]  # bad file reported, batch continues
    pairs = {(x["from_column"], x["to_column"]) for x in body["relationships"]}
    assert {("customer_id", "customer_id"), ("product_id", "product_id")} <= pairs
    integ = body["integrated"]
    assert integ and integ["run"]["status"] == "success"
    assert integ["dataset"]["row_count"] == 900 and integ["dataset"]["name"].startswith("Integrated: orders")
    detail = client.get(f"/api/datasets/{integ['dataset']['id']}", headers=auth).json()
    cols = {c["name"] for c in detail["profile"]["columns"]}
    assert {"segment", "category", "list_price"} <= cols  # dimension attributes joined in
    ids = body["insight_dataset_ids"]
    assert len(ids) == 4

    r = client.get(f"/api/insights/combined?ids={','.join(map(str, ids))}", headers=auth)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["totals"]["datasets"] == 4 and c["totals"]["insights"] > 0
    assert len(c["datasets"]) == 4 and all(d["error"] is None for d in c["datasets"])
    assert c["top_insights"] and all("dataset_name" in i for i in c["top_insights"])
    assert len(c["relationships"]) >= 2


def test_batch_without_integration_and_limits(client, auth):
    r = client.post("/api/datasets/upload-batch", headers=auth, files=_files()[:2], data={"auto_integrate": "false"})
    assert r.status_code == 200 and r.json()["integrated"] is None
    too_many = [("files", (f"f{i}.csv", b"a,b\n1,2\n", "text/csv")) for i in range(21)]
    assert client.post("/api/datasets/upload-batch", headers=auth, files=too_many).status_code == 400
    assert client.get("/api/insights/combined?ids=abc", headers=auth).status_code == 400
