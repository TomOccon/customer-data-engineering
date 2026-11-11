import pandas as pd
import pytest

from dataguard import (
    JoinFanoutError,
    assert_no_fanout,
    check_join_cardinality,
    composite_key,
    dedupe_latest,
)


def _frames():
    left = pd.DataFrame({"k": [1, 1, 2, 3, 4], "a": range(5)})
    right = pd.DataFrame({"k": [1, 1, 1, 2, 9], "b": range(5)})
    return left, right


@pytest.mark.parametrize("how", ["left", "inner"])
def test_prediction_matches_real_merge(how):
    left, right = _frames()
    report = check_join_cardinality(left, right, "k", how=how)
    assert report.predicted_rows == len(left.merge(right, on="k", how=how))


def test_report_fields_and_flag():
    left, right = _frames()
    r = check_join_cardinality(left, right, ["k"], how="left")
    assert r.left_rows == 5 and r.right_rows == 5
    assert r.left_distinct_keys == 4 and r.right_distinct_keys == 3
    assert r.right_dup_factor == pytest.approx(5 / 3)
    assert r.multiplies_rows is True
    assert r.fanout_factor > 1


def test_unique_right_does_not_multiply():
    left, _ = _frames()
    right = pd.DataFrame({"k": [1, 2, 3], "b": [1, 2, 3]})
    r = check_join_cardinality(left, right, "k")
    assert not r.multiplies_rows and r.predicted_rows == 5 and r.fanout_factor == 1.0


def test_four_x_fanout():
    left = pd.DataFrame({"k": range(100)})
    right = pd.DataFrame({"k": list(range(100)) * 4, "v": range(400)})
    r = check_join_cardinality(left, right, "k")
    assert r.fanout_factor == pytest.approx(4.0)
    with pytest.raises(JoinFanoutError):
        assert_no_fanout(left, right, "k")
    assert assert_no_fanout(left, right, "k", max_fanout=4.0).predicted_rows == 400


def test_composite_keys_and_null_keys_predicted():
    left = pd.DataFrame({"a": [1, 1, None], "b": ["x", "y", "z"]})
    right = pd.DataFrame({"a": [1, 1, None, None], "b": ["x", "x", "z", "z"]})
    r = check_join_cardinality(left, right, ["a", "b"], how="left")
    assert r.predicted_rows == len(left.merge(right, on=["a", "b"], how="left"))


def test_empty_sides():
    left, right = _frames()
    assert check_join_cardinality(left.iloc[0:0], right, "k").predicted_rows == 0
    assert check_join_cardinality(left, right.iloc[0:0], "k", how="left").predicted_rows == 5
    assert check_join_cardinality(left, right.iloc[0:0], "k", how="inner").predicted_rows == 0


def test_bad_args():
    left, right = _frames()
    with pytest.raises(ValueError):
        check_join_cardinality(left, right, "k", how="outer")
    with pytest.raises(KeyError):
        check_join_cardinality(left, right, "nope")


def test_dedupe_latest():
    df = pd.DataFrame({"k": [1, 1, 2], "v": [1, 2, 1], "x": ["old", "new", "only"]})
    out = dedupe_latest(df, "k", "v")
    assert sorted(out["x"]) == ["new", "only"]


def test_composite_key_deterministic():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert composite_key(df, ["a", "b"]).tolist() == composite_key(df.copy(), ["a", "b"]).tolist()
    assert composite_key(df, ["a", "b"], length=8).str.len().eq(8).all()


def test_composite_key_separator_ambiguity():
    df = pd.DataFrame({"a": ["ab", "a"], "b": ["c", "bc"]})
    k = composite_key(df, ["a", "b"])
    assert k[0] != k[1]


def test_composite_key_null_safe():
    df = pd.DataFrame({"a": [None, "None", "", float("nan")], "b": ["x", "x", "x", "x"]})
    k = composite_key(df, ["a", "b"])
    assert k[0] == k[3]  # None and NaN are both null
    assert len({k[0], k[1], k[2]}) == 3  # null, "None" and "" all differ
