"""Phases 3-5 end to end: run every analysis query, assert, save results.

Usage:
    .venv/bin/python src/run_all.py                # rebuild cohorts + run all
    .venv/bin/python src/run_all.py --skip-build   # reuse USER_COHORTS
    .venv/bin/python src/run_all.py --only 4       # one phase (3, 4 or 5)

Prerequisites: load.py, verify.py and sessionize.py have run (EFA.RAW.EVENTS
and EFA.ANALYTICS.EVENTS_SESSIONIZED exist).

Two kinds of checks, deliberately separated:

  STRUCTURAL -- identities that must hold whatever the data says (week 0 is
  100% retained, the decomposition sums to the headline change, by-month user
  totals overcount by exactly the users active in both months). These are the
  real gate, in the spirit of decision 0.5: expectations derived from the
  data, not typed in.

  PUBLISHED -- the handful of numbers quoted in README.md and MEMO.md. These
  ARE hardcoded, on purpose: if a query changes and one of these moves, the
  write-up is now wrong and this is how you find out.

Every result is written to reports/data/<name>.csv, which src/plots.py reads.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime
from decimal import Decimal

from config import REPO_ROOT, connect, fetch, named_queries, run
from mix_shift import decompose

SQL_DIR = REPO_ROOT / "sql"
OUT_DIR = REPO_ROOT / "reports" / "data"
DATA_END = date(2019, 12, 1)  # exclusive

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str) -> None:
    global checks
    checks += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    if not ok:
        failures.append(f"{label} -- {detail}")


def published(label: str, actual: float, quoted: float, places: int = 2) -> None:
    """A number quoted in the write-up, compared at the precision it is quoted."""
    check(f"published: {label}", round(actual, places) == quoted, f"{actual:.{places}f} (quoted {quoted})")


def as_cell(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def save(name: str, cols: list[str], rows: list[tuple]) -> list[dict]:
    """Write a result to reports/data/<name>.csv and return it as dicts."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = [dict(zip(cols, (as_cell(v) for v in r))) for r in rows]
    with open(OUT_DIR / f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(records)
    return records


def run_block(conn, file: str, name: str) -> list[dict]:
    t0 = time.time()
    cols, rows = fetch(conn, named_queries(SQL_DIR / file)[name])
    print(f"  ran {name} ({len(rows)} rows, {time.time() - t0:.0f}s)")
    return save(name, cols, rows)


def build_cohorts(conn) -> None:
    text = (SQL_DIR / "40_cohorts.sql").read_text()
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    for stmt in [s.strip() for s in code.split(";") if s.strip()]:
        t0 = time.time()
        run(conn, stmt)
        print(f"  rebuilt USER_COHORTS ({time.time() - t0:.0f}s)")


def phase3(conn) -> None:
    print("\n== Phase 3: funnel ==")
    s = run_block(conn, "30_funnel.sql", "session_funnel")[0]
    u = run_block(conn, "30_funnel.sql", "user_funnel")[0]
    by_month = run_block(conn, "30_funnel.sql", "user_funnel_by_month")
    cats = run_block(conn, "30_funnel.sql", "category_funnel")

    check("session funnel narrows", s["reached_purchase"] <= s["reached_cart"] <= s["sessions_with_view"],
          f"{s['sessions_with_view']:,} -> {s['reached_cart']:,} -> {s['reached_purchase']:,}")

    base = run(conn, """SELECT COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_30)
                        FROM EFA.ANALYTICS.EVENTS_SESSIONIZED WHERE EVENT_TYPE = 'view'""")[0][0]
    check("session base = distinct sessions with a view (independent query)",
          s["sessions_with_view"] == base, f"{s['sessions_with_view']:,} vs {base:,}")

    users = run(conn, "SELECT COUNT(DISTINCT USER_ID) FROM EFA.RAW.EVENTS")[0][0]
    check("user funnel covers every user", u["total_users"] == users, f"{u['total_users']:,} vs {users:,}")

    both = run(conn, """SELECT COUNT(*) FROM (
                          SELECT USER_ID FROM EFA.RAW.EVENTS GROUP BY USER_ID
                          HAVING COUNT(DISTINCT DATE_TRUNC('month', EVENT_TIME)) = 2)""")[0][0]
    overcount = sum(m["total_users"] for m in by_month) - u["total_users"]
    check("by-month overcount = users active in both months", overcount == both,
          f"{overcount:,} vs {both:,}")

    cat_sum = sum(c["sessions_with_views"] for c in cats)
    check("category grain counts multi-category sessions more than once",
          cat_sum > s["sessions_with_view"], f"{cat_sum:,} > {s['sessions_with_view']:,}")

    published("session purchase rate %", 100 * s["reached_purchase"] / s["sessions_with_view"], 6.86)
    published("user purchase rate %", 100 * u["reached_purchase"] / u["total_users"], 13.12)
    phone = next(c for c in cats if c["category_code"] == "electronics.smartphone")
    published("smartphone lost view->purchase", phone["lost_view_to_purchase"], 5_740_299, 0)


def phase4(conn) -> None:
    print("\n== Phase 4: cohorts and retention ==")
    status = dict(run(conn, """SELECT COHORT_STATUS, COUNT(*)
                               FROM EFA.ANALYTICS.USER_COHORTS GROUP BY 1"""))
    users = run(conn, "SELECT COUNT(DISTINCT USER_ID) FROM EFA.RAW.EVENTS")[0][0]
    check("every user has exactly one cohort status", sum(status.values()) == users,
          f"{sum(status.values()):,} vs {users:,} distinct users")
    sizes = {as_cell(w): n for w, n in run(conn, """SELECT COHORT_WEEK, COUNT(*)
        FROM EFA.ANALYTICS.USER_COHORTS WHERE COHORT_STATUS = 'included' GROUP BY 1""")}
    check("6 cohorts", len(sizes) == 6, f"{len(sizes)}")

    ret = run_block(conn, "41_retention.sql", "retention_matrix")
    buy = run_block(conn, "41_retention.sql", "retention_matrix_purchase")
    rep = run_block(conn, "41_retention.sql", "repeat_purchase_rate")
    eq = run_block(conn, "41_retention.sql", "repeat_purchase_rate_equal_window")

    check("21 observable cells (6+5+4+3+2+1)", len(ret) == 21, f"{len(ret)}")
    wk0 = [r for r in ret if r["week_offset"] == 0]
    check("week 0 is 100% for every cohort", len(wk0) == 6 and all(r["retention_rate"] == 1 for r in wk0),
          ", ".join(f"{r['retention_rate']:.4f}" for r in wk0))

    def cell_end(r) -> date:
        return date.fromisoformat(r["cohort_week"]) + (r["week_offset"] + 1) * (date(2000, 1, 8) - date(2000, 1, 1))

    latest = max(cell_end(r) for r in ret + buy)
    check("no cell extends past the data", latest <= DATA_END, f"latest cell ends {latest}")
    check("denominators = USER_COHORTS sizes",
          all(r["cohort_size"] == sizes[r["cohort_week"]] for r in ret + buy), "all cells")

    any_rate = {(r["cohort_week"], r["week_offset"]): r["retention_rate"] for r in ret}
    check("purchase week 0 below 100%", all(r["retention_rate"] < 1 for r in buy if r["week_offset"] == 0),
          ", ".join(f"{r['retention_rate']:.4f}" for r in buy if r["week_offset"] == 0))
    check("purchase retention <= any-event retention, every cell",
          all(r["retention_rate"] <= any_rate[(r["cohort_week"], r["week_offset"])] for r in buy),
          f"{len(buy)} cells")

    last = max(r["cohort_week"] for r in rep)
    full_last = next(r["repeat_rate"] for r in rep if r["cohort_week"] == last)
    eq_last = next(r["repeat_rate"] for r in eq if r["cohort_week"] == last)
    check("last cohort: equal-window repeat = full-window repeat (it IS 12 days)",
          full_last == eq_last, f"{full_last:.4f} vs {eq_last:.4f}")

    published("included users", status["included"], 3_321_898, 0)
    later = [r["retention_rate"] for r in ret if r["week_offset"] > 0]
    published("any-event retention after week 0, min %", 100 * min(later), 13.85)
    published("any-event retention after week 0, max %", 100 * max(later), 24.53)
    eq_rates = [r["repeat_rate"] for r in eq]
    published("equal-window repeat, min %", 100 * min(eq_rates), 17.35)
    published("equal-window repeat, max %", 100 * max(eq_rates), 19.52)
    first = min(r["cohort_week"] for r in rep)
    published("raw repeat, first cohort %", 100 * next(r["repeat_rate"] for r in rep if r["cohort_week"] == first), 33.36)


def phase5(conn) -> None:
    print("\n== Phase 5: mix shift vs rate change ==")
    t0 = time.time()
    d = decompose(conn)
    print(f"  ran mix_shift ({len(d['rows'])} rows, {time.time() - t0:.0f}s)")
    save("mix_shift", d["cols"], d["rows"])
    summary = {k: v for k, v in d.items() if isinstance(v, (int, float))}
    summary.update(d["sensitivity"])
    save("mix_shift_summary", ["metric", "value"], list(summary.items()))

    check("mix + rate + interaction = Nov - Oct", abs(d["total"] - d["delta"]) < 1e-6,
          f"{d['total']*100:.4f} vs {d['delta']*100:.4f} pts")
    s = d["sensitivity"]
    for m, r in [("mix@oct_rates", "rate@nov_shares"), ("mix@nov_rates", "rate@oct_shares"),
                 ("mix_midpoint", "rate_midpoint")]:
        check(f"two-term split {m} + {r} = Nov - Oct", abs(s[m] + s[r] - d["delta"]) < 1e-6,
              f"{(s[m] + s[r])*100:.4f} pts")
    check("centered mix sums to total mix", abs(sum(m for _, m in d["centered_mix"]) - d["mix"]) < 1e-6,
          f"{sum(m for _, m in d['centered_mix'])*100:.4f} pts")

    published("Oct cart->purchase %", 100 * d["oct_rate"], 52.95)
    published("Nov cart->purchase %", 100 * d["nov_rate"], 38.87)
    published("total change pts", 100 * d["delta"], -14.08)
    published("mix pts", 100 * d["mix"], -2.99)
    published("rate pts", 100 * d["rate"], -11.94)
    published("interaction pts", 100 * d["interaction"], 0.86)
    published("Nov 15-17 cart->purchase %", 100 * d["spike_rate"], 27.33)
    published("rest of Nov cart->purchase %", 100 * d["rest_nov_rate"], 46.80)
    published("spike explains pts", 100 * d["spike_explains"], 7.93)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true", help="reuse USER_COHORTS as-is")
    ap.add_argument("--only", choices=["3", "4", "5"], help="run one phase")
    args = ap.parse_args()

    t0 = time.time()
    with connect() as conn:
        if not args.skip_build and args.only in (None, "4"):
            print("== Building cohorts ==")
            build_cohorts(conn)
        for phase, fn in [("3", phase3), ("4", phase4), ("5", phase5)]:
            if args.only in (None, phase):
                fn(conn)

    print(f"\n{checks - len(failures)}/{checks} checks passed in {time.time() - t0:.0f}s")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
