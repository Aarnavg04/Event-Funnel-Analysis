"""Phase 0 verification gate. Exits non-zero on any failure.

This is the deliverable of Phase 0, not the load. A COPY that reports
"110,000,000 rows loaded, 0 errors" while handing you a fully NULL timestamp
column has succeeded by every measure except the one that matters.

Every expectation here is derived from the source files (data/manifest.json,
written by load.py from a local line count) or from the dataset's stated
semantics -- not from a number remembered off a Kaggle page.
"""

from __future__ import annotations

import json
import sys

from config import DATA_DIR, connect, run

TABLE = "EFA.RAW.EVENTS"

# The two months chosen in Phase 0. Half-open interval.
EXPECTED_MIN = "2019-10-01"
EXPECTED_MAX_EXCL = "2019-12-01"

# The dataset's stated event vocabulary. A fourth value (e.g. remove_from_cart)
# means the wrong REES46 file was downloaded -- they ship more than one.
EXPECTED_EVENT_TYPES = {"view", "cart", "purchase"}

# Columns where a NULL is not a data quality finding but a load defect.
NON_NULLABLE = ["EVENT_TIME", "EVENT_TYPE", "PRODUCT_ID", "USER_ID"]

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str) -> None:
    global checks
    checks += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    if not ok:
        failures.append(f"{label} -- {detail}")


def main() -> None:
    manifest_path = DATA_DIR / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"FAIL: {manifest_path} missing. Run src/load.py first.")
    manifest = json.loads(manifest_path.read_text())
    expected_total = manifest["expected_total_rows"]

    with connect() as conn:
        print("Phase 0 verification\n")

        # 1. Total rows against the local census.
        actual = run(conn, f"SELECT COUNT(*) FROM {TABLE}")[0][0]
        check(
            "row count",
            actual == expected_total,
            f"table={actual:,} expected={expected_total:,}",
        )

        # 2. Per-file rows against the local census. Catches a PUT that dropped
        #    one file, which a total-only check could mask.
        per_file = dict(
            run(conn, f"SELECT SOURCE_FILE, COUNT(*) FROM {TABLE} GROUP BY 1")
        )
        for name, meta in manifest["files"].items():
            got = next(
                (v for k, v in per_file.items() if name in k), None
            )
            check(
                f"row count [{name}]",
                got == meta["data_rows"],
                f"table={got if got is not None else 'MISSING':,} expected={meta['data_rows']:,}"
                if got is not None
                else f"table=MISSING expected={meta['data_rows']:,}",
            )

        # 3. event_type domain.
        types = {r[0] for r in run(conn, f"SELECT DISTINCT EVENT_TYPE FROM {TABLE}")}
        check(
            "event_type domain",
            types == EXPECTED_EVENT_TYPES,
            f"{sorted(types)}",
        )

        # 4. Date range. This is the check that catches the " UTC" suffix bug --
        #    a bad cast yields NULLs or an absurd range, both visible here.
        lo, hi = run(conn, f"SELECT MIN(EVENT_TIME), MAX(EVENT_TIME) FROM {TABLE}")[0]
        check(
            "date range",
            lo is not None
            and hi is not None
            and str(lo) >= EXPECTED_MIN
            and str(hi) < EXPECTED_MAX_EXCL,
            f"{lo} .. {hi} (expected within {EXPECTED_MIN} .. {EXPECTED_MAX_EXCL})",
        )

        # 5. Both months actually present. A range check alone passes if one
        #    month loaded and the other silently did not.
        months = {
            str(r[0]) for r in run(conn, f"SELECT DISTINCT DATE_TRUNC('month', EVENT_TIME) FROM {TABLE}")
        }
        check("months present", len(months) == 2, f"{sorted(months)}")

        # 6. NULLs in load-critical columns. Snowflake's NOT NULL constraints
        #    should make this impossible; asserting it anyway costs one scan and
        #    proves the constraints are on the columns I think they are.
        null_sql = ", ".join(f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END)" for c in NON_NULLABLE)
        counts = run(conn, f"SELECT {null_sql} FROM {TABLE}")[0]
        for col, n in zip(NON_NULLABLE, counts):
            check(f"no nulls [{col}]", n == 0, f"{n:,} nulls")

        print(f"\n{checks - len(failures)}/{checks} checks passed")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("Phase 0 verified.")


if __name__ == "__main__":
    main()
