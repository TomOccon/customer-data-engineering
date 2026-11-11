"""Pre-join cardinality checks and a deterministic composite key.

Failure mode prevented: a join on a non-unique key multiplies rows and inflates
every downstream sum, with no error raised.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import pandas as pd


class JoinFanoutError(AssertionError):
    """Raised when a join would multiply rows beyond the allowed factor."""


@dataclass(frozen=True)
class JoinCardinalityReport:
    keys: tuple[str, ...]
    how: str
    left_rows: int
    right_rows: int
    left_distinct_keys: int
    right_distinct_keys: int
    left_dup_factor: float   # rows per distinct key, left side
    right_dup_factor: float  # rows per distinct key, right side
    predicted_rows: int      # exact row count the join will produce
    fanout_factor: float     # predicted_rows / left_rows
    multiplies_rows: bool    # True when output would exceed left row count

    def summary(self) -> str:
        flag = "ROW MULTIPLICATION" if self.multiplies_rows else "ok"
        return (
            f"join on {list(self.keys)} ({self.how}): left={self.left_rows} "
            f"right={self.right_rows} right_dup_factor={self.right_dup_factor:.2f} "
            f"predicted_rows={self.predicted_rows} fanout={self.fanout_factor:.2f}x [{flag}]"
        )


def _counts(df: pd.DataFrame, keys: list[str], name: str) -> pd.DataFrame:
    return df.groupby(keys, dropna=False).size().reset_index(name=name)


def check_join_cardinality(left: pd.DataFrame, right: pd.DataFrame,
                           keys: str | Sequence[str], how: str = "left") -> JoinCardinalityReport:
    """Predict the output of left.merge(right, on=keys, how=how) without running it.

    Supports how="left" and how="inner". Null keys match each other, as in pandas merge.
    """
    key_list = [keys] if isinstance(keys, str) else list(keys)
    if how not in ("left", "inner"):
        raise ValueError("how must be 'left' or 'inner'")
    for side, df in (("left", left), ("right", right)):
        missing = [k for k in key_list if k not in df.columns]
        if missing:
            raise KeyError(f"{side} frame is missing key columns: {missing}")

    left_rows, right_rows = len(left), len(right)
    if left_rows == 0:
        predicted, l_distinct, r_distinct = 0, 0, (len(_counts(right, key_list, "_r")) if right_rows else 0)
    elif right_rows == 0:
        predicted = left_rows if how == "left" else 0
        l_distinct, r_distinct = len(_counts(left, key_list, "_l")), 0
    else:
        lc = _counts(left, key_list, "_l")
        rc = _counts(right, key_list, "_r")
        l_distinct, r_distinct = len(lc), len(rc)
        m = lc.merge(rc, on=key_list, how="left")
        r = m["_r"].fillna(0)
        if how == "left":
            r = r.clip(lower=1)
        predicted = int((m["_l"] * r).sum())

    fanout = predicted / left_rows if left_rows else 1.0
    return JoinCardinalityReport(
        keys=tuple(key_list),
        how=how,
        left_rows=left_rows,
        right_rows=right_rows,
        left_distinct_keys=l_distinct,
        right_distinct_keys=r_distinct,
        left_dup_factor=(left_rows / l_distinct) if l_distinct else 0.0,
        right_dup_factor=(right_rows / r_distinct) if r_distinct else 0.0,
        predicted_rows=predicted,
        fanout_factor=fanout,
        multiplies_rows=predicted > left_rows,
    )


def assert_no_fanout(left: pd.DataFrame, right: pd.DataFrame, keys: str | Sequence[str],
                     how: str = "left", max_fanout: float = 1.0) -> JoinCardinalityReport:
    """Run the cardinality check and raise JoinFanoutError if fanout exceeds max_fanout."""
    report = check_join_cardinality(left, right, keys, how)
    if report.fanout_factor > max_fanout:
        raise JoinFanoutError(report.summary())
    return report


def dedupe_latest(df: pd.DataFrame, keys: str | Sequence[str], order_by: str) -> pd.DataFrame:
    """Keep the row with the highest order_by per key (the ROW_NUMBER() ... rn = 1 pattern)."""
    key_list = [keys] if isinstance(keys, str) else list(keys)
    return (
        df.sort_values(order_by, ascending=False, kind="stable")
        .drop_duplicates(subset=key_list, keep="first")
        .sort_index()
    )


_SEP_LEN = "{}:{}"
_NULL = "\x00NULL"


def composite_key(df: pd.DataFrame, columns: Sequence[str], length: int = 16) -> pd.Series:
    """Deterministic, null-safe hash of several columns.

    - Same inputs always give the same hash (sha256, no process-level salt).
    - Each value is length-prefixed, so ("ab", "c") and ("a", "bc") differ.
    - Nulls get a reserved token, so None differs from "None" and from "".
    - Column order is the order given. Values are compared by str(), so 1 and "1"
      collide; cast columns to a common type first.
    """
    if not 1 <= length <= 64:
        raise ValueError("length must be between 1 and 64")
    cols = list(columns)

    def one(values: tuple) -> str:
        parts = [_NULL if pd.isna(v) else str(v) for v in values]
        payload = "|".join(_SEP_LEN.format(len(p), p) for p in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]

    hashes = [one(row) for row in df[cols].itertuples(index=False, name=None)]
    return pd.Series(hashes, index=df.index, name="composite_key", dtype="object")
