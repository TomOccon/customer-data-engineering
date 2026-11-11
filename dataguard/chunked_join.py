"""Memory-bounded join.

Failure mode prevented: "Join did not fit in memory" when volume grows from dev
scale to production scale. Three levers: drop columns and rows you do not need,
aggregate the larger side to the join grain, and join one key partition at a time.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd


def _restrict_to_keys(df: pd.DataFrame, other: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Keep only rows of df whose key appears in other. Distinct keys, so no fanout."""
    return df.merge(other[keys].drop_duplicates(), on=keys, how="inner")


def chunked_join(left: pd.DataFrame, right: pd.DataFrame, on: str | Sequence[str],
                 how: str = "inner", n_partitions: int = 8,
                 left_columns: Sequence[str] | None = None,
                 right_columns: Sequence[str] | None = None,
                 right_agg: Mapping[str, str] | None = None) -> pd.DataFrame:
    """Join left and right by hashing keys into n_partitions and joining each in turn.

    Result rows equal left.merge(right, on=on, how=how) (row order may differ).
    - left_columns / right_columns: columns to keep (join keys are always kept).
    - right_agg: e.g. {"amount": "sum"}. Aggregates right to one row per key
      before joining. This changes semantics on purpose; compare against a naive
      join of the same aggregated frame.
    Peak memory is roughly one partition's join output instead of the whole result.
    """
    keys = [on] if isinstance(on, str) else list(on)
    if how not in ("inner", "left"):
        raise ValueError("how must be 'inner' or 'left'")
    if n_partitions < 1:
        raise ValueError("n_partitions must be >= 1")
    for k in keys:
        if k not in left.columns or k not in right.columns:
            raise KeyError(f"join key {k!r} missing from one side")
        if left[k].dtype != right[k].dtype:
            # Equal values hash differently across dtypes, which would drop matches.
            raise ValueError(f"key {k!r} dtype differs: {left[k].dtype} vs {right[k].dtype}")

    if left_columns is not None:
        left = left[keys + [c for c in left_columns if c not in keys]]
    if right_columns is not None:
        right = right[keys + [c for c in right_columns if c not in keys]]
    if right_agg:
        right = right.groupby(keys, dropna=False, as_index=False).agg(dict(right_agg))

    # Pre-filter: rows that cannot match are dropped before the expensive step.
    right = _restrict_to_keys(right, left, keys)
    if how == "inner":
        left = _restrict_to_keys(left, right, keys)

    left_part = pd.util.hash_pandas_object(left[keys], index=False).to_numpy() % n_partitions
    right_part = pd.util.hash_pandas_object(right[keys], index=False).to_numpy() % n_partitions
    left_groups = dict(tuple(left.groupby(left_part)))
    right_groups = dict(tuple(right.groupby(right_part)))

    pieces = []
    for p, lpart in left_groups.items():
        rpart = right_groups.get(p, right.iloc[0:0])
        pieces.append(lpart.merge(rpart, on=keys, how=how))
        # lpart/rpart go out of scope each pass; only the joined piece is retained.
    if not pieces:
        return left.iloc[0:0].merge(right.iloc[0:0], on=keys, how=how)
    return pd.concat(pieces, ignore_index=True)
