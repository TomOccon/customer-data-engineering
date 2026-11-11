import math

import pandas as pd
import pytest

from dataguard import ReconciliationError, reconcile_counts, reconcile_frames, reconcile_sums


def test_counts_within_tolerance():
    assert reconcile_counts(10_000, 10_005, tolerance=0.001).passed


def test_counts_outside_tolerance():
    r = reconcile_counts(1000, 4000)
    assert not r.passed
    assert r.delta == 3000
    assert r.delta_pct == pytest.approx(3.0)


def test_zero_source():
    assert reconcile_counts(0, 0).passed
    r = reconcile_counts(0, 5)
    assert not r.passed and math.isinf(r.delta_pct)


def test_sums():
    assert reconcile_sums(100.0, 100.05, tolerance=0.001).passed
    assert not reconcile_sums(100.0, 140.0, tolerance=0.001).passed


def test_negative_tolerance_rejected():
    with pytest.raises(ValueError):
        reconcile_counts(1, 1, tolerance=-1)


def test_frames_report_and_raise():
    src = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
    ok = reconcile_frames(src, src.copy(), sum_columns=["v"])
    assert ok.passed
    ok.raise_if_failed()

    doubled = pd.concat([src, src], ignore_index=True)
    bad = reconcile_frames(src, doubled, sum_columns=["v"])
    assert not bad.passed
    assert len(bad.failures) == 2
    with pytest.raises(ReconciliationError):
        bad.raise_if_failed()
