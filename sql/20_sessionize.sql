-- Phase 2 -- Sessionization.  WRITTEN BY HAND.
--
-- Assign every event to a session using a 30-minute inactivity rule, computed
-- independently of the shipped USER_SESSION column.
--
-- Decision (a): compute THREE thresholds in the same pass -- 10, 30 and 60
-- minutes -- so the sensitivity of session-level conversion to this parameter
-- can be measured rather than asserted. 30 minutes is the canonical choice and
-- the one every later phase uses; 10 and 60 exist to show what moves.
--
-- Doing all three in one query matters for cost: the expensive part is sorting
-- 110M rows by (USER_ID, EVENT_TIME). Three separate queries would pay that
-- three times. One sort, three cumulative sums.
--
-- Rules
--   - PARTITION BY USER_ID, never USER_SESSION.  939 shipped sessions span more
--     than one user (finding 1.2); partitioning by session would compute a gap
--     between two different people's events.
--   - ORDER BY EVENT_TIME.
--   - Gap in SECONDS.  Thresholds are 600 / 1800 / 3600.
--   - Decision (b): STRICTLY greater than.  A gap of exactly 1800s continues
--     the session rather than starting a new one.
--   - Decision (d): no tiebreaker on equal timestamps.  Two events in the same
--     second have a gap of 0, which never exceeds any threshold, so they land
--     in the same session whatever order the sort puts them in.
--
-- Output: one row per input event (109,950,743 of them), carrying
--   gap_seconds, session_num_10, session_num_30, session_num_60
--
-- THE TRAP -- read this before writing the cumulative sum.
--   SUM(...) OVER (PARTITION BY ... ORDER BY ...) with no frame clause defaults
--   to RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW.  RANGE treats every
--   row sharing the same ORDER BY value as a peer and includes all of them in
--   the frame.  This data is full of tied timestamps -- 36% of sessions have
--   zero duration -- so the default will give wrong cumulative sums.
--   Write ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW explicitly.
--
-- Second trap: LAG returns NULL on a user's first event, and NULL > 1800 is
-- NULL, not TRUE.  Decide deliberately what a first event should do.  Never put
-- the gap comparison in a WHERE clause -- that silently drops it.
--
-- Self-checks (src/sessionize.py runs these)
--   - output row count == 109,950,743
--   - no NULL session numbers
--   - sessions_10 >= sessions_30 >= sessions_60  (a shorter threshold can only
--     ever cut MORE sessions, never fewer -- if this inverts, the flags or the
--     frame are wrong)
--   - within any session_30, no gap between consecutive events exceeds 1800s
--
-- Snowflake ships CONDITIONAL_TRUE_EVENT(cond) OVER (...) which collapses the
-- flag+cumulative-sum into one call.  Neater, but not portable and not what
-- gets asked about -- LAG + SUM by hand here.


-- your query below

WITH gapped AS (
    -- STEP 1: seconds since this user's previous event.
    -- DATEDIFF(second, <earlier>, <later>) -- mind the argument order, it is
    -- (unit, start, end) and getting it backwards gives negative gaps.
    SELECT
        EVENT_TIME, EVENT_TYPE, PRODUCT_ID, CATEGORY_ID, CATEGORY_CODE,
        BRAND, PRICE, USER_ID, USER_SESSION,
        DATEDIFF(second, ..., ...) AS gap_seconds
    FROM EFA.RAW.EVENTS
),

flagged AS (
    -- STEP 2: 1 when this row starts a new session, else 0. One flag per
    -- threshold. Remember what LAG did to the first event.
    SELECT
        gapped.*,
        CASE WHEN ... THEN 1 ELSE 0 END AS is_new_10,
        CASE WHEN ... THEN 1 ELSE 0 END AS is_new_30,
        CASE WHEN ... THEN 1 ELSE 0 END AS is_new_60
    FROM gapped
)

-- STEP 3: running total of the flags, per user, in time order.
-- This is where the RANGE-vs-ROWS trap lives.
SELECT
    flagged.* EXCLUDE (is_new_10, is_new_30, is_new_60),
    SUM(is_new_10) OVER (...) AS session_num_10,
    SUM(is_new_30) OVER (...) AS session_num_30,
    SUM(is_new_60) OVER (...) AS session_num_60
FROM flagged
