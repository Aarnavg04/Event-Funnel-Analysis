"""Snowflake connection config. Reads .env; never hardcode credentials."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data")).expanduser()

# The two months chosen in Phase 0. Oct+Nov 2019 puts Black Friday inside the
# window, which is the metric movement Phase 5 decomposes.
SOURCE_FILES = ["2019-Oct.csv", "2019-Nov.csv"]

# Cohort lookback: users first seen in this window are treated as pre-existing,
# not as new acquisitions. The dataset starts 2019-10-01, so there is no earlier
# history to draw on -- the window has to be carved out of October itself.
LOOKBACK_START = "2019-10-01"
LOOKBACK_END = "2019-10-15"  # exclusive; cohorts form from this date onward


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"FAIL: {name} is not set. Copy .env.example to .env and fill it in.")
    return value


def _private_key_bytes() -> bytes | None:
    """Load an RSA private key for key-pair auth, if one is configured."""
    path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not path:
        return None
    key_file = Path(path).expanduser()
    if not key_file.exists():
        return None

    from cryptography.hazmat.primitives import serialization

    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    key = serialization.load_pem_private_key(
        key_file.read_bytes(),
        password=passphrase.encode() if passphrase else None,
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connection_kwargs() -> dict:
    kwargs = {
        "account": _require("SNOWFLAKE_ACCOUNT"),
        "user": _require("SNOWFLAKE_USER"),
        "role": os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "EFA_WH"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "EFA"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
        # Fail fast rather than hanging on a bad account identifier.
        "login_timeout": 30,
    }

    key = _private_key_bytes()
    if key is not None:
        kwargs["private_key"] = key
    elif os.getenv("SNOWFLAKE_PASSWORD"):
        # Fallback only. Snowflake blocks single-factor password sign-in for
        # programmatic access on newer accounts; if this errors with something
        # about MFA or blocked authentication, switch to key-pair.
        kwargs["password"] = os.getenv("SNOWFLAKE_PASSWORD")
    else:
        sys.exit(
            "FAIL: no credential found. Set SNOWFLAKE_PRIVATE_KEY_PATH "
            "(preferred) or SNOWFLAKE_PASSWORD in .env."
        )
    return kwargs


@contextmanager
def connect():
    conn = snowflake.connector.connect(**connection_kwargs())
    try:
        yield conn
    finally:
        conn.close()


def run(conn, sql: str, params: tuple | None = None) -> list[tuple]:
    """Execute one statement and return all rows."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
