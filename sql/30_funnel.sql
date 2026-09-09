-- Phase 3 -- The funnel.  WRITTEN BY HAND.
--
-- view -> cart -> purchase, computed two ways, per decision 1.7:
-- REACH-based (does a session/user have >=1 of each event type, independently
-- -- not a strict same-session same-product sequence). The 65.92%/27.44%
-- coherence numbers from 1.3 are the disclosed caveat next to this, not folded
-- into it.
--
-- Checked before writing this: 8,589 sessions (0.046%) have cart/purchase
-- activity with NO logged view. Stated base is "sessions with >=1 view," per
-- the spec's own phrasing; these get reported as a separate footnote, not
-- silently dropped from any count.
--
-- Reads from EFA.ANALYTICS.EVENTS_SESSIONIZED, SESSION_NUM_30 -- the
-- canonical threshold. Any session-level rate you report needs "at 30
-- minutes" attached: Phase 2 proved purchase conversion moves 6.44% -> 7.02%
-- across 10/30/60 minutes with zero change in behavior.
--
-- Duplicates do NOT need handling here. "Reach" is >=1 (existence), not a
-- count, and Phase 1 already established cart duplicates (3.21%) cannot
-- affect an existence check. Do not dedupe before this query.


-- name: session_funnel
-- Session-level: of sessions with >=1 view, what share have >=1 cart, what
-- share have >=1 purchase. Both rates share the same base (sessions with a
-- view), independently -- NOT sequential (a session can reach purchase
-- without a cart in the funnel's count; that gap is what 1.3 quantifies).
--
-- MUST also report: single-event session share (35.92%, Phase 1) alongside
-- the rate. A third of the base could never have progressed regardless of
-- anything the business does -- the funnel rate is unreadable without it.
--
-- Self-checks
--   - purchase count from this query's base should be in the neighborhood of
--     1,659,788 minus whatever sits in the 8,589 no-view sessions (not exact,
--     since one session can have multiple purchases -- but same order of
--     magnitude; wildly different means the base is wrong)
--   - cart rate must be >= purchase rate (reach is monotonic: can't purchase
--     more often than you cart, when both are measured off the same >=1
--     logic and cart is upstream... actually check this empirically, do not
--     assume it -- a session can purchase without cart, so THIS INVARIANT MAY
--     NOT HOLD. Think about whether it should before asserting it.)

WITH sessions AS (
    SELECT 
        USER_ID,
        SESSION_NUM_30,
        COUNT(*) as n_events,
        COUNT_IF(EVENT_TYPE = 'view') > 0 AS has_view,
        COUNT_IF(EVENT_TYPE = 'cart') > 0 AS has_cart,
        COUNT_IF(EVENT_TYPE = 'purchase') > 0 AS has_purchase
    FROM EFA.ANALYTICS.EVENTS_SESSIONIZED
    GROUP BY USER_ID, SESSION_NUM_30

)

SELECT
    COUNT(*) AS sessions_with_view,
    COUNT_IF(has_cart) AS reached_cart,
    COUNT_IF(has_purchase) AS reached_purchase,
    COUNT_IF(n_events = 1) AS single_event_sessions
FROM sessions
WHERE has_view



-- name: user_funnel
-- User-level: of users active in a period, what share have >=1 cart ever,
-- what share have >=1 purchase ever. Decision (b): compute BOTH the whole
-- window AND split by month.
--
-- "Active in [period]" = has >=1 event with EVENT_TIME in that period. Do not
-- restrict to users whose FIRST event falls in the period -- that is a cohort
-- question (Phase 4), not this one.
--
-- Self-check: the whole-window row must reproduce Phase 1's census finding --
-- 697,470 of 5,316,649 users ever purchase, 13.12%. If it doesn't match
-- exactly, this query has a bug, not a new finding.

WITH users AS (
    SELECT 
        USER_ID,
        COUNT_IF(EVENT_TYPE = 'cart') > 0 AS has_cart,
        COUNT_IF(EVENT_TYPE = 'purchase') > 0 AS has_purchase
    FROM EFA.RAW.EVENTS
    GROUP BY USER_ID
)

SELECT
    COUNT(*) AS total_users,
    COUNT_IF(has_cart) AS reached_cart,
    COUNT_IF(has_purchase) AS reached_purchase
FROM users


-- name: user_funnel_by_month
-- Decision (b), second half: same question, split by month instead of over
-- the whole window. This is what Phase 5 (what moved, and why) will read from.
--
-- Structure: identical to user_funnel above, but DATE_TRUNC('month',
-- EVENT_TIME) joins USER_ID in the GROUP BY, both in the CTE and in the
-- final aggregation. That is the only change -- same has_cart / has_purchase
-- logic, one more grouping column.
--
-- A user active in both October and November now produces TWO rows in the
-- CTE, one per month, each independently flagged from only that month's
-- events. Do not carry a user's cart/purchase status across months -- a user
-- who carted in October and purchased in November should NOT show a
-- purchase against October, or a cart against November.
--
-- Expected output: exactly two rows, one per month.
--
-- Self-check -- think about this BEFORE running it, it will not self-verify
-- the way the whole-window query did:
--   Oct's total_users + Nov's total_users will NOT equal 5,316,649, and
--   neither month's total_users will equal it either. A user active in both
--   months is counted in BOTH rows. This is correct, not a bug -- be ready to
--   say why "users active in October" and "users active in November" are
--   allowed to overlap when "users active in the whole window" is a single
--   fixed population.

WITH users_by_month AS (
    SELECT
        USER_ID,
        DATE_TRUNC('month', EVENT_TIME) AS month,
        COUNT_IF(EVENT_TYPE = 'cart') > 0 AS has_cart,
        COUNT_IF(EVENT_TYPE = 'purchase') > 0 AS has_purchase
    FROM EFA.RAW.EVENTS
    GROUP BY USER_ID, DATE_TRUNC('month', EVENT_TIME)
)

SELECT
    month,
    COUNT(*) as total_users,
    COUNT_IF(has_cart) AS reached_cart,
    COUNT_IF(has_purchase) AS reached_purchase
FROM users_by_month
GROUP BY month
ORDER BY month


-- name: category_funnel
-- Breakdown by category_code, decision (a). Grain is (session, category_code)
-- pairs, NOT session -- this is the one place in Phase 3 that is genuinely
-- tricky.
--
-- THE TRAP: a session touching two categories (electronics AND furniture)
-- must contribute to EACH category's funnel independently, based on what
-- happened to THAT category's events specifically -- not by tagging the
-- whole session's final outcome onto every category it touched. If a session
-- views electronics and furniture but only purchases furniture, electronics
-- must NOT show a purchase. Compute reach per (session, category_code), where
-- "reach cart in this category" means a cart event in THIS session whose
-- category_code matches -- not just any cart anywhere in the session.
--
-- category_code is NULL for 32.21% of events (Phase 1) and cannot be
-- backfilled (finding: 0% mixed, a product is either always categorized or
-- never). COALESCE these to a literal '(uncategorized)' bucket -- do not
-- filter them out, and do not leave them as SQL NULL (NULL as a GROUP BY key
-- sorts and displays inconsistently across tools).
--
-- Decision (c): report all three transitions per category --
--   view -> cart, cart -> purchase, view -> purchase (the full pipeline)
-- -- as both a RATE and an ABSOLUTE count lost. The headline is whichever
-- category has the largest ABSOLUTE loss on the full view -> purchase
-- pipeline, not the largest rate. A category can have a terrible rate on
-- tiny volume and matter less than a mediocre rate on huge volume.
--
-- Self-checks
--   - SUM of per-category session-with-view counts, counted this way, will
--     exceed total sessions with a view (multi-category sessions count more
--     than once, on purpose -- that IS the point of this grain)
--   - the '(uncategorized)' bucket alone should account for roughly 32% of
--     view-level activity, in the right neighborhood of the row-level 32.21%
--     null rate (not exact -- sessions vs rows -- but same order of magnitude)

-- your query below

WITH session_category AS (
    SELECT
        USER_ID,
        SESSION_NUM_30,
        COALESCE(CATEGORY_CODE, '(uncategorized)') as category_code,
        COUNT_IF(EVENT_TYPE = 'view') > 0 AS has_view,
        COUNT_IF(EVENT_TYPE = 'cart') > 0 AS has_cart,
        COUNT_IF(EVENT_TYPE = 'purchase') > 0 AS has_purchase
    FROM EFA.ANALYTICS.EVENTS_SESSIONIZED
    GROUP BY USER_ID, SESSION_NUM_30, COALESCE(CATEGORY_CODE, '(uncategorized)')
)


SELECT
    category_code,
    COUNT(*) AS sessions_with_views,
    COUNT_IF(has_cart) AS reached_cart,
    COUNT_IF(has_purchase) AS reached_purchase,
    sessions_with_views - reached_cart AS lost_view_to_cart,
    reached_cart - reached_purchase AS lost_cart_to_purchase,
    sessions_with_views - reached_purchase AS lost_view_to_purchase
FROM session_category
WHERE has_view
GROUP BY category_code
ORDER BY lost_view_to_purchase DESC;