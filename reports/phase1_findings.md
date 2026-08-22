# Phase 1 — Findings

Interpretation of `reports/phase1_profile.md`. That file is generated; this one
is written by hand and survives regeneration.

Verdict column is the one that matters: **does this change the analysis plan?**

---

## The funnel is extremely top-heavy

| step | events | share of all rows |
|---|---|---|
| view | 104,335,509 | 94.89% |
| cart | 3,955,446 | 3.60% |
| purchase | 1,659,788 | 1.51% |

Naive event-level rates: cart/view **3.79%**, purchase/cart **41.96%**,
purchase/view **1.59%**. These are not the funnel — they ignore sessions and
users entirely, and Phase 3 computes it properly both ways. They are here as an
order-of-magnitude sanity anchor: if a Phase 3 number lands far from these,
something is wrong with the query, not with the business.

**13.12%** of users (697,470 of 5,316,649) ever purchase.

**Does not change the plan.**

---

## Sessions are tiny, and a third are a single event

Median session = **2 events**. p90 = 11. **35.92%** of sessions contain exactly
one event, and **35.94%** have zero duration (first and last event in the same
second).

This matters for Phase 3. A session with one event cannot exhibit a funnel, so
the session-level denominator question — *of sessions with a view, what share
reach cart* — is being asked of a population where a third of members had no
opportunity to progress. That is not a reason to exclude them; single-event
sessions are real bounces and belong in the denominator. It is a reason to
report the single-event share alongside the funnel so the rate is readable.

**Changes the plan:** Phase 3 must report the single-event session share next to
the session-level funnel.

---

## `user_session` is mostly session-like, with a tail that is not

| bucket | sessions | share |
|---|---|---|
| all | 23,016,650 | — |
| > 30 min | 819,408 | 3.56% |
| > 1 hour | 342,364 | 1.49% |
| > 1 day | 38,168 | 0.17% |
| > 7 days | 7,463 | 0.03% |
| > 30 days | 548 | 0.00% |

Max duration is **5,248,873 s = 60.7 days**, against a dataset 61 days long.
So the shipped column is broadly consistent with a ~30-minute convention for
96.4% of sessions, and definitively not inactivity-based for the tail.

This is the concrete target for Phase 2: our own 30-minute rule will split those
819,408 sessions and leave the other 96.4% alone. That is the expected shape of
the disagreement, and if our sessionization disagrees far more widely than that,
our window function is wrong.

Also: **939 sessions map to more than one `user_id`** (max 3). Tiny — 0.004% —
but it means `user_session` is not unique per user, so any sessionization must
partition by user, not by session id alone.

**Changes the plan:** gives Phase 2 a quantified prediction to check against.

---

## `category_code` behaves completely differently from `brand`

The Phase 0 brand finding was that 19,821 products (9.58%) appear both branded
and blank, so those blanks are capture failures. `category_code` was unchecked.
It is **not** the same:

| | products | share |
|---|---|---|
| mixed null and set | **0** | 0.00% |
| always null | 118,185 | 57.13% |
| always set | 88,691 | 42.87% |
| contradictory (2+ distinct values) | 0 | 0.00% |

Zero mixed, zero contradictory. `category_code` is a perfectly stable product
attribute: a product either always has one or never does.

That inverts the conclusion. Missing `brand` is a **capture failure** and can be
backfilled from the product's other rows. Missing `category_code` is a **genuine
absence** — the product has no category assigned, and there is nothing to
backfill from.

Note the row-vs-product gap: `category_code` is 32.21% null by row but 57.13% by
product. Uncategorised products are disproportionately low-traffic.

**Changes the plan:** Phase 3's category breakdown cannot backfill. 32.21% of
events must go into an explicit "uncategorised" bucket and be *reported*, not
silently dropped — dropping them would quietly remove a third of the data from
the denominator.

Smaller: **277 products carry more than one brand** and **22 carry more than one
`category_id`**. `product_id` is not a clean key for these attributes.

---

## Duplicates are a cart problem, not a purchase problem

| event_type | groups | excess rows | max group |
|---|---|---|---|
| cart | 71,966 | 126,996 | **78** |
| view | 16,198 | 17,155 | 7 |
| purchase | 85 | 85 | 2 |

**This revises the reasoning behind decision (a).** The argument for not
deduplicating was that with no quantity column, repeated purchase rows might
*be* the quantity. That was a reasonable concern before measuring — but purchase
duplication is 85 excess rows out of 1,659,788 purchases, **0.005%**. Whatever
those 85 are, they cannot move revenue.

The decision to keep duplicates stands, but the honest reason is now "it is
negligible for purchases and I would rather not touch the data" — not "it
protects revenue accuracy."

Cart is different: 126,996 excess rows, **3.21% of all cart events**, and one
group of 78 identical (user, product, second) rows. Seventy-eight is not a
quantity; it is a client-side bug or rage-clicking.

**Changes the plan:** if any Phase 3 metric counts cart events, it needs a
stated position on the 3.21%. The session/user-level funnel is unaffected,
because it asks *did this session reach cart at all*, which is insensitive to
repeats.

---

## `price = 0` never gets purchased

256,761 rows have `price = 0`: **252,203 views, 4,558 carts, 0 purchases.**

Zero out of 1,659,788 purchases is not chance. Zero-price almost certainly means
"price not captured at event time" rather than "free item" — a genuinely free
item would occasionally be taken.

**Changes the plan:** any price-based analysis excludes `price = 0` as missing
rather than treating it as a real value of zero, which would drag every mean and
percentile down.

---

## Price barely differs across the funnel

| | p50 | mean | p99 |
|---|---|---|---|
| view | 163.77 | 291.11 | 1,705.76 |
| cart | 174.53 | 300.25 | 1,613.42 |
| purchase | 174.08 | 304.35 | 1,628.94 |

Purchased items are *slightly* more expensive than viewed ones, not less. The
intuitive hypothesis — cheap things convert better — does not hold here at the
aggregate level.

Checked and rejected: the identical maximum of 2,574.07 across all three types
looked like a price cap. It is not. The tail is smooth (2574.07, 2574.04,
2573.99, 2573.81, …) and eight distinct products sit at the top price. The
shared max is just the same expensive products being viewed, carted and bought.

**Does not change the plan**, but it is a Phase 5 candidate: if conversion moved
across the two months, price mix is one thing to decompose.

---

## Still open

- **Funnel coherence is not yet measured** — the query is being written by hand.
  Until it lands, Phase 1 is not complete and Phase 3's session-level funnel
  definition is not settled.
- Whether to backfill `brand` from each product's non-null rows. Now clearly
  *possible*; not yet decided.
- The two-week lookback length, carried over from Phase 0.
