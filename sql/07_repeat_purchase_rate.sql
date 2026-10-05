-- ============================================================
-- KPI 7: REPEAT PURCHASE RATE
-- Brief §4: "Customers with 2+ orders / all customers"
-- Uses customer_unique_id (the stable PERSON id). customer_id changes
--   on every order in Olist, so using it would make everyone a
--   one-time buyer. This is the single most important gotcha in this
--   dataset.
-- ============================================================
WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT f.order_id) AS n_orders
    FROM fact_orders f
    JOIN dim_customers c ON c.customer_id = f.customer_id
    GROUP BY c.customer_unique_id
)
SELECT
    COUNT(*)                                             AS total_customers,
    COUNT(*) FILTER (WHERE n_orders >= 2)                AS repeat_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE n_orders >= 2)
          / NULLIF(COUNT(*), 0), 2)                      AS repeat_rate_pct,
    ROUND(AVG(n_orders)::numeric, 2)                     AS avg_orders_per_customer
FROM customer_orders;
