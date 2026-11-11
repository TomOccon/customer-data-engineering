"""Instance governance audit over a DataFrame of dataset metadata.

Failure mode prevented: orphaned, stale, duplicated and oversized datasets pile up,
burn compute and storage credits, and nobody owns them.

Expected columns: name, owner, rows, last_updated, downstream_count, duplicate_of.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REQUIRED_COLUMNS = ("name", "owner", "rows", "last_updated", "downstream_count", "duplicate_of")
FLAG_COLUMNS = ("is_orphaned", "is_stale", "is_duplicate", "is_oversized")


@dataclass(frozen=True)
class GovernanceConfig:
    stale_days: int = 180
    oversized_rows: int = 50_000_000
    # Illustrative default. Set this from your own contract or usage report.
    cost_per_million_rows: float = 1.0  # credits (or currency) per million rows per period


def _blank(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


def audit_datasets(df: pd.DataFrame, config: GovernanceConfig | None = None,
                   as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Return a copy of df with is_orphaned / is_stale / is_duplicate / is_oversized and flags.

    - orphaned: owner is null or blank
    - stale: last_updated older than stale_days AND downstream_count == 0
      (null downstream_count counts as 0; unparseable last_updated is not flagged)
    - duplicate: duplicate_of is set
    - oversized: rows > oversized_rows
    """
    cfg = config or GovernanceConfig()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"missing required columns: {missing}")

    now = pd.Timestamp.now(tz="UTC") if as_of is None else pd.Timestamp(as_of)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    cutoff = now - pd.Timedelta(days=cfg.stale_days)

    out = df.copy()
    updated = pd.to_datetime(out["last_updated"], errors="coerce", utc=True)
    downstream = pd.to_numeric(out["downstream_count"], errors="coerce").fillna(0)
    rows = pd.to_numeric(out["rows"], errors="coerce").fillna(0)

    out["is_orphaned"] = _blank(out["owner"])
    out["is_stale"] = (updated < cutoff) & (downstream == 0)
    out["is_duplicate"] = ~_blank(out["duplicate_of"])
    out["is_oversized"] = rows > cfg.oversized_rows

    labels = {"is_orphaned": "orphaned", "is_stale": "stale",
              "is_duplicate": "duplicate", "is_oversized": "oversized"}
    out["flags"] = out[list(FLAG_COLUMNS)].apply(
        lambda r: ",".join(labels[c] for c in FLAG_COLUMNS if r[c]), axis=1
    )
    return out


def estimate_savings(audited: pd.DataFrame, config: GovernanceConfig | None = None) -> dict:
    """Estimate cost avoided by removing stale and duplicate datasets.

    Each dataset is counted once; duplicate takes precedence over stale. Orphaned
    and oversized datasets are flagged for review but not counted as savings,
    because removing them needs an owner decision.
    """
    cfg = config or GovernanceConfig()
    rows = pd.to_numeric(audited["rows"], errors="coerce").fillna(0)
    dup = audited["is_duplicate"]
    stale = audited["is_stale"] & ~dup

    dup_rows = int(rows[dup].sum())
    stale_rows = int(rows[stale].sum())
    per_million = cfg.cost_per_million_rows
    return {
        "duplicate_datasets": int(dup.sum()),
        "stale_datasets": int(stale.sum()),
        "duplicate_rows": dup_rows,
        "stale_rows": stale_rows,
        "reclaimable_rows": dup_rows + stale_rows,
        "duplicate_savings": dup_rows / 1_000_000 * per_million,
        "stale_savings": stale_rows / 1_000_000 * per_million,
        "estimated_savings": (dup_rows + stale_rows) / 1_000_000 * per_million,
        "cost_per_million_rows": per_million,
    }
