-- ===========================================================================
-- Analyst question 2: "Which are the top 3 items that are frequently bought
-- by members?"
--
-- Grain:  one row per catalogue item.
-- Metric: times_bought = the number of distinct transactions containing the
--         item. Secondary: total_quantity = units shifted.
--
-- Run with:
--   docker compose exec db psql -U ecommerce -d ecommerce \
--     -f /queries/top3_items_by_frequency.sql
--
-- "Frequently bought" is ambiguous and the two readings disagree:
--
--   (a) HOW MANY BASKETS contained it  -- how many separate purchase decisions
--       the item was part of. A 50-pack of batteries bought once is one event.
--   (b) HOW MANY UNITS were sold       -- volume. That same 50-pack outranks
--       almost everything.
--
-- (a) is implemented as the primary metric because "frequently bought" is a
-- statement about the frequency of the buying, not the size of the purchase --
-- it is the reading a merchandiser wants for "what do people reach for". (b) is
-- returned alongside as total_quantity so the analyst can see both, and is the
-- first tiebreaker. The commented block at the bottom flips the ranking to (b)
-- if the business means volume.
--
-- On COUNT(DISTINCT ti.transaction_id): transaction_items has a composite
-- primary key on (transaction_id, item_id), so an item can appear at most once
-- per transaction and a plain COUNT(*) would give the same number today. The
-- DISTINCT is kept because it states the intent, and it stays correct if the
-- grain ever changes (e.g. splitting a line by promotion or warehouse).
--
-- Determinism: times_bought can tie, so total_quantity then item_id break it.
-- ===========================================================================

WITH item_purchases AS (
    -- Aggregate the junction on its own first. Keeping the items join outside
    -- the aggregate means the group-by runs over the narrow junction rather
    -- than over rows widened with item_name and manufacturer_name.
    SELECT
        ti.item_id,
        COUNT(DISTINCT ti.transaction_id) AS times_bought,
        SUM(ti.quantity)                  AS total_quantity
    FROM transaction_items AS ti
    GROUP BY ti.item_id
)
SELECT
    i.item_id,
    i.item_name,
    i.manufacturer_name,
    p.times_bought,
    p.total_quantity
FROM item_purchases AS p
INNER JOIN items AS i
    ON i.item_id = p.item_id
ORDER BY
    p.times_bought   DESC,
    p.total_quantity DESC,
    i.item_id
LIMIT 3;


-- ---------------------------------------------------------------------------
-- ALTERNATIVE reading (b): rank by units sold rather than by basket count.
-- Same shape, the ORDER BY swaps its first two keys. Uncomment to use.
-- ---------------------------------------------------------------------------
-- WITH item_purchases AS (
--     SELECT
--         ti.item_id,
--         COUNT(DISTINCT ti.transaction_id) AS times_bought,
--         SUM(ti.quantity)                  AS total_quantity
--     FROM transaction_items AS ti
--     GROUP BY ti.item_id
-- )
-- SELECT
--     i.item_id,
--     i.item_name,
--     i.manufacturer_name,
--     p.times_bought,
--     p.total_quantity
-- FROM item_purchases AS p
-- INNER JOIN items AS i
--     ON i.item_id = p.item_id
-- ORDER BY
--     p.total_quantity DESC,
--     p.times_bought   DESC,
--     i.item_id
-- LIMIT 3;
