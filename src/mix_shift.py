"""Phase 5: run the hand-written mix-shift decomposition, then check it.

Usage:
    .venv/bin/python src/mix_shift.py

The decomposition lives in sql/50_mix_shift.sql and is written by hand. This
module does the parts the working protocol assigns to me: running it, the
identity check against the headline rates, and three robustness checks --
baseline sensitivity, centered per-category mix, and the Nov 15-17 spike
excluded.
"""

from __future__ import annotations

import sys

from config import REPO_ROOT, connect, run

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
    body = SQL.read_text().split("-- name: mix_shift", 1)[1]
    full = body[body.index("WITH"):].strip().rstrip(";")
    code = "\n".join(line.split("--", 1)[0] for line in full.splitlines())
    if "..." in code:
        sys.exit("FAIL: sql/50_mix_shift.sql still has '...' placeholders.")
    ctes = full[: full.index("decomposition AS")].strip().rstrip(",")
    return full, ctes


def pp(x) -> str:
    return f"{float(x) * 100:7.2f}"


def main() -> None:
    full, ctes = user_query()
    with connect() as conn:
        print("== Decomposition (percentage points, Oct baseline) ==")
        rows = run(conn, full)
        print(f"  {'category':16} {'mix':>7} {'rate':>7} {'inter':>7} {'total':>7}")
        for c, m, r, i, t in rows:
            print(f"  {c:16} {pp(m)} {pp(r)} {pp(i)} {pp(t)}")
        total = next(r for r in rows if r[0] == "TOTAL")

        print("\n== Identity check ==")
        head = {b: (n, float(r)) for b, n, r in run(conn, HEADLINE)}
        oct_n, oct_r = head["2019-10"]
        spike_n, spike_r = head["Nov 15-17"]
        rest_n, rest_r = head["2019-11"]
        nov_r = (spike_n * spike_r + rest_n * rest_r) / (spike_n + rest_n)
        delta = nov_r - oct_r
        ok = abs(float(total[4]) - delta) < 1e-6
        print(f"  Oct {oct_r*100:.2f}%  Nov {nov_r*100:.2f}%  change {delta*100:.2f} pts")
        print(f"  decomposition total {float(total[4])*100:.2f} pts -> {'PASS' if ok else 'FAIL'}")

        print("\n== Baseline sensitivity (convention, not principle) ==")
        # Each two-term split folds the interaction into one side; each pair
        # sums exactly to the total change.
        mix_old_r, rate_new_s, mix_new_r, rate_old_s, mid_mix, mid_rate = run(conn, ctes + """
            SELECT
                SUM((nov_share - oct_share) * oct_rate),
                SUM(nov_share * (nov_rate - oct_rate)),
                SUM((nov_share - oct_share) * nov_rate),
                SUM(oct_share * (nov_rate - oct_rate)),
                SUM((nov_share - oct_share) * (oct_rate + nov_rate) / 2),
                SUM((oct_share + nov_share) / 2 * (nov_rate - oct_rate))
            FROM side_by_side""")[0]
        print(f"  Oct baseline, 3-term   : mix {pp(total[1])}  rate {pp(total[2])}  interaction {pp(total[3])}")
        print(f"  mix@Oct rates, rate@Nov shares : mix {pp(mix_old_r)}  rate {pp(rate_new_s)}")
        print(f"  mix@Nov rates, rate@Oct shares : mix {pp(mix_new_r)}  rate {pp(rate_old_s)}")
        print(f"  Midpoint (no interaction)      : mix {pp(mid_mix)}  rate {pp(mid_rate)}")

        print("\n== Centered per-category mix: dshare * (oct_rate - Oct overall) ==")
        print("  (raw per-row mix only sums correctly; this version reads per row)")
        for c, m in run(conn, ctes + """
            SELECT top_category,
                   (nov_share - oct_share)
                     * (oct_rate - SUM(oct_share * oct_rate) OVER ()) AS centered_mix
            FROM side_by_side
            ORDER BY ABS(centered_mix) DESC
            LIMIT 6"""):
            print(f"  {c:16} {pp(m)}")

        print("\n== Spike carved out ==")
        print(f"  Nov 15-17 pairs : {spike_n:>9,} carts at {spike_r*100:.2f}%")
        print(f"  rest of Nov     : {rest_n:>9,} carts at {rest_r*100:.2f}%")
        print(f"  Oct             : {oct_n:>9,} carts at {oct_r*100:.2f}%")
        print(f"  spike explains {(rest_r - nov_r)*100:.2f} of {-delta*100:.2f} pts")

        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
