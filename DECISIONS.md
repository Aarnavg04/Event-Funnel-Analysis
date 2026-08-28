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

## Open questions

<!-- Anything I noticed but have not resolved. Phase 1 will add to this. -->

**Is a two-week lookback long enough?** Per-day first-seen users decline
monotonically through October -- 141,952, 107,732, 88,242, 78,289, 66,122 --
and have not flattened by 2019-10-15 where cohorts start. That decline is the
pre-existing user pool draining, so cohorts 1 through 3 still carry
contamination. Extending the lookback to all of October would clean them up but
leaves roughly 4 cohorts with a 4-week horizon, all inside Black Friday. With
two months of data I cannot have both clean cohorts and a usable horizon.
UNDECIDED -- this shapes Phase 4.

**`brand` is not a stable attribute of `product_id`.** 19,821 products (9.58%)
appear both branded and blank. If Phase 3 breaks drop-off down by brand I need
a rule -- backfill each product's brand from its non-null rows, take the mode,
or leave it -- and 15,331,243 events currently have no brand to group by.
Whether `category_code` (32.2% null) behaves the same way is unchecked.

**The gate cannot detect a partially truncated download.** See 0.5. The size
floor rejects a file under 1 GB; a file truncated at 95% passes every check.
A checksum against a published hash would close this, if one exists.
