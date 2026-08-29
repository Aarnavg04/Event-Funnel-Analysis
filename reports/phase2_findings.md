# Phase 2 — Findings

Sessionization with a 30-minute inactivity rule, computed independently of the
shipped `user_session` column. Query: `sql/20_sessionize.sql`, written by hand.
Materialized as `EFA.ANALYTICS.EVENTS_SESSIONIZED`.

All four validations pass: row count preserved (109,950,743), no null session
numbers, `sessions_10 >= sessions_30 >= sessions_60`, and no gap inside a
30-minute session exceeds 1800s.

---

## Our sessions vs the shipped column

| | sessions |
|---|---|
| ours @10 min | 20,495,962 |
| **ours @30 min** | **18,756,054** |
| ours @60 min | 17,987,818 |
| shipped `user_session` | 23,016,650 |

Ours is **18.51% fewer** sessions than the shipped column at the same nominal
30-minute convention.

## The disagreement runs the opposite way from what Phase 1 predicted

| | count | share |
|---|---|---|
| shipped sessions we **split** | 407,943 | 1.77% |
| our sessions that **merge** shipped ones | 2,917,102 | 15.55% |

Finding 1.2 predicted splitting: the 819,408 shipped sessions running over 30
minutes were the only place disagreement seemed possible. That was
one-directional and wrong. **Merging dominates splitting nearly 9 to 1**, and a
single session of ours absorbs up to **1,705** shipped ones.

The shipped column starts new sessions far more eagerly than an inactivity rule
does. It is visible in a 20-row sample: one user's shipped session ends and a
new one begins after a **176-second** gap, which no 30-minute rule would ever
cut. Whatever produced `user_session`, it is not a 30-minute inactivity rule --
it behaves closer to a per-page-visit or per-tab identifier.

**This is the answer to "why do my sessions differ from theirs."** Not because
we split their long ones, but because they cut sessions we consider continuous.

The 1.2 proof still holds where it applies: **0** single-user shipped sessions
of 30 minutes or less were split by our rule. The 888 that were split all span
more than one `user_id`, which our user-partitioned rule must separate.

---

## Threshold sensitivity (decision a)

| threshold | sessions with a view | -> cart | -> purchase |
|---|---|---|---|
| 10 min | 20,470,877 | 10.50% | 6.44% |
| **30 min** | **18,747,465** | **10.86%** | **6.86%** |
| 60 min | 17,981,661 | 11.00% | 7.02% |

Session-level purchase conversion moves **6.44% -> 7.02%** across the range --
a **9% relative swing** driven entirely by a parameter that is convention, with
no change whatever in user behaviour. A shorter threshold fragments one
shopping trip into several, most fragments contain no purchase, and the
denominator inflates.

This is why Phase 3 reports both funnels. **The session-level funnel is
mechanically sensitive to a number we chose; the user-level funnel is immune to
it.** Any session-level rate quoted without its threshold is unfalsifiable.

---

## A bug worth recording: tied timestamps split across two window functions

The first build failed validation with 500 sessions containing gaps of up to
2,843,526 seconds (33 days) -- impossible under a 30-minute rule. Cause:

```
2019-11-11 19:36:03  cart   gap=         0   session_30=1   <- stranded
2019-11-11 19:36:03  view   gap= 2,843,526   session_30=2   <- got the flag
```

`LAG` and `SUM` are separate window functions and sort independently. With tied
timestamps, `LAG` ordered the pair `[view, cart]` -- giving `view` the 33-day
gap and the new-session flag -- while `SUM` processed them `[cart, view]`,
so the running total had not yet incremented when it reached `cart`. The cart
landed in a session that ended 33 days earlier.

Decision (d) originally said no tiebreaker was needed, on the reasoning that
tied events have a zero gap between them and therefore land in the same session
regardless of sort order. That reasoning assumes both window functions see the
same order. **They do not.**

Fix: a `ROW_NUMBER()` surrogate computed once per user, with both `LAG` and
`SUM` ordering by it instead of by `EVENT_TIME`. A total order the two window
functions cannot disagree about.

Aggregate impact was nil -- session counts were identical before and after, and
conversion rates moved by less than 0.01pp. The 500 stranded rows joined
existing sessions rather than creating new ones. The bug was real and the
headline numbers never moved; both halves of that are worth stating.
