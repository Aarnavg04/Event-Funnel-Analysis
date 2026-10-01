# Phase 3 — Findings

Queries: `sql/30_funnel.sql`, written by hand. Four blocks --
`session_funnel`, `user_funnel`, `user_funnel_by_month`, `category_funnel`.

Per decision 1.7, the funnel reported here is **reach-based**: does a
session/user have >=1 of each event type, independently, not a strict
same-session same-product sequence. The coherence numbers from 1.3
(65.92% same-session, 27.44% no cart ever) are the disclosed caveat that
belongs next to every rate below.

---

## Session-level funnel (30-minute sessions)

| | count | rate |
|---|---|---|
| sessions with >=1 view (base) | 18,747,465 | -- |
| reached cart | 2,036,753 | 10.87% |
| reached purchase | 1,286,051 | 6.86% |
| single-event sessions (of base) | 5,525,909 | 29.48% |

Matches Phase 2's threshold table exactly (18,747,465 / 6.86% at 30 min) --
two independent queries, same population, same answer.

**Report this rate only with "at 30 minutes" attached.** Phase 2 proved it
moves 6.44% -> 7.02% across 10/30/60 minutes with zero change in underlying
behavior -- the number is partly a property of a parameter we chose.

8,589 sessions (0.046%) had cart/purchase activity with no logged view and are
excluded from this base by definition; 4,437 of those had a purchase. Reported
here as a footnote, not dropped silently.

---

## User-level funnel, whole window

| | count | rate |
|---|---|---|
| total users | 5,316,649 | -- |
| reached cart, ever | 1,054,133 | 19.83% |
| reached purchase, ever | 697,470 | **13.12%** |

Reproduces Phase 1's census exactly. This rate needs no threshold caveat --
it is invariant to sessionization entirely, which is what makes it the number
to quote without an asterisk.

---

## User-level funnel, by month

| month | total users | reached cart | reached purchase |
|---|---|---|---|
| Oct 2019 | 3,022,290 | 337,117 (11.15%) | 347,118 (11.48%) |
| Nov 2019 | 3,696,117 | 826,323 (22.35%) | 441,638 (11.95%) |

October is inverted: more distinct users reached purchase than reached cart.
November is not. Four independent checks confirm this is real:

1. `DATE_TRUNC` correctly buckets rows at the month boundary -- no leakage.
2. Raw event counts (bypassing the user-level query entirely) show the same
   shape: Oct cart:purchase events run 1.25:1, Nov run 3.30:1.
3. An independent query with no CTE reproduces the identical distinct-user
   counts.
4. **41.6% of October's purchasers (144,341 of 347,118) had zero cart events
   anywhere that month, for any product** -- the direct mechanism.

Plausible explanation: the dataset begins 2019-10-01 with no prior history
(same fact behind the Phase 0 lookback decision), so October's no-cart
purchasers plausibly skew toward habitual repeat customers buying directly.
November is dominated by a promotional spike on **Nov 15-17** (Fri-Sun):
daily events roughly tripled (~2.0M -> 6.2-6.5M) and daily users rose ~70%
(~285k -> ~488k), then returned to baseline on Nov 18. Those three days -- 10%
of the month -- hold **43.5% of all November cart events**, at a cart:purchase
ratio of 5.20. The rest of November still ran at 2.58, roughly double
October's 1.25, so the spike explains a large share of the flip but not all
of it. Together they push cart-reach to nearly 2.4x its October level while
purchase-reach barely moves.

*Correction:* an earlier draft of this section attributed November's surge to
Black Friday. That was asserted without checking daily data, and it is wrong
-- Black Friday (Nov 29) is an ordinary day here (286,699 users, 1.85M
events). The surge is the Nov 15-17 event.

**Self-check, and it's a finding in its own right:** Oct + Nov user totals
(6,718,407) exceed the whole-window total (5,316,649) by **1,401,758** -- the
count of users active in both months, roughly 26% of the entire user base.
Expected, not a bug: "active in a period" is allowed to overlap across
periods even though "active in the whole window" is one fixed population.

**Strong Phase 5 candidate.** The cart-to-purchase-reach ratio moves from
~1:1 in October to ~1.87:1 in November, and the mechanism is already
half-decomposed here: not a conversion-rate change, but a shift in what share
of the purchasing population used cart at all.

---

## Category breakdown (largest absolute loss)

Grain: (session, category_code) pairs, not session -- a session touching two
categories contributes to each independently, based only on that category's
own events. 130 distinct category values.

| category | sessions w/ view | lost view->purchase |
|---|---|---|
| (uncategorized) | 7,306,115 | 6,964,113 |
| **electronics.smartphone** | 6,302,364 | **5,740,299** |
| electronics.audio.headphone | 888,059 | 828,281 |
| electronics.clocks | 834,320 | 799,177 |
| electronics.video.tv | 709,436 | 665,381 |

**Electronics.smartphone carries the largest absolute loss of any named
category** -- 5.74M sessions viewed a smartphone and never purchased one.
This is the headline specifically because decision (c) asks for absolute
volume, not rate: many small categories at the bottom of the table have
near-100% loss rates on a few hundred sessions and matter far less.

(uncategorized) posts a larger raw number still, but it isn't actionable in
the same way -- there's no product team to hand a "fix uncategorized" ticket
to. Worth stating both, headlining the named category.

Self-checks: summed sessions-with-view across all categories (24,894,758)
exceeds the session-level base (18,747,465), as expected -- multi-category
sessions counted more than once, which is the entire point of this grain.
(uncategorized) is 29.35% of that sum, matching Phase 1's row-level 32.21%
null rate in the right order of magnitude.

---

## Still open

- Which of the two funnels a PM should use for which decision -- required by
  the spec ("Report both and say which one a PM should use for which
  decision"), not yet written up. Candidate framing: session-level for
  internal trend-tracking (but always with the threshold stated); user-level
  for a headline claim or any external comparison, since it carries no
  sessionization assumption at all.
- Whether to also report the category breakdown at user-level rather than
  session-level -- not attempted; session-level was judged sufficient for
  identifying where volume is lost.
