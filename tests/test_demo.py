import subprocess
import sys
from pathlib import Path

from dataguard import check_join_cardinality
from examples.synthetic_data import make_orders_and_products

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_data_has_4x_fanout():
    orders, products = make_orders_and_products()
    r = check_join_cardinality(orders, products, "product_id")
    assert r.fanout_factor == 4.0
    assert len(orders.merge(products, on="product_id", how="left")) == 4 * len(orders)


def test_demo_script_catches_multiplication():
    proc = subprocess.run([sys.executable, str(ROOT / "examples" / "demo.py")],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "fanout=4.00x [ROW MULTIPLICATION]" in proc.stdout
    assert "multiplication caught and fixed" in proc.stdout
