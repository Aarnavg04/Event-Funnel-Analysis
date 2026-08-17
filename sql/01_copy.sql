-- Reference copy of the COPY INTO issued by src/load.py. Kept here so the load
-- logic is readable without reading Python.
--
-- Two things to understand about this statement:
--
-- 1. It is a *transforming* COPY (COPY INTO ... FROM (SELECT ...)). That is why
--    event_time parsing is explicit: REPLACE strips the literal " UTC" suffix,
--    then TO_TIMESTAMP_NTZ casts. Deliberately TO_ and not TRY_TO_ -- TRY_TO_
--    would return NULL on a value it could not parse, and combined with a row
--    count check that passes, that is exactly the silent partial success this
--    phase exists to prevent. TO_ raises, ON_ERROR aborts, we find out.
--
--    Trade-off: VALIDATION_MODE is not supported on transforming COPYs, so the
--    dry run in load.py is a SELECT against the stage instead.
--
-- 2. ON_ERROR = ABORT_STATEMENT. CONTINUE silently drops bad rows; SKIP_FILE
--    discards ~40M rows over one bad line. Neither is acceptable here.
--
-- GOTCHA: Snowflake records which files it has loaded and skips them on re-run
-- for 64 days. TRUNCATE + re-COPY loads NOTHING and reports success. To reload,
-- either pass FORCE = TRUE or CREATE OR REPLACE the table (which resets the
-- load metadata). load.py takes the --force flag for this.

COPY INTO EFA.RAW.EVENTS (
  EVENT_TIME, EVENT_TYPE, PRODUCT_ID, CATEGORY_ID, CATEGORY_CODE,
  BRAND, PRICE, USER_ID, USER_SESSION, SOURCE_FILE
)
FROM (
  SELECT
    TO_TIMESTAMP_NTZ(REPLACE($1, ' UTC', '')),
    $2,
    $3,
    $4,
    $5,
    $6,
    $7,
    $8,
    $9,
    METADATA$FILENAME
  FROM @EFA.RAW.EVENTS_STAGE
)
FILE_FORMAT = (FORMAT_NAME = EFA.RAW.CSV_EVENTS)
ON_ERROR     = ABORT_STATEMENT;
