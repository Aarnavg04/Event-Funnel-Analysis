-- Phase 4 -- Retention matrix and repeat-purchase rate.  WRITTEN BY HAND.
--
-- Reads EFA.ANALYTICS.USER_COHORTS (USER_ID, cohort_week, cohort_status) and
-- EFA.RAW.EVENTS. Only cohort_status = 'included' rows belong in any of this.
--
-- Decision (a): "retained" = ANY event, primary. Purchase-based retention is
-- the secondary metric, same structure, EVENT_TYPE filter swapped in.
--
-- THE CLOCK IS DIFFERENT FROM EVERY EARLIER PHASE. Phases 2-3 measured time
-- within a session or within a calendar month. This phase measures time
-- RELATIVE TO EACH USER'S OWN COHORT_WEEK -- a different zero-point per user.
--   week_offset = FLOOR(DATEDIFF(day, cohort_week, EVENT_TIME) / 7)
-- NOT DATE_TRUNC('week', EVENT_TIME). That gives you a global calendar week,
-- which is the wrong question -- it does not align to when each cohort
-- actually started.
--
-- THE MASKING TRAP -- this is the one your CLAUDE.md says has to be right.
-- A cell (cohort_week, week_offset) is only real if that week is fully inside
-- the data. The data ends 2019-11-30 (i.e. before 2019-12-01). A cell is
-- observable iff:
--     DATEADD(day, 7*(week_offset+1), cohort_week) <= '2019-12-01'
-- If you compute retention for every (cohort, offset) pair without this
-- filter, an unobserved cell does not come back as NULL -- it comes back as
-- 0 retained users, indistinguishable from "everyone actually churned." That
-- produces a diagonal cliff of fake decay marching down the matrix, one week
-- earlier for each successive cohort. Mask by NOT COMPUTING the cell at all
-- (filter it out / return NULL), not by computing it and hiding it later.
--
-- Self-checks -- work these out before running, then confirm:
--   - week_offset = 0 must be EXACTLY 100% retained under the any-event
--     definition, for every cohort. Why: a user's first event, by
--     construction, falls inside their own cohort_week, i.e. week_offset 0.
--     If this is not 100%, the join or the offset math is wrong.
--   - week_offset = 0 will NOT be 100% under the purchase-based definition --
--     most users' first event is a view, not a purchase. Do not "fix" this.
--   - Total observable (cohort, offset) cells, summed across all 6 cohorts,
--     is exactly 21 (the offsets-per-cohort pattern is 6,5,4,3,2,1 -- a
--     triangular number). If your count differs, the masking condition or
--     the cohort dates are wrong.
--   - Cohort sizes (denominators) must match: 623,332 / 522,809 / 478,942 /
--     578,750 / 576,118 / 541,947 for Oct15/22/29, Nov5/12/19 respectively.


-- name: retention_matrix
-- One row per (cohort_week, week_offset), OBSERVABLE cells only.
-- Columns: cohort_week, week_offset, cohort_size, retained_users, retention_rate.

WITH events_with_offset AS (
    SELECT
        e.USER_ID,
        u.COHORT_WEEK,
        FLOOR(DATEDIFF(day, u.COHORT_WEEK, e.EVENT_TIME) / 7) AS week_offset
    FROM EFA.RAW.EVENTS e
    JOIN EFA.ANALYTICS.USER_COHORTS u 
        ON e.USER_ID = u.USER_ID
    WHERE u.COHORT_STATUS = 'included'
),

retained AS (
    -- one row per (user, week_offset) that actually happened -- collapse
    -- multiple events in the same week to a single "yes" per user, per week.
    SELECT DISTINCT USER_ID, COHORT_WEEK, week_offset
    FROM events_with_offset
),

cohort_sizes AS (
    SELECT COHORT_WEEK, COUNT(*) AS cohort_size
    FROM EFA.ANALYTICS.USER_COHORTS
    WHERE COHORT_STATUS = 'included'
    GROUP BY COHORT_WEEK
)


-- your query below: join retained to cohort_sizes, GROUP BY cohort_week,
-- week_offset to count retained users, apply the masking filter, compute the
-- rate.

SELECT
    r.cohort_week,
    r.week_offset,
    c.cohort_size,
    COUNT(*) as retained_users,
    (COUNT(*) / c.cohort_size) as retention_rate
FROM retained as r
LEFT JOIN cohort_sizes as c
    ON r.cohort_week = c.cohort_week
WHERE DATEADD(day, 7*(week_offset+1), r.cohort_week) <= '2019-12-01'
GROUP BY r.cohort_week, r.week_offset, c.cohort_size
ORDER BY r.cohort_week, r.week_offset asc;

    

-- name: retention_matrix_purchase
-- Decision (a), secondary metric. Identical structure to retention_matrix,
-- with ONE change: events_with_offset filtered to EVENT_TYPE = 'purchase'
-- before computing week_offset. Same masking condition, same cohort_sizes.

-- your query below
WITH events_with_offset AS (
    SELECT
        e.USER_ID,
        u.COHORT_WEEK,
        FLOOR(DATEDIFF(day, u.COHORT_WEEK, e.EVENT_TIME) / 7) AS week_offset
    FROM EFA.RAW.EVENTS e
    JOIN EFA.ANALYTICS.USER_COHORTS u 
        ON e.USER_ID = u.USER_ID
    WHERE e.EVENT_TYPE = 'purchase' AND u.COHORT_STATUS = 'included'
),

retained AS (
    -- one row per (user, week_offset) that actually happened -- collapse
    -- multiple events in the same week to a single "yes" per user, per week.
    SELECT DISTINCT USER_ID, COHORT_WEEK, week_offset
    FROM events_with_offset
),

cohort_sizes AS (
    SELECT COHORT_WEEK, COUNT(*) AS cohort_size
    FROM EFA.ANALYTICS.USER_COHORTS
    WHERE COHORT_STATUS = 'included'
    GROUP BY COHORT_WEEK
)

-- name: repeat_purchase_rate
-- Decision (d). Of each cohort's purchasers (within their OWN observed
-- window, per cohort_status = 'included'), what share purchased more than
-- once? This is ONE rate per cohort, not a matrix -- no week_offset axis.
--
-- Caveat worth stating in the write-up, not fixing in the query: cohorts
-- observed longer have strictly more opportunity to accumulate a second
-- purchase, so raw repeat-rate is not an apples-to-apples comparison across
-- cohorts with different observation lengths. Report it anyway, alongside
-- each cohort's observed-week count, and let the reader see the confound
-- rather than hiding it.

-- your query below
