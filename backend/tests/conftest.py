import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="insightflow-test-")
os.environ["INSIGHTFLOW_DATA_DIR"] = _tmp
os.environ["INSIGHTFLOW_SEED_DEMO"] = "false"
os.environ["INSIGHTFLOW_SCHEDULER"] = "false"
os.environ["INSIGHTFLOW_AI_DISABLED"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/register", json={"name": "Tester", "email": "tester@example.com", "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def make_sales_csv(n: int = 600) -> bytes:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    region = rng.choice(["North", "South", "East", "West"], n).astype(object)
    region[:20] = "north "  # inconsistent label + whitespace
    units = rng.integers(1, 10, n)
    price = rng.uniform(10, 100, n).round(2)
    revenue = (units * price).round(2).astype(object)
    revenue[20:30] = [f"${v:,.2f}" for v in revenue[20:30]]  # currency strings
    revenue[30:35] = "N/A"
    df = pd.DataFrame({"Order Date": dates.strftime("%Y-%m-%d"), "Region": region, "Units": units,
                       "Unit Price": price, "Revenue": revenue, "Customer ID": [f"C{i % 50}" for i in range(n)]})
    df = pd.concat([df, df.head(5)])  # duplicates
    return df.to_csv(index=False).encode()
