from conftest import make_sales_csv


def test_auth_required(client):
    assert client.get("/api/datasets").status_code == 401


def test_login_flow(client, auth):
    r = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "secret123"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"email": "tester@example.com", "password": "wrong"}).status_code == 401


def test_end_to_end(client, auth):
    r = client.post("/api/datasets/upload", headers=auth, files={"file": ("sales.csv", make_sales_csv(), "text/csv")},
                    data={"name": "Test Sales"})
    assert r.status_code == 200, r.text
    created = r.json()[0]
    assert created["run"]["status"] == "success"
    ds = created["dataset"]
    assert ds["row_count"] == 600 and ds["primary_time"] == "order_date"
    did = ds["id"]

    detail = client.get(f"/api/datasets/{did}", headers=auth).json()
    assert detail["quality"]["issues"]["duplicates_removed"] == 5

    for ep in ["summary", "distributions", "correlations", "trends", "anomalies", "drivers", "clusters", "insights"]:
        r = client.get(f"/api/datasets/{did}/analysis/{ep}", headers=auth)
        assert r.status_code == 200, (ep, r.text)
    ins = client.get(f"/api/datasets/{did}/analysis/insights", headers=auth).json()
    assert ins["insights"] and ins["summary"]

    dashes = client.get(f"/api/dashboards?dataset_id={did}", headers=auth).json()
    assert len(dashes) == 1 and dashes[0]["widgets"]
    for w in dashes[0]["widgets"]:
        r = client.post(f"/api/datasets/{did}/widget-data", headers=auth,
                        json={"widget": w, "filters": [{"column": "region", "op": "in", "value": ["North"]}]})
        assert r.status_code == 200, (w["type"], r.text)

    r = client.post("/api/ai/ask", headers=auth, json={"dataset_id": did, "question": "total revenue by region"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "rules" and body["result"]["x"] == "region"

    r = client.post("/api/warehouse/sql", headers=auth, json={"sql": f"select count(*) as n from {ds['table_name']}"})
    assert r.status_code == 200 and r.json()["rows"][0]["n"] == 600

    assert client.get(f"/api/datasets/{did}/export?format=csv", headers=auth).status_code == 200
    assert client.get(f"/api/datasets/{did}/analysis/report", headers=auth).status_code == 200
    assert client.post(f"/api/datasets/{did}/refresh", headers=auth).status_code == 200
    assert len(client.get(f"/api/datasets/{did}/runs", headers=auth).json()) == 2


def test_isolation_between_users(client, auth):
    r = client.post("/api/auth/register", json={"name": "Other", "email": "other@example.com", "password": "secret123"})
    other = {"Authorization": f"Bearer {r.json()['token']}"}
    mine = client.get("/api/datasets", headers=auth).json()
    assert mine
    assert client.get(f"/api/datasets/{mine[0]['id']}", headers=other).status_code == 404
    r = client.post("/api/warehouse/sql", headers=other, json={"sql": f"select * from {mine[0]['table_name']}"})
    assert r.status_code == 400


def test_sql_source(client, auth, tmp_path):
    import sqlite3

    db = tmp_path / "src.db"
    with sqlite3.connect(db) as conn:
        conn.execute("create table items (id integer, name text, price real)")
        conn.executemany("insert into items values (?,?,?)", [(i, f"item{i}", i * 1.5) for i in range(30)])
    url = f"sqlite:///{db}"
    assert "items" in client.post("/api/datasets/sql/test", headers=auth, json={"connection_url": url}).json()["tables"]
    r = client.post("/api/datasets/sql", headers=auth, json={"name": "Items", "connection_url": url, "table": "items"})
    assert r.status_code == 200 and r.json()["dataset"]["row_count"] == 30
