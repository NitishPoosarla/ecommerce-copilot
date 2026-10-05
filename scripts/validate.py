"""
STEP 5 — Sanity checks: 5 queries that must pass before we trust the warehouse.
Run:  ./venv/Scripts/python.exe scripts/validate.py
Exit code 0 = all checks pass (safe for CI); 1 = something is wrong.
"""
import sys

import sqlalchemy as sa
from dotenv import load_dotenv
import os

CHECKS = [
    # 1. Row counts: fact must equal raw item count, dims must be non-empty.
    #    WHY: catches failed/partial loads immediately.
    ("1. row counts match source (fact=112,650; dims > 0)", """
        SELECT (SELECT COUNT(*) FROM fact_orders)     AS fact,
               (SELECT COUNT(*) FROM dim_customers)   AS cust,
               (SELECT COUNT(*) FROM dim_products)    AS prod,
               (SELECT COUNT(*) FROM dim_sellers)     AS sell,
               (SELECT COUNT(*) FROM dim_reviews)     AS rev,
               (SELECT COUNT(*) FROM dim_payments)    AS pay,
               (SELECT COUNT(*) FROM dim_date)        AS dt
    """, lambda r: r.fact == 112650 and r.cust == 99441 and r.prod == 32951
        and r.sell == 3095 and r.rev == 98410 and r.pay == 103886
        and r.dt == 1827),

    # 2. Date range: data must sit inside 2016-2018 (the brief's window).
    #    WHY: catches timezone mistakes and out-of-scope junk.
    ("2. order dates all within 2016-01-01 .. 2018-12-31", """
        SELECT MIN(purchase_ts)::date AS min_d, MAX(purchase_ts)::date AS max_d,
               COUNT(*) FILTER (WHERE purchase_ts < '2016-01-01'
                                   OR purchase_ts >= '2019-01-01') AS out_of_range
        FROM fact_orders
    """, lambda r: r.out_of_range == 0 and str(r.min_d) >= "2016-01-01"
        and str(r.max_d) <= "2018-12-31"),

    # 3. Null checks: keys/measures must be present; delivery may be NULL
    #    only for orders that never arrived (undelivered).
    #    WHY: a NULL purchase_ts or price would silently break every KPI.
    ("3. no nulls in key fact columns (purchase_ts, price, customer_id)", """
        SELECT COUNT(*) FILTER (WHERE purchase_ts IS NULL)    AS null_ts,
               COUNT(*) FILTER (WHERE price IS NULL)          AS null_price,
               COUNT(*) FILTER (WHERE customer_id IS NULL)    AS null_cust,
               COUNT(*) FILTER (WHERE customer_delivery_ts IS NOT NULL
                                  AND delivery_days IS NULL)  AS delivered_wo_days
        FROM fact_orders
    """, lambda r: r.null_ts == 0 and r.null_price == 0
        and r.null_cust == 0 and r.delivered_wo_days == 0),

    # 4. Duplicate keys: PKs must be unique (they'd have failed at insert,
    #    but re-checking after load also catches data bugs in later reruns).
    ("4. no duplicate primary keys in any table", """
        SELECT (SELECT COUNT(*) FROM (SELECT order_id, order_item_id
                 FROM fact_orders GROUP BY 1,2 HAVING COUNT(*)>1) x) AS dup_fact,
               (SELECT COUNT(*) FROM (SELECT customer_id FROM dim_customers
                 GROUP BY 1 HAVING COUNT(*)>1) x) AS dup_cust,
               (SELECT COUNT(*) FROM (SELECT product_id FROM dim_products
                 GROUP BY 1 HAVING COUNT(*)>1) x) AS dup_prod,
               (SELECT COUNT(*) FROM (SELECT review_id FROM dim_reviews
                 GROUP BY 1 HAVING COUNT(*)>1) x) AS dup_rev,
               (SELECT COUNT(*) FROM (SELECT date_key FROM dim_date
                 GROUP BY 1 HAVING COUNT(*)>1) x) AS dup_dt
    """, lambda r: r.dup_fact == 0 and r.dup_cust == 0 and r.dup_prod == 0
        and r.dup_rev == 0 and r.dup_dt == 0),

    # 5. Referential integrity: every fact FK must resolve to a dimension
    #    row (no orphan facts). Plus delivery math: NEGATIVE days are
    #    impossible (a package can't arrive before it was bought) -> must be 0.
    #    Days > 90 are REPORTED but not failed: Olist really does contain
    #    91-210 day deliveries (77 orders) — that's the lateness problem the
    #    business brief exists to study, not a data error.
    ("5. no orphan FKs; no negative delivery_days", """
        SELECT (SELECT COUNT(*) FROM fact_orders f
                 LEFT JOIN dim_customers c ON c.customer_id = f.customer_id
                 WHERE c.customer_id IS NULL)          AS orphan_cust,
               (SELECT COUNT(*) FROM fact_orders f
                 LEFT JOIN dim_products p ON p.product_id = f.product_id
                 WHERE p.product_id IS NULL)           AS orphan_prod,
               (SELECT COUNT(*) FROM fact_orders f
                 LEFT JOIN dim_sellers s ON s.seller_id = f.seller_id
                 WHERE s.seller_id IS NULL)            AS orphan_sell,
               (SELECT COUNT(*) FROM fact_orders
                 WHERE delivery_days < 0)              AS negative_days,
               (SELECT COUNT(*) FROM fact_orders
                 WHERE delivery_days > 90)             AS slow_over_90d_info
    """, lambda r: r.orphan_cust == 0 and r.orphan_prod == 0
        and r.orphan_sell == 0 and r.negative_days == 0),
]


def main():
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    else:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    eng = sa.create_engine(url)

    all_ok = True
    with eng.connect() as conn:
        for title, sql, predicate in CHECKS:
            row = conn.exec_driver_sql(sql).mappings().first()
            ok = predicate(row)   # RowMapping supports both r.attr and r["attr"]
            all_ok &= bool(ok)
            print(f"[{'PASS' if ok else 'FAIL'}] {title}")
            print(f"        {dict(row)}")
    print("\nRESULT:", "ALL 5 CHECKS PASSED" if all_ok else "CHECKS FAILED")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
