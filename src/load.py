"""

Usage:
    python src/load.py --setup      # run sql/00_setup.sql first
    python src/load.py
    python src/load.py --force      # reload files Snowflake already recorded

The important idea here is the *local row census*. Before anything touches
Snowflake we count the lines in the source files ourselves and write that count
to data/manifest.json. Every later assertion compares against that number.

An expected row count typed in from a dataset description is faith. An expected
row count derived from the file on disk is verification -- it is what catches a
truncated download or a PUT that died at 80%.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from config import DATA_DIR, REPO_ROOT, SOURCE_FILES, connect, run

MANIFEST = DATA_DIR / "manifest.json"
STAGE = "@EFA.RAW.EVENTS_STAGE"
TABLE = "EFA.RAW.EVENTS"

# 9 GB of CSV across two files. Anything dramatically smaller is a truncated
# download, which otherwise loads cleanly and just gives you fewer rows.
MIN_BYTES_PER_FILE = 1_000_000_000


def census() -> dict:
    """Count data rows in each local file. Header excluded."""
    entry = {}
    for name in SOURCE_FILES:
        path = DATA_DIR / name
        if not path.exists():
            sys.exit(f"FAIL: {path} not found. Download the Kaggle files into {DATA_DIR}.")

        size = path.stat().st_size
        if size < MIN_BYTES_PER_FILE:
            sys.exit(
                f"FAIL: {name} is {size / 1e9:.2f} GB, below the {MIN_BYTES_PER_FILE / 1e9:.1f} GB "
                "floor. Likely a truncated download -- re-fetch before loading."
            )

        print(f"  counting {name} ({size / 1e9:.2f} GB) ...", flush=True)
        t0 = time.time()
        out = subprocess.run(["wc", "-l", str(path)], capture_output=True, text=True, check=True)
        lines = int(out.stdout.split()[0])
        entry[name] = {"bytes": size, "data_rows": lines - 1}  # minus header
        print(f"    {lines - 1:,} data rows  ({time.time() - t0:.0f}s)", flush=True)

    total = sum(v["data_rows"] for v in entry.values())
    manifest = {"files": entry, "expected_total_rows": total}
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"  expected total: {total:,} rows -> {MANIFEST}")
    return manifest


def run_setup(conn) -> None:
    sql = (REPO_ROOT / "sql" / "00_setup.sql").read_text()
    with conn.cursor() as cur:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
    print("  setup complete")


def put_files(conn) -> None:
    for name in SOURCE_FILES:
        path = DATA_DIR / name
        print(f"  PUT {name} ... (compresses and uploads in parallel; expect minutes)", flush=True)
        t0 = time.time()
        rows = run(
            conn,
            # AUTO_COMPRESS gzips on the way up -- ~9 GB of CSV becomes ~1.5 GB
            # on the wire. OVERWRITE so a retried upload replaces a partial one.
            f"PUT file://{path} {STAGE} AUTO_COMPRESS=TRUE PARALLEL=8 OVERWRITE=TRUE",
        )
        # (source, target, source_size, target_size, source_compression,
        #  target_compression, status, message)
        for r in rows:
            print(f"    {r[0]} -> {r[1]}  {r[6]}  ({time.time() - t0:.0f}s)")
            if r[6].upper() not in ("UPLOADED", "SKIPPED"):
                sys.exit(f"FAIL: PUT returned status {r[6]}: {r[7]}")


def dry_run(conn) -> None:
    """Show 5 parsed rows before committing to the full load.

    VALIDATION_MODE does not work on a transforming COPY, so this is the dry
    run: apply the exact same expressions the COPY will apply, to a handful of
    rows, and look at them. If event_time comes back NULL here, stop.
    """
    rows = run(
        conn,
        f"""
        SELECT TO_TIMESTAMP_NTZ(REPLACE($1, ' UTC', '')) AS event_time,
               $2 AS event_type, $3 AS product_id, $4 AS category_id,
               $5 AS category_code, $6 AS brand, $7 AS price,
               $8 AS user_id, $9 AS user_session
        FROM {STAGE} (FILE_FORMAT => 'EFA.RAW.CSV_EVENTS')
        LIMIT 5
        """,
    )
    print("  parsed sample:")
    for r in rows:
        print(f"    {r}")
    if not rows:
        sys.exit("FAIL: stage returned no rows. Did PUT succeed?")
    if rows[0][0] is None:
        sys.exit("FAIL: event_time parsed to NULL. Fix the cast before loading 110M rows.")


def copy_into(conn, force: bool) -> list[tuple]:
    print("  COPY INTO ... (this is the long one)", flush=True)
    t0 = time.time()
    rows = run(
        conn,
        f"""
        COPY INTO {TABLE} (
          EVENT_TIME, EVENT_TYPE, PRODUCT_ID, CATEGORY_ID, CATEGORY_CODE,
          BRAND, PRICE, USER_ID, USER_SESSION, SOURCE_FILE
        )
        FROM (
          SELECT TO_TIMESTAMP_NTZ(REPLACE($1, ' UTC', '')),
                 $2, $3, $4, $5, $6, $7, $8, $9,
                 METADATA$FILENAME
          FROM {STAGE}
        )
        FILE_FORMAT = (FORMAT_NAME = EFA.RAW.CSV_EVENTS)
        ON_ERROR     = ABORT_STATEMENT
        FORCE        = {str(force).upper()}
        """,
    )
    print(f"  COPY finished in {time.time() - t0:.0f}s")
    return rows


def reconcile(conn, manifest: dict, copy_rows: list[tuple]) -> None:
    """Per-file COPY result must agree with the local census."""
    if not copy_rows:
        sys.exit(
            "FAIL: COPY loaded no files. Snowflake skips files it has already "
            "loaded (64-day memory) -- re-run with --force, or recreate the table."
        )

    loaded = {}
    for r in copy_rows:
        # file, status, rows_parsed, rows_loaded, error_limit, errors_seen, ...
        stage_file, status, rows_parsed, rows_loaded, _, errors_seen = r[0], r[1], r[2], r[3], r[4], r[5]
        print(f"    {stage_file}: {status} parsed={rows_parsed:,} loaded={rows_loaded:,} errors={errors_seen}")
        if status.upper() != "LOADED":
            sys.exit(f"FAIL: {stage_file} status={status}")
        if errors_seen:
            sys.exit(f"FAIL: {stage_file} saw {errors_seen} errors")
        base = Path(stage_file).name.replace(".gz", "")
        loaded[base] = rows_loaded

    for name, meta in manifest["files"].items():
        got = loaded.get(name)
        if got is None:
            sys.exit(f"FAIL: {name} was not loaded by this COPY.")
        if got != meta["data_rows"]:
            sys.exit(
                f"FAIL: {name} loaded {got:,} rows, local file has {meta['data_rows']:,}. "
                "Partial upload or a header/line-ending discrepancy."
            )
    print("  per-file counts reconcile with local census")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true", help="run sql/00_setup.sql first")
    ap.add_argument("--force", action="store_true", help="reload files Snowflake already recorded")
    args = ap.parse_args()

    print("1. local row census")
    manifest = census()

    with connect() as conn:
        if args.setup:
            print("2. setup")
            run_setup(conn)
        print("3. PUT to stage")
        put_files(conn)
        print("4. dry run")
        dry_run(conn)
        print("5. COPY INTO")
        copy_rows = copy_into(conn, args.force)
        print("6. reconcile")
        reconcile(conn, manifest, copy_rows)

    print("\nLoad complete. Now run: python src/verify.py")


if __name__ == "__main__":
    main()
