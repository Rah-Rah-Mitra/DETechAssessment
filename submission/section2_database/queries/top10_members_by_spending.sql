-- ===========================================================================
-- Analyst question 1: "Which are the top 10 members by spending?"
--
-- Grain:  one row per member.
-- Metric: SUM(transactions.total_items_price) across all of that member's
--         transactions, all time.
--
-- Run with:
--   docker compose exec db psql -U ecommerce -d ecommerce \
--     -f /queries/top10_members_by_spending.sql
--
-- Notes on the two choices this query makes:
--
--   * INNER JOIN, not LEFT JOIN. A member who has never bought anything has
--     spent 0 and cannot place in a top 10 that already has ten payers, so
--     including them only pads the scan. Swap to LEFT JOIN with
--     COALESCE(SUM(...), 0) if the question ever becomes "rank ALL members".
--
--   * It reads transactions.total_items_price rather than re-aggregating
--     transaction_items. That column is denormalised, but it is maintained by
--     the transaction_items_maintain_totals trigger, so it cannot drift from
--     the line items -- and reading it keeps this query to two tables instead
--     of three.
--
-- Determinism: total_spent alone can tie, so membership_id breaks it. Without
-- an explicit tiebreaker the same data could return a different tenth row on
-- different runs, which makes the result untrustworthy in a report.
-- ===========================================================================

SELECT
    m.membership_id,
    m.first_name,
    m.last_name,
    COUNT(t.transaction_id)  AS transaction_count,
    SUM(t.total_items_price) AS total_spent
FROM members AS m
INNER JOIN transactions AS t
    ON t.membership_id = m.membership_id
GROUP BY
    m.membership_id,   -- the PK, so first_name/last_name are functionally
    m.first_name,      -- dependent on it; named anyway for portability to
    m.last_name        -- engines that do not infer that.
ORDER BY
    total_spent DESC,
    m.membership_id
LIMIT 10;
