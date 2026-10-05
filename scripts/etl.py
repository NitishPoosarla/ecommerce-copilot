"""
STEP 4 — ETL: extract raw CSVs -> clean -> load star schema into cloud Postgres.

Run:  ./venv/Scripts/python.exe scripts/etl.py

What it does, in order:
  1. Reads DATABASE_URL from .env
  2. Enables the pgvector extension (for the future RAG chatbot)
  3. Drops old warehouse tables (idempotent = safe to rerun)
  4. Creates the star schema (1 fact + 6 dimensions)
  5. Cleans the raw CSVs (nulls, dates, dtypes, duplicate reviews)
  6. Loads every table and prints row counts

Design: fact_orders has ONE ROW PER ORDER ITEM (grain), not per order.
Order-level measures (delivery days, on-time flag) repeat across an order's
items, so order-level KPI queries must COUNT(DISTINCT order_id) — each query
in sql/ does this and comments why.
"""
import os
import sys

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

RAW = "Data/Raw"
ENGINE = None


# --------------------------------------------------------------------------
# 1. CONNECTION
# --------------------------------------------------------------------------
def get_engine():
    """Read DATABASE_URL from .env and build a SQLAlchemy engine."""
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: DATABASE_URL not found in .env")
    # SQLAlchemy 2.x defaults to the psycopg (v3) driver for postgresql://
    # URLs, but we installed psycopg2-binary — force the v2 driver explicitly.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    else:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    # Timescale cloud requires SSL; re-attach if the pasted URL lost it.
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return sa.create_engine(url)


# --------------------------------------------------------------------------
# 2. DDL — the star schema
# --------------------------------------------------------------------------
DDL = """
-- pgvector: needed later for RAG chatbot embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Wipe previous run (CASCADE clears FKs from fact -> dims first)
DROP TABLE IF EXISTS fact_orders      CASCADE;
DROP TABLE IF EXISTS dim_customers    CASCADE;
DROP TABLE IF EXISTS dim_products     CASCADE;
DROP TABLE IF EXISTS dim_sellers      CASCADE;
DROP TABLE IF EXISTS dim_reviews      CASCADE;
DROP TABLE IF EXISTS dim_payments     CASCADE;
DROP TABLE IF EXISTS dim_date         CASCADE;

-- ===== DIMENSIONS (descriptive lookup tables) =====

-- Who bought. customer_id changes per order in Olist; customer_unique_id is
-- the stable person-level ID used for repeat-purchase analysis.
CREATE TABLE dim_customers (
    customer_id          TEXT PRIMARY KEY,   -- order-scoped ID
    customer_unique_id   TEXT NOT NULL,      -- person-level ID (repeat buys)
    customer_zip_code    INTEGER,
    customer_city        TEXT,
    customer_state       TEXT
);

-- What was sold. Category is translated PT -> EN for reporting.
-- embedding column is empty for now: the RAG phase fills it with pgvector.
CREATE TABLE dim_products (
    product_id           TEXT PRIMARY KEY,
    product_category_pt  TEXT,
    product_category_en  TEXT,
    name_length          INTEGER,
    description_length   INTEGER,
    photos_qty           INTEGER,
    product_weight_g     REAL,
    length_cm            REAL,
    height_cm            REAL,
    width_cm             REAL,
    embedding            VECTOR(384)        -- reserved for RAG embeddings
);

CREATE TABLE dim_sellers (
    seller_id            TEXT PRIMARY KEY,
    seller_zip_code      INTEGER,
    seller_city          TEXT,
    seller_state         TEXT
);

-- One row per review. Duplicated review_ids removed during cleaning.
-- NOTE: 551 orders have 2 reviews — join to fact by order_id carefully
-- (the fact table pre-merges the FIRST review's score to avoid row inflation).
CREATE TABLE dim_reviews (
    review_id            TEXT PRIMARY KEY,
    order_id             TEXT,
    review_score         INTEGER,           -- 1..5 stars
    review_comment_title TEXT,
    review_comment       TEXT,
    review_creation_date DATE,
    review_answer_ts     TIMESTAMP
);

-- One row per payment attempt (an order can have several: e.g. voucher + card).
-- PK is composite because payment_sequential only repeats within an order.
CREATE TABLE dim_payments (
    order_id             TEXT NOT NULL,
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT,
    payment_installments INTEGER,
    payment_value        REAL,              -- BRL
    PRIMARY KEY (order_id, payment_sequential)
);

-- Generated calendar 2016-2020 so "revenue by month" has no gaps.
CREATE TABLE dim_date (
    date_key             INTEGER PRIMARY KEY,  -- 20171002 style
    full_date            DATE NOT NULL UNIQUE,
    year                 INTEGER,
    month                INTEGER,
    month_name           TEXT,
    quarter              INTEGER,
    day_of_week          INTEGER,
    day_name             TEXT,
    is_weekend           BOOLEAN,
    year_month           TEXT                 -- '2017-10', for grouping
);

-- ===== FACT (the numbers we measure) =====
-- Grain: one row per ORDER ITEM = (order_id, order_item_id).
-- 112,650 rows; an order with 3 products has 3 rows.
CREATE TABLE fact_orders (
    order_id               TEXT NOT NULL,
    order_item_id          INTEGER NOT NULL,
    customer_id            TEXT REFERENCES dim_customers(customer_id),
    product_id             TEXT REFERENCES dim_products(product_id),
    seller_id              TEXT REFERENCES dim_sellers(seller_id),
    purchase_date_key      INTEGER REFERENCES dim_date(date_key),
    -- degenerate dimension (no separate table needed, just a label):
    order_status           TEXT,
    -- timestamps (the raw facts about the order's journey):
    purchase_ts            TIMESTAMP,
    approved_ts            TIMESTAMP,
    carrier_delivery_ts    TIMESTAMP,       -- handed to carrier
    customer_delivery_ts   TIMESTAMP,       -- arrived at customer
    estimated_delivery_ts  TIMESTAMP,
    -- measures:
    price                  REAL,            -- item value BRL
    freight_value          REAL,            -- shipping BRL
    delivery_days          REAL,            -- purchase -> arrival (nullable)
    is_delivered           BOOLEAN,
    is_on_time             BOOLEAN,         -- arrived on/before estimate
    review_score           INTEGER,         -- first review of the order (1..5)
    PRIMARY KEY (order_id, order_item_id)
);
"""

POST_DDL = """
-- Indexes for the join paths and common filters
CREATE INDEX ON fact_orders (customer_id);
CREATE INDEX ON fact_orders (product_id);
CREATE INDEX ON fact_orders (seller_id);
CREATE INDEX ON fact_orders (purchase_date_key);
CREATE INDEX ON fact_orders (order_status);
CREATE INDEX ON dim_reviews (order_id);
CREATE INDEX ON dim_payments (order_id);
CREATE INDEX ON dim_products (product_category_en);
"""


# --------------------------------------------------------------------------
# 3. LOAD — helpers
# --------------------------------------------------------------------------
def load(df, name, conn):
    import time
    t0 = time.time()
    # MUST use the same open connection/transaction: to_sql on the engine
    # would open a 2nd connection that can't see our uncommitted DDL tables.
    df.to_sql(name, conn, if_exists="append", index=False, chunksize=2000,
              method="multi")
    print(f"  loaded {name:<16} {len(df):>8,} rows "
          f"({time.time() - t0:.1f}s)", flush=True)


def build_dim_date():
    """Generated calendar — CSV data only spans 2016-2018."""
    days = pd.date_range("2016-01-01", "2020-12-31", freq="D")
    return pd.DataFrame({
        "date_key": days.strftime("%Y%m%d").astype(int),
        "full_date": days.date,
        "year": days.year,
        "month": days.month,
        "month_name": days.strftime("%B"),
        "quarter": days.quarter,
        "day_of_week": days.dayofweek + 1,   # 1=Mon .. 7=Sun (ISO-ish)
        "day_name": days.strftime("%A"),
        "is_weekend": days.dayofweek >= 5,
        "year_month": days.strftime("%Y-%m"),
    })


def main():
    global ENGINE
    import time
    sys.stdout.reconfigure(line_buffering=True)  # see progress when redirected
    ENGINE = get_engine()
    t_start = time.time()

    print("STEP 4 — ETL starting")
    with ENGINE.begin() as conn:            # one transaction: all-or-nothing
        conn.exec_driver_sql(
            "SELECT 1"                       # fail fast if unreachable
        )
        print("connected OK")

        # --- schema -------------------------------------------------------
        # Run the whole script in one call: splitting on ';' creates chunks
        # that contain only comments, and Postgres rejects those as empty.
        conn.exec_driver_sql(DDL)
        print("star schema created (pgvector enabled)")

        # --- read raw CSVs ------------------------------------------------
        c = pd.read_csv(f"{RAW}/olist_customers_dataset.csv")
        p = pd.read_csv(f"{RAW}/olist_products_dataset.csv")
        s = pd.read_csv(f"{RAW}/olist_sellers_dataset.csv")
        o = pd.read_csv(f"{RAW}/olist_orders_dataset.csv")
        it = pd.read_csv(f"{RAW}/olist_order_items_dataset.csv")
        rv = pd.read_csv(f"{RAW}/olist_order_reviews_dataset.csv")
        pay = pd.read_csv(f"{RAW}/olist_order_payments_dataset.csv")
        cat = pd.read_csv(f"{RAW}/product_category_name_translation.csv")

        # --- cleaning: dims ----------------------------------------------
        # customers: no nulls, no dups (checked in STEP 2); just types.
        dim_customers = c.rename(columns={
            "customer_zip_code_prefix": "customer_zip_code"})
        dim_customers["customer_state"] = dim_customers["customer_state"].str.strip()

        # products: 610 missing category -> 'unknown'; translate PT->EN;
        # missing weight/dims stay NULL (honest: we don't know them).
        p = p.merge(cat, on="product_category_name", how="left")
        p["product_category_name"] = p["product_category_name"].fillna("unknown")
        p["product_category_name_english"] = (
            p["product_category_name_english"].fillna("unknown"))
        dim_products = p.rename(columns={
            "product_category_name": "product_category_pt",
            "product_category_name_english": "product_category_en",
            "product_name_lenght": "name_length",
            "product_description_lenght": "description_length",
            "product_photos_qty": "photos_qty",
            "product_length_cm": "length_cm",
            "product_height_cm": "height_cm",
            "product_width_cm": "width_cm",
        })

        dim_sellers = s.rename(columns={"seller_zip_code_prefix": "seller_zip_code"})
        dim_sellers["seller_state"] = dim_sellers["seller_state"].str.strip()

        # reviews: 814 duplicated review_ids — keep newest answer per id.
        # review_comment_title/message have legitimate nulls (people often
        # rate without writing) -> keep as NULL, don't invent text.
        rv["review_creation_date"] = pd.to_datetime(rv["review_creation_date"],
                                                     errors="coerce")
        rv["review_answer_timestamp"] = pd.to_datetime(
            rv["review_answer_timestamp"], errors="coerce")
        rv = (rv.sort_values("review_answer_timestamp")
                 .drop_duplicates("review_id", keep="last"))
        dim_reviews = rv.rename(columns={
            "review_comment_title": "review_comment_title",
            "review_comment_message": "review_comment",
            "review_answer_timestamp": "review_answer_ts",
        })[["review_id", "order_id", "review_score", "review_comment_title",
            "review_comment", "review_creation_date", "review_answer_ts"]]

        dim_payments = pay  # no nulls, no dup keys

        # --- cleaning: fact ----------------------------------------------
        DATE_COLS = ["order_purchase_timestamp", "order_approved_at",
                     "order_delivered_carrier_date",
                     "order_delivered_customer_date",
                     "order_estimated_delivery_date"]
        for col in DATE_COLS:
            o[col] = pd.to_datetime(o[col], errors="coerce")
        # 2,965 orders never arrived (cancelled/unshipped) — their delivery
        # date stays NULL and is_delivered=False. Not dropped: cancelled
        # orders are business facts too.

        # item grain + delivery math (order level, computed BEFORE the join)
        o["delivery_days"] = (
            o["order_delivered_customer_date"] - o["order_purchase_timestamp"]
        ).dt.total_seconds() / 86400
        o["is_delivered"] = o["order_delivered_customer_date"].notna()
        o["is_on_time"] = (
            o["order_delivered_customer_date"] <= o["order_estimated_delivery_date"]
        ).astype("boolean")  # nullable bool: NA allowed (pandas 3 forbids NA in plain bool)
        # NULL when never delivered: an undelivered order is neither early nor late.
        o.loc[~o["is_delivered"], "is_on_time"] = pd.NA

        # First review per order, merged in BEFORE the item join so having
        # 2 reviews or 3 items can never multiply rows (the 551-inflation bug).
        first_review = (rv.sort_values("review_creation_date")
                          .drop_duplicates("order_id", keep="first")
                          .set_index("order_id")["review_score"])
        o["review_score"] = o["order_id"].map(first_review)

        o["purchase_date_key"] = o["order_purchase_timestamp"].dt.strftime(
            "%Y%m%d").astype("Int64")

        fact = it.merge(
            o[["order_id", "customer_id", "order_status",
               "order_purchase_timestamp", "order_approved_at",
               "order_delivered_carrier_date", "order_delivered_customer_date",
               "order_estimated_delivery_date",
               "purchase_date_key", "delivery_days", "is_delivered",
               "is_on_time", "review_score"]],
            on="order_id", how="inner")   # inner: items without orders = orphans
        assert len(fact) == len(it), (
            f"JOIN INFLATION: expected {len(it)} item rows, got {len(fact)}")

        fact_orders = fact.rename(columns={
            "order_purchase_timestamp": "purchase_ts",
            "order_approved_at": "approved_ts",
            "order_delivered_carrier_date": "carrier_delivery_ts",
            "order_delivered_customer_date": "customer_delivery_ts",
            "order_estimated_delivery_date": "estimated_delivery_ts",
        })[["order_id", "order_item_id", "customer_id", "product_id",
            "seller_id", "purchase_date_key", "order_status", "purchase_ts",
            "approved_ts", "carrier_delivery_ts", "customer_delivery_ts",
            "estimated_delivery_ts", "price", "freight_value",
            "delivery_days", "is_delivered", "is_on_time", "review_score"]]

        # --- load (dims first: facts reference them) ----------------------
        print("\nloading tables...")
        load(build_dim_date(), "dim_date", conn)
        load(dim_customers, "dim_customers", conn)
        load(dim_products, "dim_products", conn)
        load(dim_sellers, "dim_sellers", conn)
        load(dim_reviews, "dim_reviews", conn)
        load(dim_payments, "dim_payments", conn)
        load(fact_orders, "fact_orders", conn)

        conn.exec_driver_sql(POST_DDL)

    # --- row counts (outside the txn, read-only) --------------------------
    print("\n=== ROW COUNTS ===")
    with ENGINE.connect() as conn:
        tables = [r[0] for r in conn.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "ORDER BY tablename")]
        total = 0
        for t in tables:
            n = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {t}").scalar()
            total += n
            print(f"  {t:<18} {n:>10,}")
        print(f"  {'TOTAL':<18} {total:>10,}")
    print("\nETL complete.", f"total {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
