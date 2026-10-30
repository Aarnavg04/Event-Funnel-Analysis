# Phase 5 — Findings

Query: `sql/50_mix_shift.sql`. The decomposition (`segment_stats`,
`side_by_side`, `decomposition`, final SELECT) is hand-written; the `pairs`
CTE is reused from Phase 3. Checks: `src/mix_shift.py`.

---

## The question

Cart → purchase conversion fell from **52.95% in October to 38.87% in
November (−14.08 points)**. Is that because November's carts moved toward
categories that convert worse (**mix shift**), or because carts within the
same categories converted worse (**rate change**)?

- **Metric:** cart → purchase rate at (session, top-level category) grain.
  Of pairs that added to cart, the share that also purchased in that category.
- **Segment:** top-level category (14 values, NULL → `uncategorized`). All 14
  have carts in both months.
- **Baseline:** October. This is a convention; see the sensitivity check
  below.

Overall rate = Σ share × rate, so per segment:

```
mix         = (share_nov − share_oct) × rate_oct
rate        = share_oct × (rate_nov − rate_oct)
interaction = (share_nov − share_oct) × (rate_nov − rate_oct)
```

These sum exactly to the total change. **Identity check: the decomposition
total is −14.08 points, matching the headline. PASS.**

---

## Result: mostly rate, not mix

| | points | share of drop |
|---|---|---|
| Mix | −2.99 | 21% |
| **Rate** | **−11.94** | **85%** |
| Interaction | +0.86 | −6% |
| **Total** | **−14.08** | |

**Every one of the 14 categories converted worse in November.** Electronics
alone is −9.12 of the −11.94 rate points: its rate fell from 56.23% to 43.36%,
and it is the largest category (70.9% of October carts).

Mix is real but small. Electronics, the best converter, fell from 70.9% to
48.7% of carts, while `uncategorized` (42% rate) grew from 12.5% to 28.2%.

### The baseline choice doesn't change the conclusion

| convention | mix | rate |
|---|---|---|
| Oct baseline, 3-term (reported) | −2.99 | −11.94 (+0.86 interaction) |
| mix at Oct rates, rate at Nov shares | −2.99 | −11.09 |
| mix at Nov rates, rate at Oct shares | −2.14 | −11.94 |
| Midpoint (no interaction) | −2.56 | −11.51 |

Rate is 79–85% of the drop under every convention.

### Don't read the per-category mix column on its own

The raw per-row mix term for `uncategorized` is **+6.67**, which looks like
its growth *helped*. It did not. `uncategorized` converts below average, so
its growth *hurt*. Because shares always sum to 1, the raw mix terms only
mean something summed. Measured against the October overall rate,
`Δshare × (rate_oct − overall_oct)`, each row reads correctly:

| category | centered mix |
|---|---|
| uncategorized | −1.67 |
| electronics | −0.73 |
| apparel | −0.20 |
| furniture | −0.15 |

The total is unchanged (−2.99). The biggest mix contributor is the growth of
uncategorized, not the shrinking of electronics.

---

## "Rate change" is not the same as "checkout got worse"

| | cart pairs | cart → purchase |
|---|---|---|
| October | 532,795 | 52.95% |
| Nov 15–17 (spike) | 654,708 | **27.33%** |
| Rest of November | 953,080 | 46.80% |

The Nov 15–17 promotional spike produced **41% of November's cart pairs
converting at 27%**. Spike shoppers carted heavily in every category, so they
pulled down each category's rate, and a category-level decomposition counts
that as rate change. It is really a shift in *who* was shopping (low-intent
promo traffic), along a dimension the segmentation does not include.

**Removing the spike recovers 7.93 of the 14.08 points.** About 6 points
(52.95% → 46.80%) remain unexplained by either the spike or category mix.
That is the candidate for a real conversion change, and this dataset cannot
say what caused it.

**How to tell if mix and rate were confused:** a mix shift along a dimension
you did not segment by always shows up as rate change. The split depends on
the segmentation, so the conclusion is "mostly rate *within category*," not
"mostly rate."

---

## Headline

November's 14-point drop in cart → purchase conversion was not caused by
shoppers moving toward weaker categories. Mix explains only about 3 points.
It was conversion falling within every category, and more than half of that
traces to the Nov 15–17 promotion, whose shoppers carted heavily and bought
at about half the normal rate. Roughly 6 points remain after removing the
spike, and those are worth investigating.
