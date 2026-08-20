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
