-- Phase 1 profiling queries.
--
-- These are the executable source of truth -- src/profile.py parses this file
-- on the "-- name:" markers and runs each block. Do not duplicate them in
-- Python; edit them here.
--
-- Design note: Phase 0 was a gate (assert, exit non-zero). Phase 1 is a
-- measurement. Almost nothing here is a pass/fail, because the things it
-- measures are properties of the data rather than defects in the load. The
-- output is a report; anything that changes the analysis plan gets copied into
-- DECISIONS.md.
--
-- Cost: each block is one scan of 110M rows. Aggregates are batched with
-- conditional aggregation so this is ~6 scans, not ~20.


-- name: census
-- Row count, null rate for every column, price sentinels, cardinalities.
-- COUNT(DISTINCT ...) is exact and expensive; used deliberately because these
-- three numbers appear in the README. Cross-check: brand NULL must be
-- 15,331,243 and category_code NULL 35,413,780, both measured in Phase 0. A
-- mismatch means a bug in the profiler, not a new finding.
SELECT
  COUNT(*)                                    AS total_rows,
  COUNT_IF(EVENT_TIME    IS NULL)             AS null_event_time,
  COUNT_IF(EVENT_TYPE    IS NULL)             AS null_event_type,
  COUNT_IF(PRODUCT_ID    IS NULL)             AS null_product_id,
  COUNT_IF(CATEGORY_ID   IS NULL)             AS null_category_id,
  COUNT_IF(CATEGORY_CODE IS NULL)             AS null_category_code,
  COUNT_IF(BRAND         IS NULL)             AS null_brand,
  COUNT_IF(PRICE         IS NULL)             AS null_price,
  COUNT_IF(USER_ID       IS NULL)             AS null_user_id,
  COUNT_IF(USER_SESSION  IS NULL)             AS null_user_session,
  COUNT_IF(PRICE = 0)                         AS price_zero,
  COUNT_IF(PRICE < 0)                         AS price_negative,
  COUNT_IF(EVENT_TYPE = 'view')               AS n_view,
  COUNT_IF(EVENT_TYPE = 'cart')               AS n_cart,
  COUNT_IF(EVENT_TYPE = 'purchase')           AS n_purchase,
  COUNT(DISTINCT EVENT_TYPE)                  AS distinct_event_types,
  COUNT(DISTINCT USER_ID)                     AS distinct_users,
  COUNT(DISTINCT PRODUCT_ID)                  AS distinct_products,
  COUNT(DISTINCT USER_SESSION)                AS distinct_sessions
FROM EFA.RAW.EVENTS;


-- name: price_by_type
-- Price is attached to EVERY row, including views. A whole-table price
-- distribution is therefore a distribution of *viewed* prices -- views are the
-- large majority -- and says almost nothing about what people actually bought.
-- Splitting by event_type is the whole point of this block.
--
-- APPROX_PERCENTILE (HyperLogLog-style sketch) rather than PERCENTILE_CONT:
-- this is profiling, not a reported metric, and the exact version sorts 110M
-- rows. If any of these numbers ends up in the README, recompute it exactly.
SELECT
  EVENT_TYPE,
  COUNT(*)                            AS n,
  COUNT_IF(PRICE = 0)                 AS zero_price,
  MIN(PRICE)                          AS p_min,
  APPROX_PERCENTILE(PRICE, 0.01)      AS p01,
  APPROX_PERCENTILE(PRICE, 0.25)      AS p25,
  APPROX_PERCENTILE(PRICE, 0.50)      AS p50,
  APPROX_PERCENTILE(PRICE, 0.75)      AS p75,
  APPROX_PERCENTILE(PRICE, 0.90)      AS p90,
  APPROX_PERCENTILE(PRICE, 0.99)      AS p99,
  APPROX_PERCENTILE(PRICE, 0.999)     AS p999,
  MAX(PRICE)                          AS p_max,
  AVG(PRICE)                          AS p_mean
FROM EFA.RAW.EVENTS
GROUP BY 1
ORDER BY n DESC;


-- name: duplicates
-- "Duplicate" here = same user, product, event_type and timestamp, per the
-- spec. event_time has SECOND granularity, so this definition cannot separate
-- a logging artifact from a genuine rapid repeat.
--
-- Critical: this dataset has NO quantity column. Two purchase rows for the same
-- user/product/second may well BE a quantity of 2. Deduplicating would silently
-- undercount revenue and purchase volume. Decision (a) is measure, do not
-- dedupe -- which is why this block reports and changes nothing.
--
-- The purchase row of this output is the one that matters.
WITH dup AS (
  SELECT USER_ID, PRODUCT_ID, EVENT_TYPE, EVENT_TIME, COUNT(*) AS n
  FROM EFA.RAW.EVENTS
  GROUP BY 1, 2, 3, 4
  HAVING COUNT(*) > 1
)
SELECT
  EVENT_TYPE,
  COUNT(*)                          AS dup_groups,
  SUM(n)                            AS rows_in_dup_groups,
  SUM(n - 1)                        AS excess_rows,
  MAX(n)                            AS max_group_size,
  APPROX_PERCENTILE(n, 0.5)         AS median_group_size
FROM dup
GROUP BY 1
ORDER BY excess_rows DESC;


-- name: session_integrity
-- Everything derived from USER_SESSION is PROVISIONAL (decision b) -- Phase 2
-- computes sessions independently and these get re-measured.
--
-- sessions_multi_user is the one that can invalidate decision (b) outright: a
-- session id mapping to more than one user_id means the column is not a session
-- key in the sense we are assuming, and the coherence numbers built on it would
-- be meaningless.
--
-- Percentiles not means: events-per-session is heavy-tailed and a mean is
-- dominated by whatever the largest sessions are. The max is where bots live.
WITH s AS (
  SELECT
    USER_SESSION,
    COUNT(DISTINCT USER_ID)                                   AS users,
    COUNT(*)                                                  AS events,
    DATEDIFF(second, MIN(EVENT_TIME), MAX(EVENT_TIME))        AS duration_s
  FROM EFA.RAW.EVENTS
  WHERE USER_SESSION IS NOT NULL
  GROUP BY 1
)
SELECT
  COUNT(*)                                AS sessions,
  COUNT_IF(users > 1)                     AS sessions_multi_user,
  MAX(users)                              AS max_users_per_session,
  APPROX_PERCENTILE(events, 0.50)         AS ev_p50,
  APPROX_PERCENTILE(events, 0.90)         AS ev_p90,
  APPROX_PERCENTILE(events, 0.99)         AS ev_p99,
  APPROX_PERCENTILE(events, 0.999)        AS ev_p999,
  MAX(events)                             AS ev_max,
  AVG(events)                             AS ev_mean,
  COUNT_IF(events = 1)                    AS single_event_sessions,
  APPROX_PERCENTILE(duration_s, 0.50)     AS dur_p50,
  APPROX_PERCENTILE(duration_s, 0.90)     AS dur_p90,
  APPROX_PERCENTILE(duration_s, 0.99)     AS dur_p99,
  MAX(duration_s)                         AS dur_max,
  COUNT_IF(duration_s = 0)                AS zero_duration_sessions
FROM s;


-- name: user_activity
-- Sessions per user and events per user. The tail here decides whether any
-- later metric needs a bot exclusion rule. Decision (e): report now, decide
-- per-metric later -- a blanket exclusion applied at this stage would quietly
-- move every downstream number.
WITH u AS (
  SELECT
    USER_ID,
    COUNT(DISTINCT USER_SESSION) AS sessions,
    COUNT(*)                     AS events,
    COUNT_IF(EVENT_TYPE = 'purchase') AS purchases
  FROM EFA.RAW.EVENTS
  GROUP BY 1
)
SELECT
  COUNT(*)                              AS users,
  APPROX_PERCENTILE(sessions, 0.50)     AS sess_p50,
  APPROX_PERCENTILE(sessions, 0.90)     AS sess_p90,
  APPROX_PERCENTILE(sessions, 0.99)     AS sess_p99,
  MAX(sessions)                         AS sess_max,
  APPROX_PERCENTILE(events, 0.50)       AS ev_p50,
  APPROX_PERCENTILE(events, 0.90)       AS ev_p90,
  APPROX_PERCENTILE(events, 0.99)       AS ev_p99,
  APPROX_PERCENTILE(events, 0.999)      AS ev_p999,
  MAX(events)                           AS ev_max,
  COUNT_IF(events = 1)                  AS single_event_users,
  COUNT_IF(purchases > 0)               AS users_with_purchase,
  MAX(purchases)                        AS max_purchases
FROM u;


-- name: attribute_stability
-- Closes the open question left by Phase 0. The brand check found 19,821
-- products (9.58%) appearing both branded and blank -- a product's brand cannot
-- change between events, so those blanks are capture failures.
--
-- This runs the same test on category_code and category_id, and adds a stronger
-- one: does a product ever carry two DIFFERENT non-null values? That is not
-- missingness, it is contradiction, and it would matter more for Phase 3 than
-- the nulls do.
WITH p AS (
  SELECT
    PRODUCT_ID,
    COUNT_IF(CATEGORY_CODE IS NULL)     AS cc_null,
    COUNT_IF(CATEGORY_CODE IS NOT NULL) AS cc_set,
    COUNT(DISTINCT CATEGORY_CODE)       AS cc_distinct,
    COUNT(DISTINCT CATEGORY_ID)         AS cid_distinct,
    COUNT(DISTINCT BRAND)               AS brand_distinct
  FROM EFA.RAW.EVENTS
  GROUP BY 1
)
SELECT
  COUNT(*)                                    AS products,
  COUNT_IF(cc_null > 0 AND cc_set > 0)        AS cc_mixed_null_and_set,
  COUNT_IF(cc_null > 0 AND cc_set = 0)        AS cc_always_null,
  COUNT_IF(cc_null = 0)                       AS cc_always_set,
  COUNT_IF(cc_distinct > 1)                   AS cc_contradictory,
  COUNT_IF(cid_distinct > 1)                  AS category_id_contradictory,
  COUNT_IF(brand_distinct > 1)                AS brand_contradictory
FROM p;


-- name: session_shape
-- Follow-up to session_integrity, which reported a max session duration of
-- 5,248,873 seconds -- 60.7 days, against a dataset that is only 61 days long.
-- A "session" spanning the whole window is not a session, so this quantifies
-- how session-like the shipped column actually is.
--
-- This is the direct setup for Phase 2: our own 30-minute inactivity rule will
-- split every session in the ">30 min" bucket, and this is the number that
-- comparison starts from.
WITH s AS (
  SELECT USER_SESSION,
         DATEDIFF(second, MIN(EVENT_TIME), MAX(EVENT_TIME)) AS d
  FROM EFA.RAW.EVENTS
  WHERE USER_SESSION IS NOT NULL
  GROUP BY 1
)
SELECT
  COUNT(*)                  AS sessions,
  COUNT_IF(d > 1800)        AS over_30_min,
  COUNT_IF(d > 3600)        AS over_1_hour,
  COUNT_IF(d > 86400)       AS over_1_day,
  COUNT_IF(d > 604800)      AS over_7_days,
  COUNT_IF(d > 2592000)     AS over_30_days
FROM s;


-- name: price_tail
-- price_by_type showed an identical maximum of 2574.07 for view, cart AND
-- purchase, which looks like a cap. It is not: the tail is smooth and eight
-- distinct products sit at the top price. Kept because "I checked whether that
-- ceiling was real" is worth more than the result.
SELECT PRICE, COUNT(*) AS n, COUNT(DISTINCT PRODUCT_ID) AS products
FROM EFA.RAW.EVENTS
WHERE PRICE > 2560
GROUP BY 1
ORDER BY 1 DESC
LIMIT 10;
