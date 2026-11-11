# Customer Data Engineering

> Real-world data pipeline patterns. Things that break. How to fix them.

Most portfolio projects work in ideal conditions. Production pipelines don't.

This repository documents patterns, failure modes, and fixes developed
across multiple customer data engineering engagements — marketing analytics,
financial reporting, support operations, and logistics.

---

## The Failures (and What I Learned)

### 1. The Silent Row Multiplication

**Symptom:** A finance team flags that their monthly revenue number is $40K higher
than expected. Pipeline ran successfully. No errors in the log.

**Root cause:** A Magic ETL join on a date + product key exceeded the platform's
internal key cardinality limit (~10,000 distinct values). The platform's behavior
at this threshold is to produce duplicate rows — silently, without error.

**Fix:** Moved to explicit SQL with a `ROW_NUMBER()` deduplication step.
Added a row count assertion: `output_rows MUST EQUAL source_rows` — any
pipeline run that violates this fails loudly rather than silently.

**Lesson:** Any join on a high-cardinality key needs an explicit deduplication
guard. Don't assume the platform catches it.

---

### 2. The Memory Failure That Only Happened in Production

**Symptom:** `Join inner did not fit in memory` on a dataflow that had been
running fine in the development environment for weeks.

**Root cause:** The dev environment had 3 months of data. Production had 3 years.
The in-memory join strategy that works at 300k rows fails at 3M.

**Fix:** Switched to a hash join strategy with pre-aggregation of the larger table
before the join. Reduced the join's memory footprint by ~85%.

**Lesson:** Test with production-scale data before go-live. Volume-based failures
are the most common class of "works in dev, breaks in prod."

---

### 3. The Connector That Silently Truncated Data

**Symptom:** A Salesforce connector was pulling 98% of records. 2% were missing.
No error. The connector reported success.

**Root cause:** The SOQL query used a regex pattern to filter certain record types.
A specific record subtype had a name format that didn't match the pattern — so
those records were filtered out rather than included.

**Fix:** Inverted the filter logic (exclude known-bad instead of include known-good).
Added a count reconciliation check: connector output record count vs. direct SOQL
count with no filters.

**Lesson:** Connectors can succeed while returning incomplete data. Always validate
output counts against a known-good source.

---

### 4. The Federated Query That Shows Zero Rows in the UI

**Symptom:** A Snowflake federated dataset shows 0 rows in the UI. The same query
run directly in Snowflake returns 44,000 rows.

**Root cause:** The Domo UI's dataset preview uses a viewer-scoped token, not
the service account token. The service account has access to the Snowflake view;
the preview user's identity does not.

**Fix:** Use the API query endpoint (not the UI) to validate federated dataset content.
Service account must have explicit USAGE grants on the Snowflake schema, not just
the table.

**Lesson:** For federated data sources, the UI is not a reliable validator.
Always confirm data availability through the API with a service-account-scoped call.

---

### 5. The Double-Count Bug in a Fan-Out ETL

**Symptom:** Monthly churn metric was ~2x the expected number. The math checked out
at the SQL level. The issue was in the data.

**Root cause:** A Recurly churn dataset had one row per `date × cancellation_reason`.
A customer who cancelled for two reasons in the same day appeared twice. The downstream
metric was summing rows, not distinct customers.

**Fix:** Added a deduplication step at ingestion: one row per customer per date,
using the "primary" cancellation reason. Also added a uniqueness assertion on
`(customer_id, date)` after the deduplication step.

**Lesson:** Always profile the grain of your source data before building aggregations.
`SELECT COUNT(*) FROM tbl` vs `SELECT COUNT(DISTINCT id) FROM tbl` is the fastest
sanity check.

---

## Patterns I Use Consistently

### Row Count Assertions

Every ETL run compares output row count against expectations:

```sql
-- after every major transform, check the grain
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT date_key || '-' || customer_id) AS expected_distinct,
    COUNT(*) = COUNT(DISTINCT date_key || '-' || customer_id) AS is_clean
FROM transformed_output
```

A pipeline that fails this check should stop and alert, not continue silently.

### Source-to-Target Reconciliation

For every source → output dataset pair:

```python
def reconcile(source_count: int, output_count: int, tolerance: float = 0.001) -> bool:
    """
    Returns True if output count is within tolerance of source count.
    Fails loudly if more than tolerance% of rows are missing or duplicated.
    """
    if source_count == 0:
        return output_count == 0
    delta = abs(output_count - source_count) / source_count
    return delta <= tolerance
```

### Hash-Based Incremental Loads

For datasets that need incremental updates without full reloads:

```python
def compute_row_hash(row: dict, key_columns: list[str]) -> str:
    """
    Deterministic hash of key columns for change detection.
    Re-running on unchanged data produces the same hash — idempotent.
    """
    key_values = "|".join(str(row[col]) for col in sorted(key_columns))
    return hashlib.sha256(key_values.encode()).hexdigest()[:12]
```

### Pre-Join Deduplication

Before any join on a high-cardinality key:

```sql
WITH deduped AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY join_key
            ORDER BY updated_at DESC
        ) AS rn
    FROM source_table
)
SELECT * FROM deduped WHERE rn = 1
```

### Native Tiles Before SQL Tiles

For customer-managed ETL pipelines, native transformation tiles are preferred
over SQL tiles. Customers can understand and maintain a MergeJoin + Filter tile
visually. They cannot maintain arbitrary SQL when something breaks at 11pm.

SQL tiles are appropriate when:
- The transform logic is genuinely complex (CTEs, window functions)
- The native tile equivalent would require 8+ chained tiles
- The pipeline is internal/FDE-owned, not customer-maintained

---

## Data Modeling Patterns

### Multi-Source Revenue Attribution

```
                    ┌──────────────┐
                    │   Raw Data   │
          ┌─────────┤   Sources    ├─────────┐
          │         └──────────────┘         │
          ▼                                  ▼
  ┌──────────────┐                  ┌──────────────┐
  │  Intermediary│                  │  Intermediary│
  │  Dataset A   │                  │  Dataset B   │
  └──────┬───────┘                  └──────┬───────┘
         │                                 │
         └──────────────┬──────────────────┘
                        ▼
               ┌──────────────────┐
               │  Semantic Layer  │
               │  (1 row / date / │
               │   channel)       │
               └────────┬─────────┘
                        ▼
               ┌──────────────────┐
               │   Analytics /    │
               │   Cards          │
               └──────────────────┘
```

All raw sources are normalized to a common grain before joining. Never join
two pre-aggregated sources at different grains.

---

## Code

The patterns above are implemented in `dataguard/`, a small Python package
(pandas and the standard library only). All data in `examples/` and `tests/`
is synthetic.

| Module | Failure mode it prevents | Failure # |
|---|---|---|
| `dataguard/reconcile.py` | Output row count or totals drift from source with no error. Count and sum reconciliation with tolerance, structured result, `raise_if_failed()`. | 1, 3 |
| `dataguard/joins.py` | A join on a non-unique key multiplies rows. `check_join_cardinality` predicts the exact output row count before you run the join and flags fanout. `composite_key` is a deterministic, null-safe multi-column hash. `dedupe_latest` is the `ROW_NUMBER() ... rn = 1` guard. | 1, 5 |
| `dataguard/completeness.py` | A connector succeeds but drops records. Expected vs received counts, percent missing, threshold alert, and the list of missing ids. | 3 |
| `dataguard/chunked_join.py` | Join runs out of memory at production volume. Prunes columns, pre-aggregates, pre-filters unmatched keys, then joins one hash partition at a time. Tested for identical results to a naive join. | 2 |
| `dataguard/governance.py` | Orphaned, stale, duplicate and oversized datasets accumulate and cost credits. Audit over a metadata DataFrame plus a savings estimate driven by a configurable cost per million rows. | n/a |
| `governance_queries.sql` | Same governance audit as generic SELECT queries (no CTEs). Adapt table names and date syntax. | n/a |

Differences from the README snippets: `reconcile_counts` returns a result object
instead of a bare bool, and `composite_key` hashes columns in the order you pass
them and length-prefixes each value so `("ab", "c")` and `("a", "bc")` do not collide.

### Run it

```bash
pip install -r requirements.txt

# test suite
python -m pytest -q

# demo: a silent 4x row multiplication, caught before and after the join
python examples/demo.py
```

Minimal usage:

```python
from dataguard import check_join_cardinality, reconcile_frames

report = check_join_cardinality(orders, products, "product_id", how="left")
print(report.summary())   # ... predicted_rows=4000 fanout=4.00x [ROW MULTIPLICATION]

joined = orders.merge(products, on="product_id", how="left")
reconcile_frames(orders, joined, sum_columns=["revenue"]).raise_if_failed()
```

```python
from dataguard import GovernanceConfig, audit_datasets, estimate_savings

cfg = GovernanceConfig(stale_days=180, oversized_rows=50_000_000, cost_per_million_rows=1.0)
audited = audit_datasets(metadata_df, cfg)   # columns: name, owner, rows, last_updated, downstream_count, duplicate_of
print(estimate_savings(audited, cfg))
```

The default cost per million rows is a placeholder. Set it from your own contract
or usage report before quoting a savings number.

---

## Technologies

`SQL` · `Python` · `pandas` · `Magic ETL` · `Snowflake` · `Salesforce` ·
`Domo` · `Recurly` · `Google Analytics` · `Jupyter`
