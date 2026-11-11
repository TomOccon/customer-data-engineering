"""Connector completeness checks.

Failure mode prevented: a connector reports success while silently dropping
records (for example a filter pattern that misses one record subtype).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CompletenessResult:
    expected_count: int
    received_count: int
    missing_count: int
    missing_pct: float        # percent of expected, 0 to 100
    threshold_pct: float
    alert: bool               # True when missing_pct > threshold_pct
    missing_ids: tuple = ()   # in expected, not received
    unexpected_ids: tuple = ()  # received, not in expected

    def summary(self) -> str:
        state = "ALERT" if self.alert else "ok"
        return (
            f"[{state}] expected={self.expected_count} received={self.received_count} "
            f"missing={self.missing_count} ({self.missing_pct:.2f}%, threshold {self.threshold_pct:.2f}%)"
        )


def _pct_missing(expected: int, received: int) -> tuple[int, float]:
    missing = max(expected - received, 0)
    pct = (missing / expected * 100.0) if expected else 0.0
    return missing, pct


def check_completeness_counts(expected_count: int, received_count: int,
                              threshold_pct: float = 0.5) -> CompletenessResult:
    """Count-only check, for when you have a direct source count but not the id list."""
    missing, pct = _pct_missing(expected_count, received_count)
    return CompletenessResult(expected_count, received_count, missing, pct, threshold_pct,
                              alert=pct > threshold_pct)


def check_completeness(expected_ids: Iterable, received_ids: Iterable,
                       threshold_pct: float = 0.5) -> CompletenessResult:
    """Compare ids from an unfiltered source query against what the connector delivered."""
    expected, received = set(expected_ids), set(received_ids)
    missing_ids = tuple(sorted(expected - received, key=str))
    unexpected = tuple(sorted(received - expected, key=str))
    # Use the id diff, not the count difference, so extra rows cannot mask missing ones.
    missing_count = len(missing_ids)
    pct = (missing_count / len(expected) * 100.0) if expected else 0.0
    return CompletenessResult(len(expected), len(received), missing_count, pct, threshold_pct,
                              alert=pct > threshold_pct, missing_ids=missing_ids,
                              unexpected_ids=unexpected)
