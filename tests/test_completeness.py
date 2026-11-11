from dataguard import check_completeness, check_completeness_counts


def test_complete():
    r = check_completeness(range(100), range(100))
    assert not r.alert and r.missing_count == 0 and r.missing_pct == 0


def test_missing_ids_and_alert():
    r = check_completeness(range(100), [i for i in range(100) if i not in (3, 7)], threshold_pct=1.0)
    assert r.missing_ids == (3, 7)
    assert r.missing_pct == 2.0
    assert r.alert


def test_below_threshold_no_alert():
    r = check_completeness(range(1000), range(1, 1000), threshold_pct=0.5)
    assert r.missing_ids == (0,) and not r.alert


def test_extra_rows_cannot_mask_missing():
    r = check_completeness(["a", "b"], ["a", "z"])
    assert r.missing_ids == ("b",) and r.unexpected_ids == ("z",)
    assert r.missing_pct == 50.0 and r.alert


def test_empty_expected():
    assert not check_completeness([], []).alert


def test_counts_only():
    r = check_completeness_counts(10_000, 9_800, threshold_pct=1.0)
    assert r.missing_count == 200 and r.missing_pct == 2.0 and r.alert
    assert not check_completeness_counts(10_000, 9_990, threshold_pct=1.0).alert
    assert not check_completeness_counts(10, 12).alert
