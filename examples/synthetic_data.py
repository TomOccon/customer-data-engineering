"""Synthetic data generators. Everything here is fictional."""

from __future__ import annotations

import random

import pandas as pd


def make_orders_and_products(n_orders: int = 1000, n_products: int = 250,
                             versions_per_product: int = 4, seed: int = 7):
    """Orders (one row per order) and a product dimension with repeated keys.

    The product table keeps `versions_per_product` historical rows per product_id.
    Joining orders to it on product_id multiplies every order by that factor.
    """
    rng = random.Random(seed)
    orders = pd.DataFrame({
        "order_id": range(1, n_orders + 1),
        "product_id": [rng.randint(1, n_products) for _ in range(n_orders)],
        "revenue": [round(rng.uniform(5, 500), 2) for _ in range(n_orders)],
    })
    products = pd.DataFrame([
        {"product_id": pid, "category": f"category_{pid % 10}", "version": v,
         "updated_at": f"2026-0{v}-01"}
        for pid in range(1, n_products + 1)
        for v in range(1, versions_per_product + 1)
    ])
    return orders, products


def make_dataset_metadata() -> pd.DataFrame:
    return pd.DataFrame({
        "name": ["sales_daily", "sales_daily_copy", "legacy_export", "web_events",
                 "tmp_scratch", "finance_monthly"],
        "owner": ["ana@example.com", "ana@example.com", None, "raj@example.com", "", "lee@example.com"],
        "rows": [2_000_000, 2_000_000, 8_000_000, 120_000_000, 500_000, 40_000],
        "last_updated": ["2026-11-01", "2026-03-01", "2025-01-15", "2026-11-10",
                         "2025-06-01", "2026-10-31"],
        "downstream_count": [12, 0, 0, 5, 0, 3],
        "duplicate_of": [None, "sales_daily", None, None, None, None],
    })
