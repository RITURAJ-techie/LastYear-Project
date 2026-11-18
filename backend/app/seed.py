"""Create a demo account populated with an integrated multi-source retail warehouse."""
from __future__ import annotations

import json
import logging
import os

import pandas as pd

from .auth import hash_password
from .config import SAMPLE_DIR
from .database import Dataset, SessionLocal, User
from .etl import extract
from .services import create_dataset

log = logging.getLogger("insightflow.seed")
DEMO_EMAIL = "demo@insightflow.ai"
DEMO_PASSWORD = "demo1234"


def ensure_sample_files() -> None:
    if not (SAMPLE_DIR / "orders.csv").exists():
        from importlib import import_module
        import sys
        sys.path.insert(0, str(SAMPLE_DIR.parent / "scripts"))
        import_module("generate_sample_data").main()


def seed_demo() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == DEMO_EMAIL).first():
            return
        ensure_sample_files()
        log.info("Seeding demo workspace...")
        user = User(name="Demo Analyst", email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.commit()
        port = os.getenv("PORT", "8000")

        orders, _ = create_dataset(db, user, "Sales Orders", "file",
                                   {"path": str(SAMPLE_DIR / "orders.csv"), "original_name": "orders.csv"},
                                   "Transactional orders exported from the POS/e-commerce system (CSV)")
        products, _ = create_dataset(db, user, "Product Catalog", "file",
                                     {"path": str(SAMPLE_DIR / "products.xlsx"), "original_name": "products.xlsx"},
                                     "Product master data maintained by merchandising (Excel)")
        customers, _ = create_dataset(db, user, "Customers (ERP)", "sql",
                                      {"connection_url": f"sqlite:///{SAMPLE_DIR / 'erp.db'}", "table": "customers"},
                                      "Customer master table pulled from the ERP database (SQL)", refresh_interval_minutes=1440)
        mk = json.loads((SAMPLE_DIR / "marketing.json").read_text())
        create_dataset(db, user, "Marketing Performance", "api",
                       {"url": f"http://127.0.0.1:{port}/api/demo-source/marketing", "record_path": "data"},
                       "Monthly campaign metrics from the marketing platform REST API", raw=pd.DataFrame(mk["data"]))

        # Integrated, modelled dataset: orders enriched with product & customer attributes
        def col(ds: Dataset, needle: str) -> str:
            return next(c["name"] for c in ds.profile["columns"] if needle in c["name"])

        from .routers.warehouse import JoinIn, JoinSpec, join
        join(JoinIn(name="Sales 360", base_dataset_id=orders.id, description="Orders joined with product and customer master data",
                    joins=[JoinSpec(dataset_id=products.id, left_column=col(orders, "product_id"), right_column=col(products, "product_id")),
                           JoinSpec(dataset_id=customers.id, left_column=col(orders, "customer_id"), right_column=col(customers, "customer_id"))]),
             user=user, db=db)
        log.info("Demo workspace ready (login: %s / %s)", DEMO_EMAIL, DEMO_PASSWORD)
    except (extract.ExtractError, StopIteration) as exc:
        log.warning("Demo seeding incomplete: %s", exc)
    finally:
        db.close()
