# Phase 4 — Findings

Queries: `sql/40_cohorts.sql` (cohort assignment, built by Claude) and
`sql/41_retention.sql` (retention matrix, purchase retention, repeat-purchase
rate, all hand-written; the equal-window repeat variant was added by Claude).

---

## Cohort definition

A user's cohort is the 7-day week containing their **first event in the
data**, with weeks anchored at 2019-10-15.

| cohort_status | users | why |
|---|---|---|
| included | 3,321,898 | first seen Oct 15 – Nov 25 |
| excluded_preexisting | 1,688,868 | first seen Oct 1–14 (lookback window) |
| excluded_partial_week | 305,883 | first seen Nov 26–30 (5-day week) |
| **total** | **5,316,649** | matches the Phase 1 user census |

**Why a lookback.** The data starts on 2019-10-01 with no earlier history, so
"first seen" is not the same as "new customer." Anyone active Oct 1–14 is
treated as pre-existing and excluded. The two-week length is a tradeoff, not
something the data dictates (see DECISIONS, Open questions): longer cleans
the cohorts but costs cohorts and horizon. **Cohorts Oct 15, Oct 22, and
Oct 29 still carry residual contamination.** Their week-0 purchase rates fall
7.33% → 6.50% → 6.20% → 5.73% across the October cohorts, which fits early
cohorts holding more disguised regulars who buy right away.

| cohort | size | weeks observable |
|---|---|---|
| Oct 15 | 623,332 | 6 |
| Oct 22 | 522,809 | 5 |
| Oct 29 | 478,942 | 4 |
| Nov 5 | 578,750 | 3 |
| Nov 12 | 576,118 | 2 |
| Nov 19 | 541,947 | 1 |

---

## Retention matrix — any event (primary)

"Retained in week *k*" = had at least one event of any type in week *k*
after the cohort week. `week_offset` is relative to each user's own
cohort_week, not the calendar week.

| cohort | wk 0 | wk 1 | wk 2 | wk 3 | wk 4 | wk 5 |
|---|---|---|---|---|---|---|
| Oct 15 | 100% | 21.33% | 18.60% | 19.82% | 21.85% | 15.14% |
| Oct 22 | 100% | 19.65% | 18.31% | 19.05% | 13.85% | |
| Oct 29 | 100% | 22.03% | 21.30% | 14.24% | | |
| Nov 5 | 100% | 24.53% | 15.33% | | | |
| Nov 12 | 100% | 20.32% | | | | |
| Nov 19 | 100% | | | | | |

Self-checks passed: 21 cells (6+5+4+3+2+1), every week 0 is exactly 100%, and
denominators match the cohort sizes.

**Masking.** A cell is computed only if its whole week falls before
2019-12-01: `DATEADD(day, 7*(week_offset+1), cohort_week) <= '2019-12-01'`.
Without the mask, each cohort gains a trailing cell covering only Nov 26–30
(5 of 7 days) that shows falsely low retention. Wholly unobserved weeks would
then render as blank or zero. The newest cohorts hit that wall at the
earliest offset, so the chart shows a diagonal cliff that looks like "newer
customers churn faster" when it is really "we couldn't see them."

**Read the matrix by diagonal, not only by row.** Retention does not decay
smoothly. Every cohort peaks in the cell that falls in the **Nov 12–18
calendar week** and drops in Nov 19–25. That is the Nov 15–17 promotional
spike pulling people back on a calendar date, not cohort aging. Rows mix
"time since joining" with "what was happening that week."

---

## Retention matrix — purchase (secondary)

Same structure, with "retained" meaning a purchase that week.

- Week 0 is **not** 100% by construction, because most users start with a
  view: 7.33 / 6.50 / 6.20 / 5.73 / **10.15** / 4.68%. The Nov 12 cohort,
  acquired during the spike, buys the most in week 0.
- Later weeks run about **1–3%**, against 14–25% for any event. Roughly
  **1 in 10 returning users buys** in a given week.
- The Nov 12–18 calendar week is again the high point. The buyer share of
  returners peaks there at 12.6–14.7%.

**What the two definitions answer.** Any-event: *are people still coming
back?* Purchase: *are they still paying?* Any-event is primary because it is
the broader signal and weekly purchases are too sparse to read cohort trends
cleanly. Purchase retention is reported next to it because the gap between
them is the finding: **users return to browse, not to buy.**

---

## Repeat-purchase rate

Of each cohort's purchasers, the share who purchased in more than one
distinct 30-minute session.

**Definition sensitivity, whole window:** 37.75% counting purchase rows,
**27.37% counting distinct sessions (chosen)**, 23.58% counting distinct days.
Rows overcount multi-item checkouts as "repeat." Sessions count separate
buying occasions.

| cohort | raw repeat rate | days observed | **equal 12-day window** |
|---|---|---|---|
| Oct 15 | 33.36% | 47 | **19.13%** |
| Oct 22 | 30.00% | 40 | **17.61%** |
| Oct 29 | 28.41% | 33 | **18.76%** |
| Nov 5 | 25.63% | 26 | **17.35%** |
| Nov 12 | 21.43% | 19 | **18.11%** |
| Nov 19 | 19.52% | 12 | **19.52%** |

**The raw decline is an observation-window artifact, not falling loyalty.**
Raw repeat rate falls in step with days observed. When every cohort gets the
same 12-day window from its cohort start, the rates sit within a 2.2-point
band (17.35–19.52%) with no trend. Nov 19 matches across both columns
because its full window already is 12 days, which makes a built-in check.

The 12-day window is the longest every cohort can be given. It cannot tell
us whether loyalty diverges beyond day 12.

---

## Headline

About 1 in 5 new users comes back in any given later week, but only about
1 in 10 of those returners buys. Cohorts acquired across October and November
behave the same once you control for how long each was observed. The visible
differences come from the calendar (the Nov 15–17 spike) and from the
observation window, not from the users.
