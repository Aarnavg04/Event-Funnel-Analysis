"""Phase 5: run the hand-written mix-shift decomposition, then check it.

Usage:
    .venv/bin/python src/mix_shift.py

The decomposition lives in sql/50_mix_shift.sql and is written by hand. This
module does the parts the working protocol assigns to me: running it, the
identity check against the headline rates, and three robustness checks --
baseline sensitivity, centered per-category mix, and the Nov 15-17 spike
excluded. src/run_all.py calls decompose() for the same numbers.
"""

from __future__ import annotations

import sys

from config import REPO_ROOT, connect, fetch, named_queries, run

SQL = REPO_ROOT / "sql" / "50_mix_shift.sql"

# Same pairs grain as the hand-written query, plus the pair's first timestamp
# so the spike days can be carved out.
HEADLINE = """
WITH pairs AS (
    SELECT
        DATE_TRUNC('month', MIN(EVENT_TIME)) AS month,
        MIN(EVENT_TIME) AS first_event,
        COUNT_IF(EVENT_TYPE = 'cart') > 0 AS has_cart,
        COUNT_IF(EVENT_TYPE = 'purchase') > 0 AS has_purchase
    FROM EFA.ANALYTICS.EVENTS_SESSIONIZED
    GROUP BY USER_ID, SESSION_NUM_30,
        COALESCE(SPLIT_PART(CATEGORY_CODE, '.', 1), 'uncategorized')
)
SELECT
    IFF(first_event >= '2019-11-15' AND first_event < '2019-11-18',
        'Nov 15-17', TO_CHAR(month, 'YYYY-MM')) AS bucket,
    COUNT(*) AS carts,
    COUNT_IF(has_purchase) / COUNT(*) AS rate
FROM pairs
WHERE has_cart
GROUP BY bucket
ORDER BY bucket
"""


def user_query() -> tuple[str, str]:
    """Return (full query, CTEs up to and including side_by_side)."""
    full = named_queries(SQL)["mix_shift"]
    full = full[full.index("WITH"):]
    code = "\n".join(line.split("--", 1)[0] for line in full.splitlines())
    if "..." in code:
        sys.exit("FAIL: sql/50_mix_shift.sql still has '...' placeholders.")
    ctes = full[: full.index("decomposition AS")].strip().rstrip(",")
    return full, ctes


def decompose(conn) -> dict:
    """Run the decomposition and every check; return all numbers as floats."""
    full, ctes = user_query()
    cols, rows = fetch(conn, full)
    rows = [(r[0], *(float(v) for v in r[1:])) for r in rows]
    total = next(r for r in rows if r[0] == "TOTAL")

    head = {b: (n, float(r)) for b, n, r in run(conn, HEADLINE)}
    oct_n, oct_r = head["2019-10"]
    spike_n, spike_r = head["Nov 15-17"]
    rest_n, rest_r = head["2019-11"]
    nov_n = spike_n + rest_n
    nov_r = (spike_n * spike_r + rest_n * rest_r) / nov_n

    # Each two-term split folds the interaction into one side; each pair
    # sums exactly to the total change.
    sens = [float(v) for v in run(conn, ctes + """
        SELECT
            SUM((nov_share - oct_share) * oct_rate),
            SUM(nov_share * (nov_rate - oct_rate)),
            SUM((nov_share - oct_share) * nov_rate),
            SUM(oct_share * (nov_rate - oct_rate)),
            SUM((nov_share - oct_share) * (oct_rate + nov_rate) / 2),
            SUM((oct_share + nov_share) / 2 * (nov_rate - oct_rate))
        FROM side_by_side""")[0]]

    centered = [(c, float(m)) for c, m in run(conn, ctes + """
        SELECT top_category,
               (nov_share - oct_share)
                 * (oct_rate - SUM(oct_share * oct_rate) OVER ()) AS centered_mix
        FROM side_by_side
        ORDER BY ABS(centered_mix) DESC""")]

    return {
        "cols": cols,
        "rows": rows,
        "mix": total[1],
        "rate": total[2],
        "interaction": total[3],
        "total": total[4],
        "oct_carts": oct_n,
        "oct_rate": oct_r,
        "nov_carts": nov_n,
        "nov_rate": nov_r,
        "delta": nov_r - oct_r,
        "spike_carts": spike_n,
        "spike_rate": spike_r,
        "rest_nov_carts": rest_n,
        "rest_nov_rate": rest_r,
        "spike_explains": rest_r - nov_r,
        "sensitivity": {
            "mix@oct_rates": sens[0], "rate@nov_shares": sens[1],
            "mix@nov_rates": sens[2], "rate@oct_shares": sens[3],
            "mix_midpoint": sens[4], "rate_midpoint": sens[5],
        },
        "centered_mix": centered,
    }


def pp(x) -> str:
    return f"{float(x) * 100:7.2f}"


def main() -> None:
    with connect() as conn:
        d = decompose(conn)

    print("== Decomposition (percentage points, Oct baseline) ==")
    print(f"  {'category':16} {'mix':>7} {'rate':>7} {'inter':>7} {'total':>7}")
    for c, m, r, i, t in d["rows"]:
        print(f"  {c:16} {pp(m)} {pp(r)} {pp(i)} {pp(t)}")

    print("\n== Identity check ==")
    ok = abs(d["total"] - d["delta"]) < 1e-6
    print(f"  Oct {d['oct_rate']*100:.2f}%  Nov {d['nov_rate']*100:.2f}%  change {d['delta']*100:.2f} pts")
    print(f"  decomposition total {d['total']*100:.2f} pts -> {'PASS' if ok else 'FAIL'}")

    s = d["sensitivity"]
    print("\n== Baseline sensitivity (convention, not principle) ==")
    print(f"  Oct baseline, 3-term   : mix {pp(d['mix'])}  rate {pp(d['rate'])}  interaction {pp(d['interaction'])}")
    print(f"  mix@Oct rates, rate@Nov shares : mix {pp(s['mix@oct_rates'])}  rate {pp(s['rate@nov_shares'])}")
    print(f"  mix@Nov rates, rate@Oct shares : mix {pp(s['mix@nov_rates'])}  rate {pp(s['rate@oct_shares'])}")
    print(f"  Midpoint (no interaction)      : mix {pp(s['mix_midpoint'])}  rate {pp(s['rate_midpoint'])}")

    print("\n== Centered per-category mix: dshare * (oct_rate - Oct overall) ==")
    print("  (raw per-row mix only sums correctly; this version reads per row)")
    for c, m in d["centered_mix"][:6]:
        print(f"  {c:16} {pp(m)}")

    print("\n== Spike carved out ==")
    print(f"  Nov 15-17 pairs : {d['spike_carts']:>9,} carts at {d['spike_rate']*100:.2f}%")
    print(f"  rest of Nov     : {d['rest_nov_carts']:>9,} carts at {d['rest_nov_rate']*100:.2f}%")
    print(f"  Oct             : {d['oct_carts']:>9,} carts at {d['oct_rate']*100:.2f}%")
    print(f"  spike explains {d['spike_explains']*100:.2f} of {-d['delta']*100:.2f} pts")

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
