-- Phase 4 -- Cohort assignment.  BUILT BY CLAUDE (boilerplate, per protocol).
--
-- Cohort = week of first observed event, per decision 0.2. Two exclusions
-- apply before a user gets a real cohort:
--
--   1. Lookback: first event before 2019-10-15 -- pre-existing customer,
--      "first observed" is not "first acquired" for these users (decision
--      confirmed: 2-week lookback, not extended).
--   2. Trailing partial week: first event on/after 2019-11-26. Oct 15 through
--      Nov 25 is exactly 6 clean 7-day weeks; Nov 26-30 is a 5-day remainder,
--      not a real cohort week, discarded per the Phase 0 arithmetic already
--      baked into every "6 cohorts, 5-week max horizon" statement in
--      DECISIONS.md 0.2.
--
-- Week convention: cohort weeks are anchored to 2019-10-15, NOT Monday-aligned
-- DATE_TRUNC('week'). This is the arbitrary-but-stated convention flagged back
-- in Phase 0 -- anchoring to the lookback boundary keeps cohort 1 a clean 7
-- days and matches the cohort count/horizon numbers already committed to.
--
-- Materialized (decision c pattern from Phase 2): every later query in this
-- phase reads USER_ID -> cohort_week, so compute it once.
CREATE OR REPLACE TABLE EFA.ANALYTICS.USER_COHORTS AS
WITH first_seen AS (
    SELECT USER_ID, MIN(EVENT_TIME) AS first_event_time
    FROM EFA.RAW.EVENTS
    GROUP BY USER_ID
)
SELECT
    USER_ID,
    first_event_time,
    CASE
        WHEN first_event_time < '2019-10-15' THEN NULL
        WHEN first_event_time >= '2019-11-26' THEN NULL
        ELSE DATEADD(day,
                 FLOOR(DATEDIFF(day, '2019-10-15', first_event_time) / 7) * 7,
                 '2019-10-15'::date)
    END AS cohort_week,
    CASE
        WHEN first_event_time < '2019-10-15' THEN 'excluded_preexisting'
        WHEN first_event_time >= '2019-11-26' THEN 'excluded_partial_week'
        ELSE 'included'
    END AS cohort_status
FROM first_seen;
