"""
Phase 3, STEP 2 — Exploratory Data Analysis (EDA).

Loads data from the cloud Postgres warehouse (connection in .env) with pandas,
answers the business brief's Section 3 questions, saves every result as a CSV
in analysis/outputs/, and prints a plain-English summary.

Run:  ./venv/Scripts/python.exe analysis/eda.py

GRAIN REMINDER (the rule that keeps numbers honest):
  fact_orders = 1 row per ORDER ITEM.
  - Money (price+freight) can be SUMmed directly at item grain (each BRL
    appears exactly once).
  - Order-level KPIs (on-time %, delivery days, review scores) must first
    collapse to DISTINCT order_id, or multi-item orders get overcounted.
"""
import os

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

OUT = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUT, exist_ok=True)


def get_engine():
    """Read DATABASE_URL from .env and build a SQLAlchemy engine."""
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    # Force the psycopg2 driver (SQLAlchemy 2 defaults to psycopg v3,
    # which isn't installed — same fix as Phase 2's ETL).
    url = url.replace("postgres://", "postgresql+psycopg2://", 1) \
        if url.startswith("postgres://") else \
        url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return sa.create_engine(url)


def q(engine, sql):
    """Run SQL, return a DataFrame."""
    return pd.read_sql(sql, engine)


def save(df, name):
    """Save a DataFrame as CSV and echo it."""
    path = os.path.join(OUT, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"  saved {name}.csv ({len(df)} rows)")
    return df


def main():
    eng = get_engine()
    print("Phase 3 EDA — querying warehouse...\n")

    # ------------------------------------------------------------------
    # 1. Monthly revenue trend (item grain: money sums directly)
    # ------------------------------------------------------------------
    monthly = q(eng, """
        SELECT d.year_month,
               COUNT(DISTINCT f.order_id) AS orders,
               ROUND(SUM(f.price + f.freight_value)::numeric, 2) AS revenue_brl
        FROM fact_orders f
        JOIN dim_date d ON d.date_key = f.purchase_date_key
        GROUP BY d.year_month
        ORDER BY d.year_month
    """)
    save(monthly, "01_monthly_revenue")

    # ------------------------------------------------------------------
    # 2. Top AND bottom 10 categories by revenue
    #    (two queries UNIONed so they land in one CSV with a rank_side)
    # ------------------------------------------------------------------
    cat_rank = q(eng, """
        WITH cat AS (
            SELECT p.product_category_en AS category,
                   ROUND(SUM(f.price + f.freight_value)::numeric, 2) AS revenue_brl,
                   COUNT(DISTINCT f.order_id) AS orders
            FROM fact_orders f
            JOIN dim_products p ON p.product_id = f.product_id
            GROUP BY 1
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (ORDER BY revenue_brl DESC) AS rank_desc
            FROM cat
        )
        SELECT CASE WHEN rank_desc <= 10 THEN 'top10' ELSE 'bottom10' END AS side,
               rank_desc, category, revenue_brl, orders
        FROM ranked
        WHERE rank_desc <= 10
           OR rank_desc > (SELECT COUNT(*) FROM cat) - 10
        ORDER BY rank_desc
    """)
    save(cat_rank, "02_category_rank_top_bottom")

    # ------------------------------------------------------------------
    # 3. On-time delivery % overall AND by customer state
    #    (collapsed to one row per order FIRST — item grain would
    #     overcount multi-item orders)
    # ------------------------------------------------------------------
    ontime_overall = q(eng, """
        SELECT COUNT(*) AS delivered_orders,
               COUNT(*) FILTER (WHERE is_on_time) AS on_time_orders,
               ROUND(100.0 * COUNT(*) FILTER (WHERE is_on_time)
                     / COUNT(*), 2) AS on_time_pct
        FROM (SELECT DISTINCT order_id, is_on_time
              FROM fact_orders WHERE is_delivered) o
    """)
    save(ontime_overall, "03a_ontime_overall")

    ontime_state = q(eng, """
        SELECT c.customer_state,
               COUNT(*) AS delivered_orders,
               ROUND(100.0 * COUNT(*) FILTER (WHERE o.is_on_time)
                     / COUNT(*), 1) AS on_time_pct
        FROM (SELECT DISTINCT order_id, customer_id, is_on_time
              FROM fact_orders WHERE is_delivered) o
        JOIN dim_customers c ON c.customer_id = o.customer_id
        GROUP BY 1
        HAVING COUNT(*) >= 200          -- small states = noisy stats
        ORDER BY on_time_pct ASC
    """)
    save(ontime_state, "03b_ontime_by_state")

    # ------------------------------------------------------------------
    # 4. Average delivery days by state
    # ------------------------------------------------------------------
    days_state = q(eng, """
        WITH per_state AS (
            SELECT c.customer_state,
                   COUNT(*) AS delivered_orders,
                   ROUND(AVG(o.delivery_days)::numeric, 1) AS avg_delivery_days
            FROM (SELECT DISTINCT order_id, customer_id, delivery_days
                  FROM fact_orders WHERE delivery_days IS NOT NULL) o
            JOIN dim_customers c ON c.customer_id = o.customer_id
            GROUP BY 1
            HAVING COUNT(*) >= 200
        ),
        national AS (   -- true national avg, no hardcoded number
            SELECT AVG(delivery_days) AS natl_avg
            FROM (SELECT DISTINCT order_id, delivery_days
                  FROM fact_orders WHERE delivery_days IS NOT NULL) x
        )
        SELECT *,
               ROUND((avg_delivery_days - natl_avg)::numeric, 1)
                   AS days_vs_natl_avg
        FROM per_state, national
        ORDER BY avg_delivery_days DESC
    """)
    save(days_state, "04_delivery_days_by_state")

    # ------------------------------------------------------------------
    # 5a. Review score distribution (order grain)
    # ------------------------------------------------------------------
    reviews_dist = q(eng, """
        SELECT review_score,
               COUNT(*) AS orders,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM (SELECT DISTINCT order_id, review_score
              FROM fact_orders WHERE review_score IS NOT NULL) r
        GROUP BY 1
        ORDER BY 1
    """)
    save(reviews_dist, "05a_review_score_distribution")

    # ------------------------------------------------------------------
    # 5b. THE core hypothesis: avg review of LATE vs ON-TIME orders
    # ------------------------------------------------------------------
    late_vs_ontime = q(eng, """
        SELECT is_on_time,
               COUNT(*) AS orders,
               ROUND(AVG(review_score)::numeric, 2) AS avg_review_score,
               ROUND(100.0 * COUNT(*) FILTER (WHERE review_score = 1)
                     / COUNT(*), 1) AS pct_1star
        FROM (SELECT DISTINCT order_id, is_on_time, review_score
              FROM fact_orders
              WHERE is_on_time IS NOT NULL AND review_score IS NOT NULL) o
        GROUP BY 1
        ORDER BY 1 DESC
    """)
    save(late_vs_ontime, "05b_late_vs_ontime_reviews")

    # ------------------------------------------------------------------
    # 6. Repeat purchase rate (customer_unique_id = the stable PERSON id;
    #    customer_id changes every order in Olist)
    # ------------------------------------------------------------------
    repeat = q(eng, """
        WITH cust AS (
            SELECT c.customer_unique_id,
                   COUNT(DISTINCT f.order_id) AS n_orders
            FROM fact_orders f
            JOIN dim_customers c ON c.customer_id = f.customer_id
            GROUP BY 1
        )
        SELECT COUNT(*) AS total_customers,
               COUNT(*) FILTER (WHERE n_orders >= 2) AS repeat_customers,
               ROUND(100.0 * COUNT(*) FILTER (WHERE n_orders >= 2)
                     / COUNT(*), 2) AS repeat_rate_pct,
               ROUND(AVG(n_orders)::numeric, 3) AS avg_orders_per_customer
        FROM cust
    """)
    save(repeat, "06_repeat_purchase_rate")

    # Extra evidence for recommendations: repeat vs one-time REVENUE share
    # (cited in recommendations.md)
    rev_split = q(eng, """
        WITH order_money AS (
            SELECT order_id, customer_id,
                   SUM(price + freight_value) AS order_revenue
            FROM fact_orders GROUP BY 1, 2
        ),
        cust_n AS (
            SELECT c.customer_unique_id, COUNT(DISTINCT om.order_id) AS n
            FROM order_money om
            JOIN dim_customers c ON c.customer_id = om.customer_id
            GROUP BY 1
        )
        SELECT CASE WHEN cn.n >= 2 THEN 'repeat' ELSE 'one_time' END AS buyer_type,
               COUNT(DISTINCT om.order_id) AS orders,
               ROUND(SUM(om.order_revenue)::numeric, 2) AS revenue_brl,
               ROUND((100.0 * SUM(om.order_revenue)
                      / SUM(SUM(om.order_revenue)) OVER ())::numeric, 1)
                      AS pct_of_revenue
        FROM order_money om
        JOIN dim_customers c ON c.customer_id = om.customer_id
        JOIN cust_n cn ON cn.customer_unique_id = c.customer_unique_id
        GROUP BY 1
    """)
    save(rev_split, "07_revenue_repeat_vs_onetime")

    # ------------------------------------------------------------------
    # PLAIN-ENGLISH SUMMARY
    # ------------------------------------------------------------------
    print("\n=== FINDINGS (plain English) ===")
    peak = monthly.loc[monthly.revenue_brl.idxmax()]
    print(f"\n1. REVENUE: peaks at {peak.revenue_brl:,.0f} BRL in "
          f"{peak.year_month}; strong seasonality (Black-Friday-like Nov spikes).")

    top10 = cat_rank[cat_rank.side == "top10"]
    bot10 = cat_rank[cat_rank.side == "bottom10"]
    print(f"2. CATEGORIES: top10 = {top10.revenue_brl.sum():,.0f} BRL; "
          f"bottom10 combined only {bot10.revenue_brl.sum():,.0f} BRL "
          f"(top: {top10.iloc[0].category}, worst: {bot10.iloc[-1].category}).")

    ot = ontime_overall.iloc[0]
    worst = ontime_state.iloc[0]
    best = ontime_state.iloc[-1]
    print(f"3. ON-TIME: {ot.on_time_pct}% overall ({ot.on_time_orders:,}/"
          f"{ot.delivered_orders:,}). Worst state {worst.customer_state} "
          f"{worst.on_time_pct}% vs best {best.customer_state} {best.on_time_pct}%.")

    slow = days_state.iloc[0]
    natl = slow.avg_delivery_days - slow.days_vs_natl_avg  # true national avg
    print(f"4. SPEED: avg {natl:.1f} days nationally; "
          f"slowest {slow.customer_state} {slow.avg_delivery_days} days "
          f"({slow.days_vs_natl_avg} days above national average).")

    lv = late_vs_ontime.set_index("is_on_time")
    print(f"5. LATENESS HURTS REVIEWS: on-time orders avg {lv.loc[True].avg_review_score} "
          f"stars vs late {lv.loc[False].avg_review_score} stars; "
          f"{lv.loc[False].pct_1star}% of late orders get 1 star "
          f"(vs {lv.loc[True].pct_1star}% on-time).")

    rp = repeat.iloc[0]
    print(f"6. LOYALTY: only {rp.repeat_rate_pct}% of customers buy 2+ times "
          f"({rp.repeat_customers:,} of {rp.total_customers:,}); "
          f"avg {rp.avg_orders_per_customer} orders/customer. Repeat buyers = "
          f"{rev_split[rev_split.buyer_type=='repeat'].pct_of_revenue.iloc[0]}% of revenue.")

    print(f"\nAll CSVs saved in {OUT}/")
    print("EDA complete.")


if __name__ == "__main__":
    main()
