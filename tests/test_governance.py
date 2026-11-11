import pytest

from dataguard import GovernanceConfig, audit_datasets, estimate_savings
from examples.synthetic_data import make_dataset_metadata

AS_OF = "2026-11-11"


@pytest.fixture
def audited():
    return audit_datasets(make_dataset_metadata(), as_of=AS_OF).set_index("name")


def test_flags(audited):
    assert audited.loc["legacy_export", "is_orphaned"]
    assert audited.loc["tmp_scratch", "is_orphaned"]  # blank string owner
    assert not audited.loc["sales_daily", "is_orphaned"]
    assert audited.loc["sales_daily_copy", "is_duplicate"]
    assert audited.loc["web_events", "is_oversized"]
    assert not audited.loc["sales_daily", "is_duplicate"]


def test_stale_requires_no_downstream(audited):
    assert audited.loc["legacy_export", "is_stale"]
    assert audited.loc["tmp_scratch", "is_stale"]
    assert audited.loc["sales_daily_copy", "is_stale"]  # 255 days, no downstream
    assert not audited.loc["web_events", "is_stale"]


def test_old_but_used_is_not_stale():
    df = make_dataset_metadata()
    df.loc[df["name"] == "legacy_export", "downstream_count"] = 2
    out = audit_datasets(df, as_of=AS_OF).set_index("name")
    assert not out.loc["legacy_export", "is_stale"]


def test_config_thresholds():
    cfg = GovernanceConfig(stale_days=10, oversized_rows=1_000_000)
    out = audit_datasets(make_dataset_metadata(), cfg, as_of=AS_OF).set_index("name")
    assert out.loc["sales_daily_copy", "is_stale"]
    assert out.loc["sales_daily", "is_oversized"]


def test_flags_column(audited):
    assert audited.loc["legacy_export", "flags"] == "orphaned,stale"
    assert audited.loc["finance_monthly", "flags"] == ""


def test_input_not_mutated():
    df = make_dataset_metadata()
    cols = list(df.columns)
    audit_datasets(df, as_of=AS_OF)
    assert list(df.columns) == cols


def test_missing_columns():
    with pytest.raises(KeyError):
        audit_datasets(make_dataset_metadata().drop(columns=["owner"]))


def test_savings_counts_each_dataset_once():
    audited = audit_datasets(make_dataset_metadata(), as_of=AS_OF)
    s = estimate_savings(audited, GovernanceConfig(cost_per_million_rows=2.0))
    # duplicate: sales_daily_copy 2M. stale only: legacy_export 8M + tmp_scratch 0.5M.
    assert s["duplicate_rows"] == 2_000_000
    assert s["stale_rows"] == 8_500_000
    assert s["reclaimable_rows"] == 10_500_000
    assert s["estimated_savings"] == pytest.approx(21.0)
    assert s["duplicate_datasets"] == 1 and s["stale_datasets"] == 2


def test_savings_zero_cost():
    audited = audit_datasets(make_dataset_metadata(), as_of=AS_OF)
    assert estimate_savings(audited, GovernanceConfig(cost_per_million_rows=0))["estimated_savings"] == 0
