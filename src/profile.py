"""Phase 1 data profiling. Runs sql/10_profile.sql and writes a report.

Usage:
    .venv/bin/python src/profile.py
    .venv/bin/python src/profile.py --only census,duplicates

Unlike src/verify.py this does NOT gate. It measures. Almost nothing here is a
pass/fail, because the things it measures are properties of the data rather
than defects in the load -- a purchase with no prior cart is a finding, not a
bug. The two exceptions are the cross-checks against Phase 0's known values,
where a mismatch means the profiler is wrong.

Queries live in sql/10_profile.sql, parsed on "-- name:" markers, so there is
one copy of each and it is the readable one.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from config import REPO_ROOT, connect, run

REPORT = REPO_ROOT / "reports" / "phase1_profile.md"

# Measured in Phase 0. If the profiler disagrees, the profiler is wrong.
KNOWN = {
    "total_rows": 109_950_743,
    "null_brand": 15_331_243,
    "null_category_code": 35_413_780,
}


def load_queries() -> dict[str, str]:
    """Parse sql/10_profile.sql into {name: sql}."""
    text = (REPO_ROOT / "sql" / "10_profile.sql").read_text()
    blocks = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    # blocks[0] is the file header before the first marker
    out = {}
    for name, body in zip(blocks[1::2], blocks[2::2]):
        sql = body.strip().rstrip(";").strip()
        if sql:
            out[name] = sql
    return out


def fetch(conn, sql: str) -> tuple[list[str], list[tuple]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return [d[0].lower() for d in cur.description], cur.fetchall()


def fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def pct(n, total) -> str:
    return "—" if not total else f"{100 * n / total:.2f}%"


def md_table(cols: list[str], rows: list[tuple]) -> str:
    head = "| " + " | ".join(cols) + " |"
    rule = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(fmt(v) for v in r) + " |" for r in rows]
    return "\n".join([head, rule, *body])


# Percentiles, means and extrema are not counts -- a "% of denominator" column
# against them is meaningless. Skip them.
_NOT_A_COUNT = ("p01", "p25", "p50", "p75", "p90", "p99", "mean", "_max", "max_", "min")


def kv_table(cols: list[str], row: tuple, denom_label: str, denom: int | None) -> str:
    """Single-row result rendered vertically -- readable for 20-column rows.

    denom is the natural base for THIS section: rows for the census, sessions
    for session integrity, users for user activity, products for attribute
    stability. Using total_rows everywhere silently turns "36% of sessions are
    single-event" into "7.5%", which is true of nothing anyone asked about.
    """
    lines = [f"| metric | value | % of {denom_label} |", "|---|---|---|"]
    for c, v in zip(cols, row):
        skip = any(t in c for t in _NOT_A_COUNT) or c == cols[0]
        share = "" if skip or not denom or not isinstance(v, int) else pct(v, denom)
        lines.append(f"| {c} | {fmt(v)} | {share} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated query names to run")
    args = ap.parse_args()

    queries = load_queries()
    if args.only:
        wanted = [n.strip() for n in args.only.split(",")]
        missing = [n for n in wanted if n not in queries]
        if missing:
            sys.exit(f"FAIL: unknown query name(s): {missing}. Have: {list(queries)}")
        queries = {n: queries[n] for n in wanted}

    results: dict[str, tuple[list[str], list[tuple]]] = {}
    warnings: list[str] = []

    with connect() as conn:
        for name, sql in queries.items():
            print(f"  {name} ...", end="", flush=True)
            t0 = time.time()
            cols, rows = fetch(conn, sql)
            results[name] = (cols, rows)
            print(f" {time.time() - t0:.0f}s")

    # ---- cross-checks against Phase 0 -------------------------------------
    total = None
    if "census" in results:
        cols, rows = results["census"]
        c = dict(zip(cols, rows[0]))
        total = c["total_rows"]
        for key, expected in KNOWN.items():
            if key in c and c[key] != expected:
                warnings.append(
                    f"{key}: profiler says {c[key]:,}, Phase 0 measured {expected:,} "
                    "-- profiler bug, not a finding"
                )
        if c["n_view"] + c["n_cart"] + c["n_purchase"] != total:
            warnings.append("event_type counts do not sum to total_rows")
        if c["distinct_event_types"] != 3:
            warnings.append(f"expected 3 event types, found {c['distinct_event_types']}")

    # ---- report ------------------------------------------------------------
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = [
        "# Phase 1 — Data quality profile",
        "",
        "Generated by `src/profile.py` from `sql/10_profile.sql`.",
        "",
        "This is a **measurement**, not a gate. Numbers here are properties of the",
        "data, not defects in the load. Anything that changes the analysis plan is",
        "copied into `DECISIONS.md` Open questions.",
        "",
        "Everything derived from `user_session` is **provisional** — Phase 2 computes",
        "sessions independently and these get re-measured.",
        "",
    ]

    if warnings:
        out += ["## ⚠ Cross-check failures", ""]
        out += [f"- {w}" for w in warnings] + [""]
    else:
        out += ["Cross-checks against Phase 0 values: **pass**.", ""]

    titles = {
        "census": "Census, null rates and cardinality",
        "price_by_type": "Price distribution by event type",
        "duplicates": "Duplicate events",
        "session_integrity": "Session integrity (provisional)",
        "user_activity": "User activity distribution",
        "attribute_stability": "Product attribute stability",
    }

    # Each single-row section gets its own natural denominator.
    denoms = {
        "census": ("rows", total),
        "session_integrity": ("sessions", None),
        "user_activity": ("users", None),
        "attribute_stability": ("products", None),
    }
    for name in ("session_integrity", "user_activity", "attribute_stability"):
        if name in results:
            label, _ = denoms[name]
            cols, rows = results[name]
            denoms[name] = (label, rows[0][0])  # first column IS the denominator

    for name, (cols, rows) in results.items():
        out += [f"## {titles.get(name, name)}", ""]
        if len(rows) == 1 and len(cols) > 6:
            label, denom = denoms.get(name, ("rows", total))
            out += [kv_table(cols, rows[0], label, denom)]
        else:
            out += [md_table(cols, rows)]
        out += ["", "_Interpretation: `reports/phase1_findings.md`._", ""]

    out += [
        "## Funnel coherence",
        "",
        "_Not yet measured — query written by hand. Phase 1 is not complete until",
        "this lands._",
        "",
    ]

    REPORT.write_text("\n".join(out))
    print(f"\nreport -> {REPORT}")
    if warnings:
        print("\nCROSS-CHECK FAILURES:")
        for w in warnings:
            print(f"  - {w}")
        sys.exit(1)


if __name__ == "__main__":
    main()
