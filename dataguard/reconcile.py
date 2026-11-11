"""Source-to-target reconciliation.

Failure mode prevented: a pipeline "succeeds" while output rows or totals drift
from the source (silent row multiplication, truncated connectors).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


class ReconciliationError(AssertionError):
    """Raised when one or more reconciliation checks fail."""


@dataclass(frozen=True)
class ReconcileResult:
    metric: str
    source: float
    output: float
    delta: float
    delta_pct: float  # relative to source; inf when source is 0 and output is not
    tolerance: float
    passed: bool

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.metric}: source={self.source:g} output={self.output:g} "
            f"delta={self.delta:+g} ({self.delta_pct:.4%}, tolerance {self.tolerance:.4%})"
        )


@dataclass(frozen=True)
class ReconcileReport:
    results: tuple[ReconcileResult, ...]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> tuple[ReconcileResult, ...]:
        return tuple(r for r in self.results if not r.passed)

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise ReconciliationError("\n".join(str(r) for r in self.failures))


def _compare(metric: str, source: float, output: float, tolerance: float) -> ReconcileResult:
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    delta = output - source
    if source == 0:
        delta_pct = 0.0 if output == 0 else math.inf
    else:
        delta_pct = abs(delta) / abs(source)
    return ReconcileResult(
        metric=metric,
        source=source,
        output=output,
        delta=delta,
        delta_pct=delta_pct,
        tolerance=tolerance,
        passed=delta_pct <= tolerance,
    )


def reconcile_counts(source_count: int, output_count: int, tolerance: float = 0.001,
                     metric: str = "row_count") -> ReconcileResult:
    """Compare row counts. Tolerance is a fraction (0.001 = 0.1 percent)."""
    return _compare(metric, source_count, output_count, tolerance)


def reconcile_sums(source_sum: float, output_sum: float, tolerance: float = 0.001,
                   metric: str = "sum") -> ReconcileResult:
    """Compare a column total between source and output."""
    return _compare(metric, float(source_sum), float(output_sum), tolerance)


def reconcile_frames(source: pd.DataFrame, output: pd.DataFrame,
                     sum_columns: Iterable[str] = (), tolerance: float = 0.001) -> ReconcileReport:
    """Reconcile row count plus the total of each column in sum_columns."""
    results = [reconcile_counts(len(source), len(output), tolerance)]
    for col in sum_columns:
        results.append(
            reconcile_sums(source[col].sum(), output[col].sum(), tolerance, metric=f"sum({col})")
        )
    return ReconcileReport(tuple(results))
