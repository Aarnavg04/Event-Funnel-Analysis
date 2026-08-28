"""Phase 2: materialize sessions from the hand-written query, then validate.

Usage:
    .venv/bin/python src/sessionize.py --dry     # 20 rows, no table written
    .venv/bin/python src/sessionize.py          # build + validate
    .venv/bin/python src/sessionize.py --validate-only

The window function lives in sql/20_sessionize.sql and is written by hand.
This module does the parts the working protocol assigns to me: DDL, the
comparison harness against the shipped USER_SESSION column, and the checks.

Materialized rather than recomputed (decision c). The expensive step is sorting
110M rows by (USER_ID, EVENT_TIME); Phases 3-5 all need sessions, so we pay
that once and every later query reads a plain table.
"""

from __future__ import annotations

import argparse
import sys
import time

from config import REPO_ROOT, connect, run

TABLE = "EFA.ANALYTICS.EVENTS_SESSIONIZED"
EXPECTED_ROWS = 109_950_743
SHIPPED_SESSIONS = 23_016_650  # Phase 1, for the comparison


def user_query() -> str:
    text = (REPO_ROOT / "sql" / "20_sessionize.sql").read_text()
    marker = "-- your query below"
    if marker not in text:
        sys.exit("FAIL: marker '-- your query below' missing from sql/20_sessionize.sql")
    q = text.split(marker, 1)[1].strip().rstrip(";").strip()
    if not q or "..." in q:
        sys.exit(
            "FAIL: sql/20_sessionize.sql still has '...' placeholders in it.\n"
            "      Fill in the query before running this."
        )
    return q


def dry_run(conn, q: str) -> None:
    """Eyeball 20 rows for one busy user before writing 110M."""
    rows = run(conn, f"SELECT * FROM ({q}) ORDER BY USER_ID, EVENT_TIME LIMIT 20")
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM ({q}) LIMIT 0")
        cols = [d[0].lower() for d in cur.description]
    print("  columns:", ", ".join(cols))
    for r in rows:
        print("   ", r)


def build(conn, q: str) -> None:
    print(f"  CREATE OR REPLACE TABLE {TABLE} ...", flush=True)
    print("  (sorting 110M rows by user+time on an X-Small; expect minutes and spill)")
    t0 = time.time()
    run(conn, f"CREATE OR REPLACE TABLE {TABLE} AS {q}")
    print(f"  built in {time.time() - t0:.0f}s")


def validate(conn) -> list[str]:
    fails: list[str] = []

    def check(label: str, ok: bool, detail: str) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
        if not ok:
            fails.append(f"{label} -- {detail}")

    n = run(conn, f"SELECT COUNT(*) FROM {TABLE}")[0][0]
    check("row count preserved", n == EXPECTED_ROWS, f"{n:,} (expected {EXPECTED_ROWS:,})")

    nulls = run(
        conn,
        f"""SELECT COUNT_IF(SESSION_NUM_10 IS NULL), COUNT_IF(SESSION_NUM_30 IS NULL),
                   COUNT_IF(SESSION_NUM_60 IS NULL) FROM {TABLE}""",
    )[0]
    check("no null session numbers", all(v == 0 for v in nulls), f"10/30/60 -> {nulls}")

    # A shorter inactivity threshold can only ever cut MORE sessions. If this
    # inverts, the flags or the window frame are wrong.
    c = run(
        conn,
        f"""SELECT COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_10),
                   COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_30),
                   COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_60) FROM {TABLE}""",
    )[0]
    check(
        "sessions_10 >= sessions_30 >= sessions_60",
        c[0] >= c[1] >= c[2],
        f"{c[0]:,} / {c[1]:,} / {c[2]:,}",
    )

    # The definitional check: inside one 30-minute session, no consecutive gap
    # may exceed 1800s. This is what proves the window function did its job.
    bad = run(
        conn,
        f"""
        WITH g AS (
          SELECT DATEDIFF(second,
                   LAG(EVENT_TIME) OVER (PARTITION BY USER_ID, SESSION_NUM_30
                                         ORDER BY EVENT_TIME),
                   EVENT_TIME) AS gap
          FROM {TABLE}
        )
        SELECT COUNT_IF(gap > 1800), MAX(gap) FROM g
        """,
    )[0]
    check("no >30min gap inside a session_30", bad[0] == 0, f"{bad[0]:,} violations, max gap {bad[1]:,}s")

    return fails


def compare(conn) -> None:
    """Ours vs the shipped USER_SESSION column."""
    print("\n  --- ours vs shipped user_session ---")
    r = run(
        conn,
        f"""
        SELECT
          COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_30)          AS ours_30,
          COUNT(DISTINCT USER_SESSION)                              AS shipped,
          COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_10)          AS ours_10,
          COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_60)          AS ours_60
        FROM {TABLE}
        """,
    )[0]
    print(f"    ours @10min  {r[2]:>12,}")
    print(f"    ours @30min  {r[0]:>12,}")
    print(f"    ours @60min  {r[3]:>12,}")
    print(f"    shipped      {r[1]:>12,}   (Phase 1 measured {SHIPPED_SESSIONS:,})")
    d = r[0] - r[1]
    print(f"    ours@30 - shipped = {d:+,} ({100*d/r[1]:+.2f}%)")

    # Split vs merge, both directions. Phase 1 predicted only splitting; a
    # 30-minute rule can also MERGE two shipped sessions that are close together.
    print("\n  --- how they disagree ---")
    r = run(
        conn,
        f"""
        WITH per_shipped AS (
          SELECT USER_SESSION, COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_30) AS ours
          FROM {TABLE} WHERE USER_SESSION IS NOT NULL GROUP BY 1
        ),
        per_ours AS (
          SELECT USER_ID || '-' || SESSION_NUM_30 AS sid,
                 COUNT(DISTINCT USER_SESSION) AS shipped
          FROM {TABLE} WHERE USER_SESSION IS NOT NULL GROUP BY 1
        )
        SELECT
          (SELECT COUNT(*)          FROM per_shipped),
          (SELECT COUNT_IF(ours>1)  FROM per_shipped),
          (SELECT MAX(ours)         FROM per_shipped),
          (SELECT COUNT(*)          FROM per_ours),
          (SELECT COUNT_IF(shipped>1) FROM per_ours),
          (SELECT MAX(shipped)      FROM per_ours)
        """,
    )[0]
    print(f"    shipped sessions we SPLIT : {r[1]:>10,} of {r[0]:,} ({100*r[1]/r[0]:.2f}%)  max pieces {r[2]}")
    print(f"    our sessions that MERGE   : {r[4]:>10,} of {r[3]:,} ({100*r[4]/r[3]:.2f}%)  max merged {r[5]}")

    # Phase 1 proved a shipped session <=30min cannot be split by a 30-min rule.
    # This is that proof, checked against reality.
    r = run(
        conn,
        f"""
        WITH s AS (
          SELECT USER_SESSION,
                 DATEDIFF(second, MIN(EVENT_TIME), MAX(EVENT_TIME)) AS dur,
                 COUNT(DISTINCT USER_ID || '-' || SESSION_NUM_30)   AS ours
          FROM {TABLE} WHERE USER_SESSION IS NOT NULL GROUP BY 1
        )
        SELECT COUNT_IF(dur <= 1800), COUNT_IF(dur <= 1800 AND ours > 1) FROM s
        """,
    )[0]
    ok = r[1] == 0
    print(f"    [{'PASS' if ok else 'FAIL'}] shipped sessions <=30min never split: "
          f"{r[1]:,} violations out of {r[0]:,}")

    # Decision (a): what the threshold actually costs you.
    print("\n  --- session-level conversion by threshold (decision a) ---")
    for t in (10, 30, 60):
        r = run(
            conn,
            f"""
            WITH s AS (
              SELECT USER_ID || '-' || SESSION_NUM_{t} AS sid,
                     COUNT_IF(EVENT_TYPE='view')     AS v,
                     COUNT_IF(EVENT_TYPE='cart')     AS c,
                     COUNT_IF(EVENT_TYPE='purchase') AS p
              FROM {TABLE} GROUP BY 1
            )
            SELECT COUNT_IF(v>0), COUNT_IF(v>0 AND c>0), COUNT_IF(v>0 AND p>0) FROM s
            """,
        )[0]
        print(f"    @{t:>2}min  sessions w/ view {r[0]:>12,}   ->cart {100*r[1]/r[0]:5.2f}%   ->purchase {100*r[2]/r[0]:5.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="20 rows, write nothing")
    ap.add_argument("--validate-only", action="store_true", help="skip the rebuild")
    args = ap.parse_args()

    with connect() as conn:
        if args.dry:
            dry_run(conn, user_query())
            return
        if not args.validate_only:
            build(conn, user_query())
        print("\nvalidation")
        fails = validate(conn)
        compare(conn)

    if fails:
        print("\nFAILED:")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print("\nPhase 2 sessionization validated.")


if __name__ == "__main__":
    main()
