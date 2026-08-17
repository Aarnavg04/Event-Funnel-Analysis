# Build 2 — Event-Level Funnel, Retention & Cohort Analysis

## Objective

Answer a product question from raw event data, in Snowflake, with the same process
discipline as `email-campaign-experiment-analysis`.

The deliverable is not a notebook of charts. It is a README that opens with **the
answer**, a documented metric layer, and an honest limitations section.

---

## Data

**eCommerce behavior data from a multi-category store** (Kaggle, REES46).
Columns: `event_time`, `event_type` (view / cart / purchase), `product_id`,
`category_id`, `category_code`, `brand`, `price`, `user_id`, `user_session`.

Use **two consecutive months** (~80M rows). Do not use the full seven months on a
trial account. Two months is enough for weekly cohorts with real observation
windows, and ~80M rows is a legitimate "tens of millions" claim.

Alternative if the above is unwieldy: **RetailRocket ecommerce dataset**
(~2.7M events). Smaller, cleaner, same funnel semantics. Prefer the larger one
if the load succeeds.

---

## Stack

- **Snowflake** — metric layer. All aggregation, sessionization, funnel, cohort
  logic in SQL. Load via internal stage + `COPY INTO`.
- **Python** — only what SQL cannot do: significance tests on metric movements,
  plots, any bootstrap.
- **Git** — same history discipline as the experiment repo.
- **dbt** (stretch, only if the core is done) — model the metric layer as
  `staging → intermediate → marts`. Named by Hasbro and increasingly common.

Snowflake free trial is **30 days / $400 credits**. Do not start it until you are
ready to work. Use an XS warehouse with auto-suspend at 60 seconds.

---

## Phases

### Phase 0 — Load and verify
`COPY INTO` from stage. Verification exits non-zero unless row count, distinct
`event_type` values, and date range match expectations. Same pattern as
`src/db.py` in the experiment repo — a silent partial load must not pass.

### Phase 1 — Data quality gate (before any metric)
Run and document:
- Row count, null rate per column
- `event_type` distribution
- **Funnel coherence**: does every `purchase` have a prior `cart` in the same
  session? Almost certainly not — quantify it. This is a finding, not a bug.
- Duplicate events (same user, product, type, timestamp)
- `price` distribution and outliers
- Sessions per user, events per session — check the tail

Write down anything that changes the analysis plan, as you did with the
degenerate p99 winsorization.

### Phase 2 — Sessionization
Define sessions with a **30-minute inactivity rule** using SQL window functions
(`LAG` on `event_time` partitioned by user).

Note the dataset ships a `user_session` column. Compute your own anyway, then
compare. Where they disagree and why is genuinely interesting and shows you
didn't take a provided column on faith.

State the 30-minute choice as a choice, with its rationale.

### Phase 3 — Funnel
`view → cart → purchase`, computed two ways:
- **Session-level**: of sessions with a view, what share reach cart, then purchase
- **User-level**: of users active in a period, what share ever convert

These answer different questions. Report both and say which one a PM should use
for which decision.

Break drop-off down by at least one dimension (category or brand) and identify
where the largest absolute loss sits — not the largest rate, the largest volume.

### Phase 4 — Retention and cohorts
**This is the part that has to be right.**

- Cohort = users grouped by **week of first observed event**. Time-based. This is
  what "cohort" means; purchase-frequency tiers are segments, not cohorts.
- Build a weekly retention matrix: cohort × weeks-since-acquisition.
- **Truncate honestly.** A cohort acquired in the final week cannot have week-4
  retention. Do not let partial observation windows render as decay. Either mask
  those cells or state the observation cutoff explicitly.
- Define "retained" precisely: any event? a view? a purchase? Pick one as
  primary, report at least one alternative, and say why the choice matters.
- Compute repeat-purchase rate by cohort as a secondary metric.

### Phase 5 — One diagnostic
Pick a metric that moves across the two months. Investigate why.

Decompose it — mix shift vs. rate change is the classic split. Was conversion
down because users converted less, or because traffic shifted toward
lower-converting categories? Several job descriptions ask explicitly for
"root cause of metric movements"; this phase is that.

### Phase 6 — Decision memo
One page, non-technical reader. What you found, what you recommend, what you are
not confident about.

---

## Limitations to state (non-exhaustive)

- No user attributes, no acquisition channel, no marketing spend — cannot do
  attribution or LTV, and should not pretend to.
- Two months is short for retention. Long-horizon retention is unobservable here.
- Observational data. Everything is correlational; no causal claims.
- No guardrail metrics (returns, complaints, support contacts).
- Sessionization threshold is a convention, not ground truth.

---

## Non-goals

- Do not build a dashboard. The README is the deliverable.
- Do not build a churn prediction model. That is a different project and it
  dilutes this one.
- Do not claim petabyte or "big data" scale. Tens of millions of rows is what
  this is, and saying so plainly is a credibility signal.

---

## Definition of done

- README opens with the answer, before methodology
- Retention matrix correctly truncated for partial observation
- Both funnel definitions reported and distinguished
- Limitations section written without hedging
- Verification assertions in code, not just prose
- Runs end to end from a clean clone
