"""Demo: a silent 4x row multiplication, caught before and after the join.

Run from the repo root:  python examples/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synthetic_data import make_orders_and_products  # noqa: E402

from dataguard import (  # noqa: E402
    check_join_cardinality,
    dedupe_latest,
    reconcile_frames,
)


def main() -> int:
    orders, products = make_orders_and_products()
    print(f"orders={len(orders)} products={len(products)} (4 rows per product_id)\n")

    print("Step 1: pre-join cardinality check")
    report = check_join_cardinality(orders, products, "product_id", how="left")
    print(" ", report.summary())

    print("\nStep 2: run the naive join anyway and reconcile")
    naive = orders.merge(products, on="product_id", how="left")
    before = reconcile_frames(orders, naive, sum_columns=["revenue"])
    for r in before.results:
        print(" ", r)

    print("\nStep 3: dedupe the dimension to one row per key, then re-check")
    products_1 = dedupe_latest(products, "product_id", order_by="version")
    fixed_report = check_join_cardinality(orders, products_1, "product_id", how="left")
    print(" ", fixed_report.summary())
    fixed = orders.merge(products_1, on="product_id", how="left")
    after = reconcile_frames(orders, fixed, sum_columns=["revenue"])
    for r in after.results:
        print(" ", r)

    caught = report.multiplies_rows and not before.passed and after.passed
    print("\nRESULT:", "multiplication caught and fixed" if caught else "unexpected outcome")
    return 0 if caught else 1


if __name__ == "__main__":
    raise SystemExit(main())
