# Decisions

Every substantive choice in this project, why it was made, and what it costs.

Written by me, in my own words. The "Decision" lines are statements of fact.
The "Why" and "What it costs" lines are the ones that matter -- if I cannot
write those without looking anything up, I do not understand the decision yet.

---

## Phase 0 — Load and verify

### 0.1 Two months: October and November 2019

**Decision:** Loaded `2019-Oct.csv` and `2019-Nov.csv` from the REES46
multi-category store dataset. 109,950,743 rows.

**Why these two months:**
<!-- What does two consecutive months buy that one does not? What specific
     event falls inside this window, and is that a problem for Phase 5 or the
     reason Phase 5 works? --> These were the only two months that exist in the dataset. 

**What it costs:**
<!-- Two months is short for retention. How short? What is the longest
     retention horizon any cohort in this data can possibly have? --> The retention horizon is also capped at roughly 5 weeks fro my earliest cohort, and the long-horizon retention is simply unobservable which becomes a limitation line. 

---

### 0.2 Cohorts start from week 3, with a two-week lookback

**Decision:** Users whose first event falls in 2019-10-01 through 2019-10-14
are treated as pre-existing, not as new. Cohorts form from 2019-10-15 onward.

**Why a lookback window at all:**
<!-- What is wrong with "cohort = week of first observed event" on a dataset
     that starts mid-life for the store? Which direction does the bias run --
     do early cohorts look better or worse than they really are, and why? --> A lookback window allows us to determine if a customer has previously purchased an item before and is not a new customer to see the existing customer retention. In addition, we could not have our cohorts to be the week of thier first observed event because the data does not initialize when the store first opened so we do not know for sure when a customer first observed an item if its before our data. Early cohorts look better since in the first week of the data the store's habitual customers will show up casuing week 1's "new user" cohort to be larger witht he store's most loyal existing customers. By week 5, every habitual customer has already been claimed by an earlier week.

**Why it is carved out of October rather than sourced from earlier data:**
<!-- One sentence. This one is not a judgement call. --> The dataset contains exactly two files and no data exists before 2019-10-01.

**What it does NOT fix:**
<!-- A user who last purchased in August and returns in November. What does my
     lookback do about them? This is the honest limitation and I need to be the
     one who says it before an interviewer does. --> This is unable to fix a customer who first purchased something before October and purchases something again in the October to November window since they get labeled as a new customer. They become known as a reactivated lapsed customer and behave differently from an actual first timer customer. No window length inside this dataset fizes this issue. In addition, this residual is roughly constant across cohorts, so it is able to shift the level rather than fake a new trend. 

**What it costs:**
<!-- How many cohorts am I left with, and what does the observation window look
     like across them? -->  6 full weekly cohorts and a 5 day reminader between November 26th to November 30th. The longest horizon was 5 weeks. Each cohort is acquired one week later, and every cohort shares the same hard stop at Nov 30. So each one loses exactly one week of horizon relative to the one before it

---

### 0.3 Empty strings load as NULL

**Decision:** `EMPTY_FIELD_AS_NULL = TRUE` in the file format, so blank
`brand` and `category_code` fields arrive as NULL rather than `''`.

**Why:**
<!-- Two reasons: one about the Phase 1 null-rate audit, one about what
     GROUP BY does if you don't. --> Phase 1 requires a null rate per column. If the blanks load as empty strings then the count function will return 0 and my audit reports will be branded as 100% populated. Group by treats '' as a real value and becomes a group keyed on the empty string. 

**What it costs / when it would be wrong:**
<!-- Is there a case where '' and NULL genuinely mean different things? Do I
     know that this dataset is not such a case, or am I assuming it? --> When '' and NULL do not mean the same thing is for answered none and never captured. I tested it rather than assuming where I discovered the same product_id appearing both branded and blank where blank must be capture failure, since a product's brand can't change between events. 19,821 of 206,876 products were mixed and there were zero sentinel values (unbranded/none/generic). If the distinction existed it died at export and not at load.
---

### 0.4 Typed on load, with ON_ERROR = ABORT_STATEMENT

**Decision:** Data lands directly in a typed table. No all-VARCHAR raw layer.
`event_time` is cast with `TO_TIMESTAMP_NTZ` (not `TRY_TO_`), and four columns
carry `NOT NULL`.

**Why not TRY_TO_:**
<!-- What does TRY_TO_ do on a parse failure, and why is that specifically
     dangerous when combined with a row-count check that passes? --> Try_TO_ returns NULL while TO raises an error. COPY reports only rows_loaded + errors_seen. TRY_TO is able to move the fiallure out of errors_seen and into the data. Wrong strip with TRY_TO can lead to 110 million NULL rows which will still report a successful load. THis will still cause the data to have dead columns underneath everything.

**Why not a raw VARCHAR layer:**
<!-- This is the standard ELT pattern and I chose against it. What does it buy,
     what does it cost here, and what makes this dataset a case where skipping
     it is defensible? --> The standard approach is usally to load everything as text first, then convert it later. I alreadt have the original which is in a zip file still in the Snowflake stage. I can read them as plain text any time wuthout touching the table I created. Keeping raw text matters mostly when the source might change, or is hard to retrieve. This file is published which allows me to retrieve it any time I want requiring me not to have a raw text version of the file. 

**Why not ON_ERROR = CONTINUE or SKIP_FILE:**
<!-- What does each of those do to 110M rows when one line is malformed? --> Continue is able to skip the line with the error and laod all of the other lines causing me to quietly miss a row. SKIP_FILE throws away the entire November file while still reporting success. This causes me to only have the October data inside the window. Abort_statement causes the whole load to fail and have nothing save. Instead, I picked abort because I know exactly what this file looks like and I am able to also test the partsing on real rows first. If I get an error, my understanding of the file is wrong causing me to stop instead of carrying on or continuing with the parts that succesfully load. 

---

### 0.5 Expectations derived from source, not hardcoded

**Decision:** `src/load.py` runs `wc -l` on the local files before touching
Snowflake and writes the counts to `data/manifest.json`. Every assertion in
`src/verify.py` compares against that file.

**Why this rather than hardcoding 109,950,743:**
<!-- What failure does the derived count catch that a hardcoded literal cannot?
     Name the specific scenario. --> If I am hardcoding the number, I am checking the table against a number I made up which can cause issues if typed wrong. Instead I count the lines on my laptop and compare that to the numbers loaded in Snowflake which gives me two spearate sources. If they disagree, we will instantly know if something is wrong. This will also be able to catch an upload that died halfway, a file that never uploaded, and Snowflake skipping a file it had already seen before. However, this does not catch a download that arrived incomplete. 

**Why the gate checks BOTH the date range and the month count:**
<!-- These look redundant. Describe the exact failure where one passes and the
     other fails. --> We still want to check both the date range and the month count to see if no extra data was loaded in. The month check sees if there two different months and if there is only one it fails. One check is able to catch extra data that shouldn't be there while the other catches missing data that shouldn't be there. For example, November never uploads. Earlies date Oct 1, latest Oct 31 which are both inside the window causing the range check pass. With only one check, half the data will not load and be gone. The month count is required since it will see one month and fail. Overall, the date range checks if there is extra data and the month count checks if there is any missing data from the selected months.   

---

### 0.6 Cost controls

**Decision:** X-Small warehouse, `AUTO_SUSPEND = 60`, resource monitor with a
100-credit quota that suspends at 90%.

**Why:**
<!-- What actually burns a Snowflake trial? It is not the load -- the COPY took
     136 seconds. What is the real risk? --> Loading the data was not expensive since it is only 110 million rows which takes around 136 seconds. The actual costs is leaving the warehouse switched on. Snowflake charges per second while it's running, whether or not anyone is querying it. Auto-suspend at 60 seconds means it turns itself off. The other main cost is running lots of big queries. Phases 1-5 scan 110 million rows many times. Using meaningless big queries can burn through my free trial credits very quickly. Having a resource monitor acts as a safety net where it can warn me when I have used 75% of my credits and shutting the warehouse off at 90%. X-small becauses 136 is already fasty enough. A bigger warehouse costs proportionally more per second for work that's quick either way.

---

## Phase 1 — Data quality profile

### 1.1 Duplicates measured, not deduplicated

**Decision:** `sql/10_profile.sql` duplicates block. Cart: 71,966 groups,
126,996 excess rows (3.21% of all cart events), largest group 78 identical
rows. Purchase: 85 groups, 85 excess rows (0.005%). No rows removed from
`EFA.RAW.EVENTS`.

**Why measure rather than dedupe:**
<!-- The dataset has no quantity column. What would deduping silently do to
     revenue and purchase-volume numbers if a repeated purchase row actually
     represented buying two of an item? --> We want to measure and not dedupe to not reduce the revenue of potential customers who had duplicate orders. There is no actual quantity column, so a repeated purchased row could indicate a customer bought two items. If we actually deduped we would silently remove the repeated purchase if someone bought two which would be changed to one. 

**How my reasoning changed after measuring:**
<!-- Before measuring, the concern was that dedup could undercount revenue.
     The purchase duplicate rate came back at 0.005%. What does that do to the
     strength of that original argument? What is the honest reason to keep
     duplicates now, and is it the same reason I started with? --> The 0.005% purchase duplicate rate means the original revenue-protection argument doesn't hold much weight anymore. The honest reason to keep duplicates now is that they're negligible for purchases and I'd rather not modify raw data for that small an effect. 

**What it costs:**
<!-- Cart duplicates are 3.21%, not negligible. If a later metric counts cart
     EVENTS (not just "did this session/user ever cart"), what does it need to
     decide about that 3.21%? --> Due to the duplicates, we would have to decide whether to count raw cart vents or DISTINCT (session, product) carts, and that choice needs to be stated wherever cart counts shows up.
---

### 1.2 Session identity: `user_session`, provisional

**Decision:** `session_integrity` block run against the shipped `USER_SESSION`
column. 96.4% of sessions run 30 minutes or under; 819,408 (3.56%) exceed 30
minutes; max duration 5,248,873s (60.7 days) against a 61-day dataset. 939
sessions (0.004%) map to more than one `USER_ID`, max 3.

**Why provisional:**
<!-- Phase 2 computes sessions independently with a 30-minute rule. What is
     the relationship between this measurement and that one -- what should the
     comparison look like if the 30-minute rule is doing what it is supposed
     to? --> As we currently know, USER_SESSION is a column the dataset was created with. To check this rule we would have to answer the question of whether it is possible for any single gap between two consecutive events inside a session to exceed 30 minutes if a session's total duration is 30 minutes or less. No, a gap inside a session can never exceed the session's own total duration. For example, if a session has three events at 10:00, 10:05, and 10:28 the total span of the session would be 28 minutes. No gap between two consecutive events in this session could ever be greater than that total session duration. Overall, this 30-minute-inactivity rule mathematically cannot split any of the 96.4% of sessions that already run 30 minutes or under. This measurement is against someone else's definition of how long a USER_SESSION should be and Phase 2 is where I discover if my own definition agrees. We should see in Phase 2 that the 96.4% should be unchanged and the other 819,408 get split into two or more separate sessions by the window function. 

**What the multi-user sessions mean for how Phase 2 must be built:**
<!-- 939 is tiny, but what does it prove about USER_SESSION as a key? If a
     sessionization window function grouped by USER_SESSION alone instead of
     by USER_ID, what would go wrong? -->  939 sessions mapping to more than one USER_ID indicate how USER_SESSION values aren't guaranteed unique to one user. 939 is tiny in count (0.004%) but not negligible in consequence, because each one silently corrupts two or three users' data with no signal that it happened.However, this proves that USER_SESSION cannot be partioned or used a primary key since the 939 sessions would pull together events from different people into one group. My lag would then compute a time gap between, two different people's event times who would have unrelated events which would be wrongly treated as consecutive activity by the same person. This would corrupt the session for both users at once, and also corrupt anything built on top of it such as funnel or retention. To fix this issue we should partition by USER_ID and never by USER_SESSION. 

---

### 1.3 Funnel coherence: matched on `product_id`, `MIN` not `MAX`

**Decision:** `sql/11_coherence.sql`. Coherence tested per purchase against two
collapsed cart tables -- same session + product, and same user + product,
across any session -- each collapsed with `MIN(EVENT_TIME)`, compared with
`<=`. Result: same-session 65.92%, any-session-ever 69.28%, no cart anywhere
27.44%.

**Why match on the same `product_id`, not just any cart in the session:**
<!-- What weaker, less useful question would "any cart in the session" be
     answering instead? --> Matching on the same product_id lets us compare the same product and not different products that were carted and then bought. For example, carting a bike but buying a toothbrush in the same session.

**Why `MIN(EVENT_TIME)` and not `MAX`:**
<!-- Walk through one session with a cart before the purchase AND a cart after
     it. What does MAX get wrong there, and in which direction -- does it
     over- or undercount real coherence? --> Imagine a sesison has three events. Carting the item at 10:00, purchashing it at 10:05, and carting the item at 10:10. The aggregate max function would report the 10:10 time and will fail under the purchases_with_prior_cart_same_session or purchases_with_prior_cart_ever since the time is after the purchase time. The min function acts as a safety net to make sure the cart time is before the purchase time. This purchase genuinely had a prior cart, MAX reports it as not coherent, so MAX would undercount which indicates real matches get lost, never invented.

**What the result means:**
<!-- Same-session and any-session-ever are only 3.36 points apart, but both
     are far short of 100%. What does that gap (or lack of it) rule in or rule
     out as the explanation for the missing third of purchases? --> The gap indicates that a third of users do not cart the item they are going to purchase at all and just purchase it. The gap of 3.36 is small, which indicates there is not that much of an increase from widenning the gap from the same session to earlier session ever. This result articulates how cross-session behavior like carting an item Monday and purchasing it Wednesday is a minor effect, and does not explain the missing third. Therefore, the 27.44% are seen not carting at all and just purchasing their items.

---

### 1.4 Tie rule: `<=`, turned out not to matter

**Decision:** Chose `<=` over strict `<` so a cart and purchase landing in the
same second would still count as coherent. Measured result: zero purchases
matched only by a tie; the 1st-percentile cart-to-purchase gap is 9 seconds.

**Why this turned out not to matter:**
<!-- What does zero tie-only matches tell you about whether the logger ever
     writes a cart and a purchase in the same second? --> This turned out not to matter since there were no instances of a user carting and purchasing an item in the same second. The fastest someone carted and purchased was 9 seconds which indicate that the decision to choose <= over < was not required.

**Was the decision still worth making in advance, given it ended up moot:**
<!-- You made this call before you had this data. Was that the wrong time to
     make it? --> I initally made this decision as a harmless safety net to include potential users who would cart and purchase in the same second. Since I did not initally know the 9-second gap, I was guarding against a same-second collision since it was a reasonable preccaution. In addition, it has no additional cost since it is just a different operator. It is able to protect against a real category of risk which includes timestamp ties from any source such as network malfunctions, batched writes, and clock rounding. The fact that this dataset's logger turned out to be clean is what we were able to learn afterwards and not evidence the precaution was misguided.
---

### 1.5 Heavy tails and possible bots: report now, decide per metric later

**Decision:** No exclusion rule applied anywhere in Phase 1. Distributions
reported instead: 35.92% of sessions are single-event, session max 22,542
sessions for one user, event max 22,929 events for one user.

**Why per-metric rather than one blanket rule:**
<!-- Different Phase 3+ metrics count different things -- session counts,
     event counts, purchases. Why might the right exclusion threshold differ
     between them, such that one rule applied now would be wrong for some of
     them later? --> If we only have one blanket rule rather than a per-metric exclusion rule it would not be able to adapt to certain metrics and leave out critical data. For example, someone with 22,542 sessions is almost certainly a bot for a session-count metric, but that same person might still have made a handful of completely genuine purchases mixed in, therefore, excluding them from a purchase-based metric could throw away real revenue that a session-count exclusion rule would have correctly flagged as suspicious.

**What the current evidence suggests about whether exclusion is even needed
yet:**
<!-- Is there evidence in the percentiles that the extreme tail is large
     enough to distort a typical Phase 3 metric, or small enough to defer? --> The tail maxima of session max 22,542 sessions for one user and event max 22,929 events for one user are not substantial pieces of evidence even though having roughly 375 sessions a day for two straight months is very suspicious and most likely indicates a bot. Just because the max is extreme does not indicate most of the data is highly skewed since it doesn't yet establish whether they're common enough to distort a typical Phase 3 metric. 

---

### 1.6 Price profiled by `event_type`; `price = 0` treated as missing

**Decision:** `price_by_type` run separately per event type rather than over
the whole table. `price = 0` found in 252,203 views and 4,558 carts, and in
**zero** of 1,659,788 purchases. 

**Why split by event_type:**
<!-- 94.89% of rows are views. What would a single whole-table price
     distribution actually be measuring, versus what someone reading "price
     distribution" would assume it measures? --> The main assumption is that if we just had the price distribution it would just give us what things cost from the customer's perspective. Since 94.89% of the whole-table aggregate are rows of views, the avg(price) would just give us the distirubtion of prices attached to things people looked at and not what they bought. It's mainly influenced by browsing behavior and not purchasing behavior. Splitting by event_type lets us see the price distribution by putchasing, carting, and browsing variations. In addition, once split by purchase event type, the purchasing distirbution will then accurately output the right data which won't be heavily influenced by viewing data. 

**Why treat `price = 0` as missing rather than a genuine free item:**
<!-- Zero purchases at price = 0, out of 1.66 million. If free items existed
     and people could buy them, what would you expect that count to look like
     instead? --> Suppose we genuinely meant this item was free rather than the price wasn't captured. If free items really existed in the catalog and people were free to buy them, would we expect the purcahse count at that price to look exactly zero forrever. Furthermore, "exactly zero" itself is informative since it's not just a free low number but the complete absence of an event type that should be trivially easy to trigger since free items are usually the easiest thing to get someone to buy. 

---

### 1.7 Phase 3 funnel definition: reach-based primary, coherence as caveat

**Decision:** The Phase 3 session-level and user-level funnels report
stage-reach (does a session/user have >=1 cart event, >=1 purchase event) as
the primary metric, not the strict same-session product-matched sequence
tested in 1.3. The coherence numbers (65.92% same-session, 27.44% no cart
anywhere) are reported alongside as a disclosed caveat, not folded into the
primary rate.

**Why reach-based rather than strict sequential as the primary metric:**
<!-- What would a strict, product-matched sequential funnel do to the reported
     purchase-step conversion rate, given 1.3's numbers? Is that closer to or
     further from what "share of sessions that purchased" should mean to
     someone reading it? --> We utilize reach-based rather than strict sequential as the primary metric since 34.08% of purchases have no prior cart in the same session. If the funnel's "reached purchase" step required that same-session, same-product sequence then we wouldn't know what to do with that percentage of customers. Even though they're real purchases they wouldn't be highlighted and counted by the funnel since they never utilized the cart for that item in that session. Therefore, it makes the reported purchase-step rate further from what "share of sessions that purchased" should actually mean. 

**Why not report reach-based alone, with no caveat:**
<!-- If someone reads a funnel that just says "X% of sessions that carted went
     on to purchase," what would they wrongly assume cart is doing for every
     one of those purchases, given what 1.3 actually found? --> If someone reads a funnel that just proclaims "X% of sessions that carted went on to purchase," they would assume the cart causes or directly preceded the sale of an item. However, from 1.3 we know that 27.44% of purchases have no cart event for that product anywhere in the dataset, and 34.08% have none in the same session. Therefore, an impactful chunk of the purchases measured through our funnel are not actually preceded by the cart that we are crediting.
---

## Phase 2 — Sessionization


### 2.1 30-minute inactivity rule, with 10 and 60 measured alongside

**Decision:** `sql/20_sessionize.sql`. Sessions cut on a gap strictly greater
than 1800 seconds, partitioned by `USER_ID`. 10- and 60-minute variants computed
in the same pass. Session-level purchase conversion: 6.44% @10min, 6.86%
@30min, 7.02% @60min -- a 9% relative swing. Session counts: 20,495,962 /
18,756,054 / 17,987,818.

**Why measure the sensitivity instead of calling 30 minutes a convention:**
<!-- 30 minutes is inherited from Google Analytics, not derived from this data.
     The sensitivity table turns that from an admission into a demonstrated
     claim. What does the 6.44% -> 7.02% swing prove about what a session-level
     conversion rate IS, and what does that imply about reporting one without
     stating the threshold? Connect it to why Phase 3 also reports a
     user-level funnel. --> Even though the 30 minute session time is the standard as seen from Google Analytics, I wanted to test other session times such as 10 minutes and 60 minutes to compare and contrast between the session conversion rates and the session counts for all of the different session variations. This allows the sensitivity findings to convert from an  admission into a demonstrated claim. Since the relative swing is 9% we can conclude that the session conversion rate is sensitive to increases in the session duration. Furthermore, the swing proves that the session-level rate is partly an artifact of a modeling choice, and not purely a measurement of behavior since two different people using different thresholds would report different "true" conversion rates for the identical underlying data. The connection to the user-level funnel is that the user-level rate (13.12%) is invariant to this threshold entirely since no session boundary is involved. Furthermore, the session-level number is useful but threshold-dependent the user-level number is the metric I would trust for a claim of the conversion rate increasing an X amount.

---

### 2.2 Our sessions vs the shipped `user_session`

**Decision:** 18,756,054 sessions at 30 minutes against 23,016,650 shipped --
18.51% fewer. We split 407,943 shipped sessions (1.77%); 2,917,102 of ours
(15.55%) merge two or more shipped ones, up to 1,705 in one case. Zero
single-user shipped sessions of <=30 minutes were split. The shipped column cuts
new sessions after gaps as short as 176 seconds.

**Why the count fell, and what that says about what `user_session` actually is:**
<!-- Finding 1.2 predicted splitting and that was wrong. Explain how the count
     can drop 18.51% while zero short sessions are split -- the two checks
     measure opposite operations. Then: if the shipped column starts a new
     session after 176 seconds of inactivity, what is it more likely tracking
     than a browsing session? This is the "why do my sessions differ from
     theirs" answer I have to give unaided. -->  When one shipped session splits into two, the split adds one session count to the total. When two shipped sessions merge into one, the total count will decrease by 1 since the two separate sessions are combined into 1 session. Therefore the net effect is negative, since merges vastly outnumber splits. Our data proved that 15.55% sessions were actually merged. The number of sessions actually split were 1.77%. If the shipped column starts a new session after 176 seconds of inactivity, it is more likely tracking a single page visit or a browser tab rather than a browsing session. Some session-tracking systems mint a new session ID on things like a new tab, a referrer change, or a technical page-load event, not on the shopper actually going away.

---

### 2.3 `ROW_NUMBER` tiebreaker -- supersedes decision (d)

**Decision:** Both `LAG` and `SUM` order by a `ROW_NUMBER()` surrogate computed
once per user, not by `EVENT_TIME`. Before this fix, 500 sessions contained gaps
of up to 2,843,526 seconds (33 days). Session counts and conversion rates were
identical before and after.

**Why ties needed a tiebreaker after all:**
<!-- Decision (d) said no tiebreaker was needed: tied events have a zero gap
     between them so they land in the same session whichever order the sort
     picks. That reasoning contained a hidden assumption about LAG and SUM.
     Name the assumption, say why it is false, and trace what happened to the
     cart at 2019-11-11 19:36:03. Then: the aggregates did not move at all --
     does that make it a real bug or not? --> Ties needed a tiebreaker after all since the window functions LAG and SUM can vary on which rows they order on ties. I initially assumed that SQL would consistently order the rows for both the window functions however, after running the function I found this to be false. I had to assign a row number to each row in order to get rid of ties and keep the LAG and SUM windows consistent. Furthermore, the actual cart at 2019-11-11 19:36:03 has LAG treat view coming after cart in its ordering, causing view to look back across 33 days and raising a new-session flag. SUM processed the pair in the opposite order having cart first before the running total had incremented. This caused cart to stay in the old session while view started the new one. Since the aggregates did not move at all, the error was too small to be noticed and to shift a summary number. However, this would still be considered a real bug even if it doesn't noticeably affect the aggregates since 500 rows that show continuous sessions are still considered to be bugs and not correct.

---

### 2.4 Materialized, not recomputed

**Decision:** `EFA.ANALYTICS.EVENTS_SESSIONIZED`, 109,950,743 rows, built in
66 seconds.

**Why materialize:**
<!-- What is the expensive part of this query, how many later phases need
     sessions, and what would recomputing cost across all of them? --> The expensive part of this query which was shown to us from the build log was sorting the 110M rows by user_id, event_time. Sorting is generally a costly operation since sorting at this scale on an X-small will cause the data to be put on disks causing every downstream query that recomputed the window function from scratch to pay the same cost for sorting again in full. Since phases 3, 4, and 5 all need session boundaries, materializing the data in this phase and not every time for each phase saves us cost. Since the sorting took 66 seconds once, having to rerun the sort for the future phases instead of reading a plain table will cause us to pay the 66-second sort three additional times. Suppose we added an ad-hoc query along the way that touches the sessions, we would have to pay additional costs for every fix. Materializing turns a repeated expensive operation into a one-time cost plus cheap reads afterwards. 

---

## Phase 3 — The funnel


### 3.1 Category grain: (session, category_code), not session

**Decision:** `category_funnel` computed at (session, category_code) pairs.
NULLs coalesced to `(uncategorized)`. 130 distinct category values. Self-checks
passed: summed per-category sessions (24,894,758) exceed the 18,747,465 base;
`(uncategorized)` is 29.35% of that sum, matching the row-level 32.21% null
rate in order of magnitude.

**Why this grain, and why the "exceeds the base" self-check is proof the grain
is right rather than a red flag:**
<!-- Name the concrete failure this avoids: a session viewing electronics and
     furniture but only purchasing furniture, tagged by whole-session outcome.
     Then explain why summed per-category counts SHOULD exceed the single-
     session base -- what would it mean if they didn't? --> If you tagged a session's whole outcome onto every category it touched, a session that carted furniture+electronics but purchased only furniture would wrongly show a purchase in the electronics funnel too, inflating electronics' apparent conversion with a sale that never happened there. The category_funnel grain fixes this problem by separating them and only showing the category that was actually purchased a different row. Since we are now summing on per-category counts, users will have multiple items from different categories which will be counted in different rows causing the overall count to exceed the single session base. If they did not exceed it wouuld prove that customers are strictly stick to one category. 

---

### 3.2 Largest absolute loss on the full pipeline, not the largest rate

**Decision:** All three transitions (view->cart, cart->purchase,
view->purchase) reported as both rate and absolute count, per category.
Headline = largest absolute count lost on view->purchase. Result:
electronics.smartphone, 5,740,299 lost -- the largest of any named category.

**Why absolute loss on the full pipeline, not the largest rate:**
<!-- Somewhere in the 130 categories is one with a near-100% loss rate on a
     few hundred sessions. Why does electronics.smartphone matter more for a
     PM's roadmap than that category does, even though its rate is worse? --> Using absolute loss on the full pipeline rather than the largest rate is important for categories within the 130 that have a few hundred sessions since they will output close to a 100% loss rate and a rate-based ranking would put them at the top, wrongly, ahead of categories that actually matter more. In regard to smartphones for the electronics category, even if the actual rate of the category is moderate, focusing on the 5,740,299 lost sessions can help the PM make improvements in conversion where absolute revenue can actually move than completely fixing a tiny category with 200 lost sessions but a near 100% loss rate. Since 5,740,299 is roughly 28,700 times larger than 200, a PM's roadmap would target the smartphones over the other tiny category.

---

### 3.3 User-level period: whole window AND by month

**Decision:** Whole-window reproduces the Phase 1 census exactly
(697,470/5,316,649, 13.12%). By-month split found October inverted -- 347,118
purchasers vs 337,117 carters -- while November was not (441,638 vs 826,323).
Four independent checks confirmed this is real, not a bug: DATE_TRUNC
boundaries are correct, raw event counts show the same shape bypassing the
query entirely, an independent no-CTE query reproduces identical numbers, and
41.6% of October's purchasers (144,341 of 347,118) had zero cart events all
month. Oct+Nov totals (6,718,407) exceed the whole-window total (5,316,649) by
1,401,758 -- users active in both months.

**Explain the October inversion, and why the by-month totals summing higher
than the whole-window total is correct, not a bug:**
<!-- The 41.6%-no-cart mechanism, why October specifically given the dataset's
     start date (2019-10-01, no prior history), and why November flips. Then:
     what does it mean for "users active in a period" to overlap across
     periods when "users active in the whole window" is one fixed population? --> The October Inversion was caused since the dataset had no previous history and started on 2019-10-01. In addition, 41.6% of October's purchasers had no cart event at all for any product. The innate cause of this can be due to a share of that 41.6% of customers already being pre-existing customers of the store before October that were not shown in the data. In addition, Phase 0's lookback decision was built around people who already knew what they wanted to and bought directly with no need to browse or cart first since the data just started watching these customers mid way and not when the store started their business. November flips since the November 15th to 17th promotional spike that browses and adds to cart heavily without converting at the same pace, causing the cart-reach far ahead of purchase-reach showcasing the opposite pattern of October. The overlap is correct and not a bug since users active in October and users active in November are two separate, independently defined groups that are allowed to share members where an active user can be in both months. Users active in the whole window are different since a single group by definition is one row per user. Since October and November can share members while the whole-window count can't, summing two overlapping groups will naturally produce a total that's larger than one non-overlapping group — and that's exactly what the 1,401,758 gap is: the count of people counted twice. 

---

### 3.4 Session-level vs user-level: which for which decision

**Decision:** The spec requires stating which funnel a PM should use for which
decision. Session-level purchase rate is 6.86% at 30 minutes, and Phase 2
proved this number moves 6.44%->7.02% purely from the sessionization
threshold. User-level (13.12%) carries no such dependency.

**Write the actual guidance -- this goes in the README:**
<!-- Given the threshold-sensitivity from Phase 2, argue which metric a PM
     should reach for to track week-over-week internal trend, and which one
     they should reach for to state a headline conversion rate or compare
     against any external/competitor number. Say why the other one is the
     wrong tool for that specific job. -->When it comes to tracking a week-over-week internal trend, a PM would be more inclined to utilize the session level since they can actually detect the affect of their interventions on the scale of a single visit. The 30-minute threshold also stays fixed across every week. Even though the session level is sensitive to the threshold, it does not matter as long as the methodology doesn't change. The week-over-week movement is still apparent even if the absolute value is partly an artifact of the convention. In addition, this only holds if nobody quietly changes the sessionization rule mid-comparison. In regards to stating a headline conversion rate, or comparing against a competitor's published number, the user-level rate should be utilized. This rate carries zero dependency on a threshold nobody outside your team has agreed to, making it also useful to an external audience. Session-level would be the wrong tool here since it depends on the threshold you choose. User-level for week-over-week internal trend would fail since it is too coarse and it does not explicitly tell the PM where in a visit people drop off, only whether they ever converted, not depending on the number of sessions. Session-level for external/competitor number is dishonest since it quotes 6.86% without saying "at 30 minutes" because it implies a precision the number doesn't have.

---

### 3.5 Zero-view sessions: footnoted, not dropped

**Decision:** Checked before building (per your call to verify rather than
assume). 8,589 sessions (0.046%) have cart/purchase activity with no logged
view; 4,437 of those have a purchase. Excluded from the funnel base (base =
sessions with >=1 view, per the spec's own phrasing) and reported as a
separate footnote rather than silently dropped.

**What footnoting instead of silently dropping actually buys you here:**
<!-- 0.046% will not move any headline number. So what is the footnote
     actually for -- what would change about this project's credibility if a
     reader found these 8,589 sessions themselves and noticed they were never
     mentioned? --> Instead of silently dropping these zero-view sessions, footnoting them allows us to explain this gap and builds the reader's trust. If someone finds 8,589 sessions with real purchase activity and no views that never appear anywhere in my funnel, they will be skeptical to my findings and will wonder if "that's negligible." They will also wonder, "what else did I not account or check for?" Leaving this gap allows the reader to doubt my other results in the report even if they were verifiable and are accurate. The footnote displays how I found these sessions and understood how they are purchased items likely from a deep link or missing tracking event. A silently-dropped 0.046% is faith that it didn't matter. A footnoted 0.046% is verification that it doesn't, which is worth more to my credibility than the number itself.

---

## Phase 4 — Cohorts and retention

<!-- Provenance: 4.1-4.3 answers are my own reasoning (given as interview
     answers in chat) -->

### 4.1 Masking: unobserved cells are not computed

**Decision:** A (cohort, week_offset) cell is computed only if its whole week
ends on or before 2019-12-01. 21 observable cells (6+5+4+3+2+1). Every week 0
is 100% under any-event retention.

**What the chart would look like without the mask, and why:**
The data ends on Nov 30 for every cohort, so newer cohorts run out of observable weeks at an earlier week_offset. Without the mask, two things go wrong. First, each cohort gains one last cell covering only Nov 26–30, 5 of a 7-day week, and its retention looks artificially low even though it's computed from real rows. Second, weeks we never observed have no rows at all, so a chart draws them as blank or zero. The result is a diagonal cliff that hits newer cohorts earliest and hardest: the Nov 19 cohort would look like it collapses right after week 0, and Oct 15 would look like it holds up longest. That reads as "newer customers churn faster," but nothing about behavior changed. Those are weeks we couldn't see, not weeks where users left. The mask fixes this by not computing a cell unless its whole week ends by 2019-12-01, instead of computing it and hiding it later.

---

### 4.2 "Retained" = any event (primary), purchase (secondary)

**Decision:** Any-event retention after week 0 is 14-25%. Purchase retention
is 1-3%, so about 1 in 10 returners buys. Both are reported.

**What each definition answers, and why any-event leads:**
If we only reported purchase retention, retention would look roughly ten times weaker: about 1–3% after week 0, against 14–25% for any event, because purchases happen far less often than views. Even week 0 is only 4.7–10.2% under purchase, since most users' first event is a view. Any-event retention shows overall engagement, meaning whether a user comes back to the site and looks at products at all, whether or not they buy. That's why it leads. It's the broader signal, and weekly purchases are too sparse to read cohort trends cleanly. The two definitions answer different questions: any-event asks "are they still coming back?" and purchase asks "are they still paying?" A PM looking only at purchases would see a retention crisis. One looking only at any-event would see healthy engagement. So I report both, because the gap between them is the actual finding. Only about 1 in 10 returning users buys in a given week, so people come back to browse, not to buy.

---

### 4.3 Repeat purchase: distinct sessions, compared over an equal window

**Decision:** Repeat = purchases in more than one distinct 30-min session
(27.37%, vs 37.75% by rows, 23.58% by days). The raw rate falls 33.36% ->
19.52% across cohorts; over an equal 12-day window every cohort is
17.35-19.52%.

**Why the raw decline is not a loyalty decline, and which number proves it:**
Days observed fall with each cohort (47, 40, 33, 26, 19, 12), and the raw repeat rate falls along with them, from 33.36% to 19.52%. Earlier cohorts simply had more days to make a second purchase. The Nov 19 cohort had only 12 days before the data ended. So the decline comes from how long we watched each cohort, not from loyalty. The proof is the equal-window comparison. When every cohort is measured over the same first 12 days from its cohort start, repeat rates sit between 17.35% and 19.52% with no trend. If newer customers were really less loyal, the decline would still show up there, and it doesn't. As a built-in check, the Nov 19 cohort comes out at 19.52% in both versions, because its full window already is 12 days. The limit: 12 days is the longest window every cohort can share, so this can't tell us whether loyalty diverges after day 12. It's the same trap as forgetting to mask in 4.1, confusing "we watched them less" with "they did less."

---

## Phase 5 — Mix shift vs rate change


### 5.1 Metric, segment, and baseline

**Decision:** Cart -> purchase rate at (session, top-level category) grain;
segmented by top-level category (14 values, all present in both months);
October as baseline. Oct 52.95% -> Nov 38.87%, -14.08 pts.

**Why this metric, why category and not spike days, and why October:**
The metric is the session-level cart → purchase rate: of the (session, category) pairs that added to cart, the share that also purchased in that category. It's where October and November diverged most in Phase 3 (event-level cart:purchase went from 1.25:1 to 3.30:1), so it's the metric with the most to explain. I segmented by top-level category because a segment has to exist in both months, and both its rate and its share of carts must be able to change. Category fits: all 14 have carts in both months, conversion differs between them, and the Nov 15–17 spike could have shifted which categories people carted. I couldn't segment by spike days vs. normal days, because October has no spike days. There's no October rate for that segment to compare against, so the decomposition breaks. Instead, I checked the spike separately (5.3). October is the baseline because it's the "before" period, and the question is how much each factor changed starting from where we were. That's a convention, not something the data decides. The other choices are checked in 5.2.

---

### 5.2 Result: mostly rate change, robust to the baseline

**Decision:** Mix -2.99, rate -11.94, interaction +0.86 (sums to -14.08 exactly).
Across all baseline conventions, mix is -2.1 to -3.0 and rate -11.1 to -11.9.
Every category's rate fell; electronics alone is -9.12 of the rate effect.

**What this says, and how you checked it isn't an artifact of the method:**
The overall rate is each category's share times its rate, added up. Between October and November both ingredients changed, so I changed one at a time while holding the other at October's value. Mix = new shares at old rates. Rate = old shares at new rates. Interaction = the leftover from both moving at once, which corrects the double count. For electronics: its share fell from 70.9% to 48.7% (mix −12.51) and its rate from 56.2% to 43.4% (rate −9.12). Those overshoot its real −18.77 drop, so the interaction is +2.86. Summed over all 14 categories, the result is mostly rate: −11.94 of −14.08 points. Every single category converted worse in November. The check is that the three parts must add up exactly to Nov overall minus Oct overall, which was computed separately from raw counts. They do, to the hundredth, and if any formula were wrong they wouldn't. If I used November as the baseline instead, the split moves by under a point (mix −2.1 to −3.0, rate −11.1 to −11.9), but rate is 80–85% of the drop either way, so the baseline choice doesn't change the conclusion. One trap: the raw per-category mix terms only mean something summed. Uncategorized shows +6.67, which looks like its growth helped. But it converts below the October average (42% vs. 52.95%), so its growth actually hurt. Because shares always sum to 1, a single row only reads correctly when measured against the average: uncategorized becomes −1.67, and it's the biggest mix contributor.

---

### 5.3 "Rate change" isn't "checkout got worse"

**Decision:** Nov 15-17 carts converted at 27.33% vs 46.80% for the rest of
November. Removing the spike recovers 7.93 of the 14.08 points.

**Why a category decomposition labels the spike as rate change, and what's
left over:**
Not necessarily. Much of the rate drop comes from the Nov 15–17 promotional spike, not Black Friday (Nov 29 is an ordinary day here). Spike-day cart pairs were 41% of November's carts and converted at 27.33%, compared with 46.80% for the rest of November. Those shoppers carted heavily in every category, so they lowered each category's rate, and a category-level decomposition counts that as rate change. It's really a shift in who was shopping, low-intent promo traffic, along a dimension I didn't segment by. That's the general failure mode: a mix shift along an unmeasured dimension always shows up as rate change, so the honest conclusion is "mostly rate within category," not "mostly rate." Removing the spike recovers 7.93 of the 14.08 points. The remaining ~6 points (52.95% → 46.80%) aren't explained by the spike or by category mix. That's the part that could be a real conversion problem, and this dataset can't say what caused it.

## Open questions


**RESOLVED -- two-week lookback stays at 2 weeks, not extended.** Per-day
first-seen users decline monotonically through October -- 141,952, 107,732,
88,242, 78,289, 66,122 -- and have not flattened by 2019-10-15 where cohorts
start, so cohorts 1 through 3 still carry contamination from pre-existing
customers. Extending to 4 weeks would clean that up but pushes cohort
formation into November, which is worse: first-seen counts rise again there,
including a promotional spike on Nov 15-17, and a 4-week lookback would leave
only ~4 November cohorts -- one of them acquired during that spike -- with at
most a 4-week horizon. Phase 3's finding that 41.6% of October's purchasers
had zero cart activity all month is corroborating evidence the contamination
is real, not just a curve shape. Decision: keep 2 weeks (6 cohorts, 5-week
max horizon), and flag cohorts 1-3 explicitly in the Phase 4 retention matrix
as carrying known residual contamination, rather than trading it for a
shorter, spike-dominated cohort study. (Corrected: this entry originally
called the November spike "Black Friday." Daily data shows the spike is
Nov 15-17; Black Friday, Nov 29, is an ordinary day in this dataset.)

**RESOLVED -- `brand` backfill deferred, not needed.** 19,821 products (9.58%)
appear both branded and blank -- a genuine capture failure, confirmed
backfillable via mode/first-non-null-value if ever needed. But nothing in
Phases 3 or 4 uses `brand` as a grouping dimension -- Phase 3's category
breakdown used `category_code` instead, and Phase 4 does not touch brand at
all. Revisit only if Phase 5's diagnostic ends up wanting a brand-level cut of
whatever metric moved; the fix is already known and cheap if that happens.

**The gate cannot detect a partially truncated download.** See 0.5. The size
floor rejects a file under 1 GB; a file truncated at 95% passes every check.
A checksum against a published hash would close this, if one exists.
