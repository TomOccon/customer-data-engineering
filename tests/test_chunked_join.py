import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from dataguard import chunked_join


def _norm(df):
    cols = sorted(df.columns)
    return df[cols].sort_values(cols, na_position="last").reset_index(drop=True)


@pytest.fixture
def data():
    rng = np.random.RandomState(1)
    left = pd.DataFrame({
        "k1": rng.randint(0, 200, 3000),
        "k2": rng.choice(["a", "b", "c"], 3000),
        "lval": rng.rand(3000),
    })
    right = pd.DataFrame({
        "k1": rng.randint(100, 300, 2000),
        "k2": rng.choice(["a", "b", "c", "d"], 2000),
        "rval": rng.rand(2000),
        "unused": "x",
    })
    return left, right


@pytest.mark.parametrize("how", ["inner", "left"])
@pytest.mark.parametrize("n", [1, 7, 16])
def test_matches_naive_join(data, how, n):
    left, right = data
    naive = left.merge(right, on=["k1", "k2"], how=how)
    got = chunked_join(left, right, on=["k1", "k2"], how=how, n_partitions=n)
    assert len(got) == len(naive)
    assert_frame_equal(_norm(got), _norm(naive), check_dtype=False)


def test_column_pruning(data):
    left, right = data
    got = chunked_join(left, right, on=["k1", "k2"], how="inner", right_columns=["rval"])
    assert "unused" not in got.columns
    naive = left.merge(right.drop(columns="unused"), on=["k1", "k2"], how="inner")
    assert_frame_equal(_norm(got), _norm(naive), check_dtype=False)


def test_pre_aggregation_equals_naive_on_aggregated(data):
    left, right = data
    agg = right.groupby(["k1", "k2"], as_index=False).agg({"rval": "sum"})
    naive = left.merge(agg, on=["k1", "k2"], how="left")
    got = chunked_join(left, right[["k1", "k2", "rval"]], on=["k1", "k2"], how="left",
                       n_partitions=5, right_agg={"rval": "sum"})
    assert len(got) == len(left)  # aggregation removes the fanout
    assert_frame_equal(_norm(got), _norm(naive), check_dtype=False)


def test_null_keys_match_like_pandas():
    left = pd.DataFrame({"k": ["a", None, "b"], "x": [1, 2, 3]})
    right = pd.DataFrame({"k": [None, "b", "b"], "y": [10, 20, 30]})
    naive = left.merge(right, on="k", how="left")
    got = chunked_join(left, right, on="k", how="left", n_partitions=3)
    assert_frame_equal(_norm(got), _norm(naive), check_dtype=False)


def test_empty_result():
    left = pd.DataFrame({"k": [1, 2], "x": [1, 2]})
    right = pd.DataFrame({"k": [8, 9], "y": [1, 2]})
    assert len(chunked_join(left, right, on="k", how="inner")) == 0


def test_dtype_mismatch_rejected():
    left = pd.DataFrame({"k": [1, 2]})
    right = pd.DataFrame({"k": [1.0, 2.0]})
    with pytest.raises(ValueError):
        chunked_join(left, right, on="k")


def test_bad_args():
    df = pd.DataFrame({"k": [1]})
    with pytest.raises(ValueError):
        chunked_join(df, df, on="k", how="outer")
    with pytest.raises(ValueError):
        chunked_join(df, df, on="k", n_partitions=0)
