# Decisions

Every substantive choice in this project, why it was made, and what it costs.

The "Decision" lines are statements of fact. The "Why" and "What it costs"
lines are the ones that matter -- if I cannot say those out loud without
reading them, I do not understand the decision yet.

Provenance note: 0.1, 0.2 and the "Why" of 0.3 are mine. The rest were drafted
for me and still need to be rewritten in my own words.

---

## Phase 0 — Load and verify

### 0.1 Two months: October and November 2019

**Decision:** Loaded `2019-Oct.csv` and `2019-Nov.csv` from the REES46
multi-category store dataset. 109,950,743 rows.

**Why these two months:** These were the only two months that exist in the
dataset.

**What it costs:** The retention horizon is capped at 5 weeks for my earliest
cohort, and the long-horizon retention is simply unobservable which becomes a
limitation line.

---

### 0.2 Cohorts start from week 3, with a two-week lookback

**Decision:** Users whose first event falls in 2019-10-01 through 2019-10-14
are treated as pre-existing, not as new. Cohorts form from 2019-10-15 onward.

**Why a lookback window at all:** A lookback window allows us to determine if a
customer has previously purchased an item before and is not a new customer to
see the existing customer retention. In addition, we could not have our cohorts
to be the week of thier first observed event because the data does not
initialize when the store first opened so we do not know for sure when a
customer first observed an item if its before our data. Early cohorts look
better since in the first week of the data the store's habitual customers will
show up casuing week 1's "new user" cohort to be larger witht he store's most
loyal existing customers. By week 5, every habitual customer has already been
claimed by an earlier week.

**Why it is carved out of October rather than sourced from earlier data:** The
dataset contains exactly two files and no data exists before 2019-10-01.

**What it does NOT fix:** This is unable to fix a customer who first purchased
something before October and purchases something again in the October to
November window since they get labeled as a new customer. They become known as
a reactivated lapsed customer and behave differently from an actual first timer
customer. No window length inside this dataset fizes this issue. In addition,
this residual is roughly constant across cohorts, so it is able to shift the
level rather than fake a new trend.

**What it costs:** 6 full weekly cohorts and a 5 day reminader between November
26th to November 30th. The longest horizon was 5 weeks. Each cohort is acquired
one week later, and every cohort shares the same hard stop at Nov 30. So each
one loses exactly one week of horizon relative to the one before it.

---

### 0.3 Empty strings load as NULL

**Decision:** `EMPTY_FIELD_AS_NULL = TRUE` in the file format, so blank
`brand` and `category_code` fields arrive as NULL rather than `''`.

**Why:** Phase 1 requires a null rate per column. If the blanks load as empty
strings then the count function will return 0 and my audit reports will be
branded as 100% populated. Group by treats '' as a real value and becomes a
group keyed on the empty string.

**What it costs / when it would be wrong:** `''` and NULL genuinely differ when
the source distinguishes "answered, and the answer is none" from "never
captured" -- here, a genuinely unbranded generic product versus a product whose
brand was not recorded. I tested whether this dataset makes that distinction
rather than assuming it. 19,821 products (9.58% of 206,876) appear with a brand
in some rows and blank in others under the same `product_id`, and a product's
brand cannot change between events, so for those the blank is definitively a
capture failure and not "this thing has no brand". There are also no sentinel
values anywhere in the column -- no `unbranded`, `none`, `n/a`, `generic` -- so
the source has no vocabulary for genuine absence. The limit of that evidence is
that 48,590 products (23.5%) are always blank, and those could genuinely be
unbranded with no way to tell them apart. The broader point is that I could not
have destroyed the distinction even if it existed: a CSV has one representation
for both cases, so if the source system ever separated them, that was lost at
export, before the load.

---

### 0.4 Typed on load, with ON_ERROR = ABORT_STATEMENT

**Decision:** Data lands directly in a typed table. No all-VARCHAR raw layer.
`event_time` is cast with `TO_TIMESTAMP_NTZ` (not `TRY_TO_`), and four columns
carry `NOT NULL`.

**Why not TRY_TO_:** `TRY_TO_TIMESTAMP_NTZ` returns NULL when it cannot parse a
value; `TO_TIMESTAMP_NTZ` raises. That difference decides where a failure shows
up. `COPY INTO` reports exactly two things about a load -- `rows_loaded` and
`errors_seen` -- and `TRY_TO_` moves a parse failure out of `errors_seen` and
into the data itself, where nothing is looking. Had the `' UTC'` strip been
wrong, `TRY_TO_` would have written NULL for all 109,950,743 rows and the load
would have reported full success with zero errors, leaving a dead `EVENT_TIME`
column underneath sessionization, cohorts and retention. `TO_` fails loudly at
load time; `TRY_TO_` fails quietly at query time, weeks later, in a number I
cannot trace back. `TRY_TO_` is the right tool when I expect dirty values and
intend to quarantine them, but only if I then count the NULLs it produced --
using it without that count is the actual antipattern. The `NOT NULL`
constraint on `EVENT_TIME` is a second, independent defense at the schema
layer: even with `TRY_TO_`, those rows could not have committed.

**Why not a raw VARCHAR layer:** The standard ELT pattern lands everything as
VARCHAR in a RAW schema and casts downstream, so malformed values survive
verbatim and re-processing never requires re-ingesting. I skipped it, and cost
is not the reason -- the whole table is 2.89 GB compressed and the COPY took
136 seconds, so a second copy would be nearly free. The first real reason is
that I already have a raw layer: the internal stage still holds both gzipped
files, and `SELECT $1, $2, $7 FROM @EFA.RAW.EVENTS_STAGE` reads the original
untyped text with no table involved, so every inspection a RAW schema would
allow is already available. The second is that a raw layer exists for
repeatability under change -- new columns, unseen dirt, an expensive source you
do not control. This is a static published dataset that will never change, it
sits on local disk, and re-running the COPY from the existing stage takes 136
seconds. For a live source I would build the raw layer. The choice is
defensible because of this dataset's properties, not because raw layers are
wrong.

**Why not ON_ERROR = CONTINUE or SKIP_FILE:** Take one malformed line in
`2019-Nov.csv` and follow each setting. `CONTINUE` skips that row, loads the
other 67,501,978, sets `errors_seen` above zero, and the statement still
succeeds -- a silent partial load that surfaces only if something explicitly
inspects `errors_seen`. `SKIP_FILE` discards the entire 67.5M-row file, leaving
October alone loaded, and also reports success; note that the date-range
assertion would still pass in that case, and only the month-completeness check
catches it. `ABORT_STATEMENT` fails the whole statement, commits nothing, and
names the file, line and column. Abort is right here because the file format is
fully specified and the dry run validated the parse on real rows, so the
expected error count is exactly zero -- any error means my understanding of the
file is wrong, which is precisely when I want to stop rather than proceed with
99.99% of the data. It also makes the load all-or-nothing, which is what makes
the reconciliation in 0.5 a strong guarantee rather than a weak one. For a
nightly ingest of dirty third-party data I would choose `CONTINUE` with a
monitored error threshold instead; blocking a pipeline on one bad row is the
wrong trade there.

---

### 0.5 Expectations derived from source, not hardcoded

**Decision:** `src/load.py` runs `wc -l` on the local files before touching
Snowflake and writes the counts to `data/manifest.json`. Every assertion in
`src/verify.py` compares against that file.

**Why this rather than hardcoding 109,950,743:** The point is not that a
derived number is inherently more trustworthy -- it is that it is compared
against something independent. The census is local truth read off the disk; the
per-file `rows_loaded` that Snowflake returns from the COPY is remote truth.
Asserting one against the other tests the transfer itself, so it catches a PUT
that uploaded only part of a file, a file that failed to upload at all, a COPY
that silently skipped a file it had already loaded, and any header or
line-ending discrepancy that shifts the count by one. A hardcoded literal
cannot test the transfer, because it is compared against nothing -- it only
proves the table matches a number I typed, and it silently becomes wrong the
moment I change which months I load.

Being precise about the limit: a derived census does **not** catch a truncated
download. If the CSV arrived short, `wc -l` would faithfully count the short
file, Snowflake would load exactly that many rows, and every assertion would
pass. That case is covered separately and crudely by the file-size floor at
`src/load.py:46`, which only rejects a file under 1 GB. A download truncated at
95% would pass everything. This is the one place where a hardcoded expected
count would actually have been stronger, and it is recorded in Open questions
rather than pretended away.

**Why the gate checks BOTH the date range and the month count:** They fail in
opposite directions. The range check asks whether MIN and MAX fall inside
2019-10-01 to 2019-12-01. That is a containment check: it verifies nothing
arrived from outside the window, but says nothing about whether the window was
filled. If the November file failed to upload and only October loaded, MIN
would be 2019-10-01 and MAX 2019-10-31, both inside the window, and the range
check passes -- while the month count sees one distinct month and fails.
Conversely, if the data were September and October, the month count would be
two and pass, while MIN falls outside the window and the range check fails. So
range catches contamination -- data from outside the intended period, or a
broken timestamp cast producing garbage dates -- and month count catches
incompleteness. The per-file row count in check 2 also catches the
missing-November case; that overlap is deliberate, because assertions are cheap
and the pattern of which ones fail together tells me what broke.

---

### 0.6 Cost controls

**Decision:** X-Small warehouse, `AUTO_SUSPEND = 60`, resource monitor with a
100-credit quota that suspends at 90%.

**Why:** The load is not what burns a trial. The COPY moved 109,950,743 rows in
136 seconds and the account has used a fraction of a credit so far. The real
risk is a warehouse left running: Snowflake bills by the second while a
warehouse is up, whether or not a query is executing, so an idle session costs
the same as a busy one. `AUTO_SUSPEND = 60` caps that exposure at a minute of
idle time. The second risk is repeated full scans -- Phases 1 through 5 run many
aggregations over 110M rows, and an unbounded exploratory loop burns credits
faster than any single load ever will. The resource monitor is the backstop for
both: a 100-credit quota that notifies at 75% and suspends at 90%, so a runaway
cannot consume the trial while I am not watching. X-Small because the COPY
finished in 136 seconds on it, and a larger warehouse costs proportionally more
per second for work that is already fast enough. I deliberately did not add a
clustering key -- auto-clustering consumes credits continuously, and at 110M
rows on an X-Small the scans are fast enough without it.

---

## Open questions

**Is a two-week lookback long enough?** Per-day first-seen users decline
monotonically through October -- 141,952, 107,732, 88,242, 78,289, 66,122 --
and have not flattened by 2019-10-15 where cohorts start. That decline is the
pre-existing user pool draining. Cohorts 1 through 3 therefore still carry
contamination. Extending the lookback to all of October would clean them up but
leaves roughly 4 cohorts with a 4-week horizon, all inside Black Friday. With
two months of data I cannot have both clean cohorts and a usable horizon.
Undecided.

**`brand` is not a stable attribute of `product_id`.** 19,821 products (9.58%)
appear both branded and blank. If Phase 3 breaks drop-off down by brand I need
a rule -- backfill each product's brand from its non-null rows, take the mode,
or leave it -- and 15,331,243 events currently have no brand to group by.
Whether `category_code` (32.2% null) behaves the same way is unchecked.

**The gate cannot detect a partially truncated download.** See 0.5. The size
floor rejects a file under 1 GB; a file truncated at 95% passes every check.
A checksum against a published hash would close this, if one exists.
