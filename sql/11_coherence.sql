-- Phase 1 -- Funnel coherence.  WRITTEN BY HAND.
--
-- Question: does every purchase have a prior cart?  Measured two ways.
--
--   same session : does a cart for the SAME product exist earlier in the SAME
--                  session?  This is coherence proper, and it decides whether
--                  Phase 3 can compute a strict session-level funnel at all.
--
--   ever         : does a cart for the same product exist earlier ANYWHERE,
--                  across sessions?  This is the user-level precursor.
--
-- The GAP between the two numbers is the finding: it quantifies how much of the
-- funnel spans sessions rather than completing inside one.
--
-- Rules
--   - match on the same PRODUCT_ID, not just any cart in the session
--   - session identity = USER_SESSION (provisional; Phase 2 re-measures)
--   - timestamp comparison uses <= ; second granularity means cart and purchase
--     land in the same second often enough that strict < would inflate the
--     violation rate with noise.  Count tie-only matches separately so we can
--     see how big that effect is.
--   - filter to cart + purchase before joining; views are 94.89% of the table
--
-- Output: ONE row
--   total_purchases
--   purchases_with_prior_cart_same_session
--   purchases_with_prior_cart_ever
--   purchases_matched_only_by_tie
--   + derived rates
--
-- Self-checks before believing the result
--   - total_purchases must equal 1,659,788.  Anything higher means the join
--     multiplied rows -- a session with 3 carts for one product turning one
--     purchase into 3.
--   - same_session <= ever <= total_purchases.  If that ordering breaks, the
--     join is wrong.
--
-- Two traps
--   1. Row multiplication.  Collapse the cart side to at most one row per join
--      key BEFORE joining.  Earliest or latest cart time -- work out which one
--      actually answers "does a cart exist before this purchase".
--   2. Putting the time comparison in WHERE instead of ON.  That turns a LEFT
--      JOIN into an INNER JOIN, drops every purchase with no cart, and returns
--      a coherence rate of 100%.


-- Step 1 is boilerplate, so here is the shape. Everything below it is yours.

WITH ev AS (
    -- 110M rows -> ~5.6M. Views are 94.89% of the table and irrelevant here.
    SELECT USER_ID, PRODUCT_ID, USER_SESSION, EVENT_TIME, EVENT_TYPE
    FROM EFA.RAW.EVENTS
    WHERE EVENT_TYPE IN ('cart', 'purchase')
),

purchases AS (
    -- your denominator. must come out to 1,659,788 rows.
    SELECT ...
    FROM ev
    WHERE ...
),

-- STEP 3+4: two collapsed cart tables, one row per join key each.
--   cart_in_session : grouped by session + product
--   cart_ever       : grouped by user + product
-- Each needs ONE timestamp per group. Earliest or latest? Decide from what the
-- question is asking: "does a cart exist before this purchase".

cart_in_session AS (
    SELECT ...
),

cart_ever AS (
    SELECT ...
)

-- STEP 5+6+7: LEFT JOIN purchases to both, then count.
-- Time comparison goes in ON or in the counting, NOT in WHERE.
SELECT
    COUNT(*)  AS total_purchases,
    ...       AS purchases_with_prior_cart_same_session,
    ...       AS purchases_with_prior_cart_ever,
    ...       AS purchases_matched_only_by_tie
FROM purchases p
LEFT JOIN cart_in_session s ON ...
LEFT JOIN cart_ever       e ON ...
;
