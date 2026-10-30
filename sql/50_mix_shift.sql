-- Phase 5 -- Mix shift vs rate change in cart -> purchase, Oct -> Nov.
--
-- Metric:   cart -> purchase rate at (session, top-level category) grain.
--           Of the pairs that carted in a category, the share that also
--           purchased in that category. Same grain as Phase 3 category_funnel.
-- Segment:  top-level category = first part of category_code
--           ('electronics.smartphone' -> 'electronics'), NULL -> 'uncategorized'.
-- Baseline: October (the "before" period). Convention, not principle --
--           the interaction term is reported so the reader can see how much
--           the split depends on it.
--
-- The identity this all rests on:
--   total_rate(month) = SUM over segments of share(segment) * rate(segment)
--   share = segment's cart pairs / all cart pairs that month
--   rate  = segment's cart pairs that purchased / segment's cart pairs
-- So, per segment, with o = Oct and n = Nov:
--   mix         = (share_n - share_o) * rate_o
--   rate        = share_o * (rate_n - rate_o)
--   interaction = (share_n - share_o) * (rate_n - rate_o)
-- and SUM(mix + rate + interaction) over segments = total_rate_n - total_rate_o
-- EXACTLY. That equality is the self-check.
--
-- Month is the month of the pair's first event. A session that crosses
-- midnight on Oct 31 could have pairs in different months; the number of such
-- sessions is negligible and this is a deliberate simplification.


-- name: mix_shift
WITH pairs AS (
    -- top-level category. One row per (session, top_category).
    SELECT
        USER_ID,
        SESSION_NUM_30,
        COALESCE(SPLIT_PART(CATEGORY_CODE, '.', 1), 'uncategorized') AS top_category,
        DATE_TRUNC('month', MIN(EVENT_TIME)) AS month,
        COUNT_IF(EVENT_TYPE = 'cart') > 0 AS has_cart,
        COUNT_IF(EVENT_TYPE = 'purchase') > 0 AS has_purchase
    FROM EFA.ANALYTICS.EVENTS_SESSIONIZED
    GROUP BY USER_ID, SESSION_NUM_30,
        COALESCE(SPLIT_PART(CATEGORY_CODE, '.', 1), 'uncategorized')
),

-- ---- your query below -----------------------------------------------------

segment_stats AS (
    -- One row per (month, top_category), cart pairs only.
    -- Columns: month, top_category, carts, buys, share, rate
    --   carts = number of pairs with has_cart
    --   buys  = number of pairs with has_cart AND has_purchase
    --   share = carts / total carts in that month
    --           (hint: SUM(...) OVER (PARTITION BY month))
    --   rate  = buys / carts
    SELECT
        month,
        top_category,
        COUNT(*) as carts,
        COUNT_IF(has_purchase) as buys,
        COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY month) AS share,
        (buys/carts) as rate
    FROM pairs
    WHERE has_cart
    GROUP BY month, top_category
),

side_by_side AS (
    -- One row per top_category with oct_share, oct_rate, nov_share, nov_rate.
    -- Hint: conditional aggregation, e.g.
    --   MAX(IFF(month = '2019-10-01', share, NULL)) AS oct_share
    -- Check before moving on: does any category have NULL in one month
    -- (no carts at all that month)? If so, mix * NULL = NULL silently drops
    -- that category's contribution -- decide what to do about it.
    SELECT
        top_category,
        MAX(IFF(month = '2019-10-01', share, NULL)) AS oct_share,
        MAX(IFF(month = '2019-10-01', rate, NULL)) AS oct_rate,
        MAX(IFF(month = '2019-11-01', share, NULL)) AS nov_share,
        MAX(IFF(month = '2019-11-01', rate, NULL)) AS nov_rate
    FROM segment_stats
    GROUP BY top_category
),

decomposition AS (
    SELECT
        top_category,
        ((nov_share - oct_share) * oct_rate) as mix,
        (oct_share * (nov_rate - oct_rate)) as rate_effect,
        ((nov_share - oct_share) * (nov_rate - oct_rate)) as interaction
    FROM side_by_side
)

-- Final SELECT: one row per top_category with mix, rate, interaction
-- (formulas at the top of this file), ordered by the largest absolute
-- contribution. Then add a total line -- either a second query or
-- GROUP BY ROLLUP -- and check it against the headline numbers.
SELECT 
    top_category,
    mix,
    rate_effect,
    interaction,
    (mix + rate_effect + interaction) as total
FROM decomposition

UNION all

SELECT
    'TOTAL',
    SUM(mix),
    SUM(rate_effect),
    SUM(interaction),
    SUM(mix + rate_effect + interaction)
FROM decomposition

ORDER BY ABS(total) DESC;
