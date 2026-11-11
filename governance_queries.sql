-- Generic governance audit queries.
-- Assumes a metadata table `dataset_metadata` with columns:
--   name, owner, rows, last_updated, downstream_count, duplicate_of
-- Adapt table and date-arithmetic syntax to your warehouse. All queries are
-- SELECT-only and avoid CTEs so they also run on engines that lack them.
-- Thresholds below (180 days, 50,000,000 rows, 1.0 per million rows) are examples.

-- 1. Orphaned: no owner.
SELECT name, rows, last_updated, downstream_count
FROM dataset_metadata
WHERE owner IS NULL OR TRIM(owner) = ''
ORDER BY rows DESC;

-- 2. Stale: not updated in 180 days and nothing downstream depends on it.
SELECT name, owner, rows, last_updated
FROM dataset_metadata
WHERE last_updated < CURRENT_DATE - INTERVAL '180' DAY
  AND COALESCE(downstream_count, 0) = 0
ORDER BY rows DESC;

-- 3. Duplicates: flagged copies, plus the original they point at.
SELECT d.name AS duplicate_name, d.owner AS duplicate_owner, d.rows AS duplicate_rows,
       d.duplicate_of AS original_name
FROM dataset_metadata d
WHERE d.duplicate_of IS NOT NULL AND TRIM(d.duplicate_of) <> ''
ORDER BY d.rows DESC;

-- 3b. Likely duplicates by shared name and row count, when duplicate_of is not maintained.
SELECT name, COUNT(*) AS copies, MAX(rows) AS rows_each
FROM dataset_metadata
GROUP BY name, rows
HAVING COUNT(*) > 1
ORDER BY rows_each DESC;

-- 4. Oversized: above 50 million rows, largest first.
SELECT name, owner, rows, downstream_count
FROM dataset_metadata
WHERE rows > 50000000
ORDER BY rows DESC;

-- 5. Savings estimate: rows held by stale or duplicate datasets, priced at
--    1.0 per million rows per period. Each dataset is counted once.
SELECT
    COUNT(*) AS reclaimable_datasets,
    SUM(rows) AS reclaimable_rows,
    SUM(rows) / 1000000.0 * 1.0 AS estimated_savings
FROM dataset_metadata
WHERE (duplicate_of IS NOT NULL AND TRIM(duplicate_of) <> '')
   OR (last_updated < CURRENT_DATE - INTERVAL '180' DAY
       AND COALESCE(downstream_count, 0) = 0);

-- 6. Owners with the most flagged datasets (follow-up list).
SELECT COALESCE(NULLIF(TRIM(owner), ''), '(none)') AS owner_name,
       COUNT(*) AS flagged_datasets,
       SUM(rows) AS flagged_rows
FROM dataset_metadata
WHERE (duplicate_of IS NOT NULL AND TRIM(duplicate_of) <> '')
   OR (last_updated < CURRENT_DATE - INTERVAL '180' DAY
       AND COALESCE(downstream_count, 0) = 0)
   OR owner IS NULL OR TRIM(owner) = ''
GROUP BY COALESCE(NULLIF(TRIM(owner), ''), '(none)')
ORDER BY flagged_rows DESC;
