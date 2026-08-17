-- Phase 0 setup: warehouse, cost guardrail, schemas, file format, stage, table.
-- Run once. Idempotent except where marked CREATE OR REPLACE.

-- ---------------------------------------------------------------------------
-- Cost guardrail first. The trial is 30 days / $400 and the thing that kills it
-- is not the load, it is a warehouse left running or repeated full scans.
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE RESOURCE MONITOR IF NOT EXISTS EFA_MONITOR
  WITH CREDIT_QUOTA = 100
       FREQUENCY = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 75  PERCENT DO NOTIFY
           ON 90  PERCENT DO SUSPEND
           ON 100 PERCENT DO SUSPEND_IMMEDIATE;

CREATE WAREHOUSE IF NOT EXISTS EFA_WH
  WAREHOUSE_SIZE      = 'XSMALL'
  AUTO_SUSPEND        = 60      -- seconds
  AUTO_RESUME         = TRUE
  INITIALLY_SUSPENDED = TRUE;

ALTER WAREHOUSE EFA_WH SET RESOURCE_MONITOR = EFA_MONITOR;

CREATE DATABASE IF NOT EXISTS EFA;
CREATE SCHEMA   IF NOT EXISTS EFA.RAW;
CREATE SCHEMA   IF NOT EXISTS EFA.ANALYTICS;

USE DATABASE EFA;
USE SCHEMA   RAW;
USE WAREHOUSE EFA_WH;

-- ---------------------------------------------------------------------------
-- File format.
--
-- Note what is NOT here: a TIMESTAMP_FORMAT. The source column looks like
--   2019-10-01 00:00:00 UTC
-- with a literal " UTC" suffix that is not an offset and not a format element
-- Snowflake parses natively. Rather than lean on a format string I am not
-- certain of, the COPY statement casts event_time explicitly (see 01_copy.sql).
-- A wrong format string here would not error -- it would give a column of NULLs
-- on a load that reports success.
--
-- EMPTY_FIELD_AS_NULL: brand and category_code are frequently blank. Mapping
-- '' -> NULL is a decision, not a default: it makes the Phase 1 null-rate audit
-- meaningful and stops GROUP BY brand producing an empty-string bucket.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FILE FORMAT EFA.RAW.CSV_EVENTS
  TYPE                           = CSV
  FIELD_DELIMITER                = ','
  SKIP_HEADER                    = 1
  FIELD_OPTIONALLY_ENCLOSED_BY   = '"'
  EMPTY_FIELD_AS_NULL            = TRUE
  NULL_IF                        = ('', 'NULL', 'null')
  TRIM_SPACE                     = FALSE
  ENCODING                       = 'UTF8'
  ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE
  COMPRESSION                    = AUTO;

CREATE STAGE IF NOT EXISTS EFA.RAW.EVENTS_STAGE
  FILE_FORMAT = EFA.RAW.CSV_EVENTS;

-- ---------------------------------------------------------------------------
-- Target table.
--
-- CATEGORY_ID is an ~18-digit integer. NUMBER(38,0), never FLOAT -- a float
-- silently drops low-order digits and collapses distinct categories together,
-- which you would not notice until the Phase 3 category breakdown looked
-- suspiciously tidy.
--
-- The NOT NULL constraints are enforced by Snowflake on load. They are the
-- cheapest assertion in the project: a load that produced NULL timestamps
-- cannot commit.
--
-- TIMESTAMP_NTZ, holding UTC wall-clock. The store serves a Russian market, so
-- any later hour-of-day analysis needs an explicit offset. Storing NTZ keeps
-- that conversion visible instead of letting a session timezone apply silently.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE EFA.RAW.EVENTS (
  EVENT_TIME     TIMESTAMP_NTZ  NOT NULL,
  EVENT_TYPE     VARCHAR(16)    NOT NULL,
  PRODUCT_ID     NUMBER(38,0)   NOT NULL,
  CATEGORY_ID    NUMBER(38,0),
  CATEGORY_CODE  VARCHAR(128),
  BRAND          VARCHAR(128),
  PRICE          NUMBER(12,2),
  USER_ID        NUMBER(38,0)   NOT NULL,
  USER_SESSION   VARCHAR(64),
  SOURCE_FILE    VARCHAR(256)   NOT NULL   -- METADATA$FILENAME, for per-file reconciliation
);
