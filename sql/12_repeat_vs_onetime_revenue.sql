-- ============================================================
-- KPI 12: REVENUE — REPEAT vs ONE-TIME BUYERS
-- Brief Section 3: "How much revenue comes from repeat customers
--                   vs one-time buyers?"
-- Step 1 collapses items -> one row per ORDER (money summed at order
--        grain so multi-item orders count once).
-- Step 2 flags customers (customer_unique_id!) with 2+ orders.
-- Step 3 sums order revenue by that flag.
-- ============================================================
WITH orders AS (
    SELECT DISTINCT order_id, customer_id
    FROM fact_orders
),
order_money AS (
    SELECT order_id, SUM(price + freight_value) AS order_revenue
    FROM fact_orders
    GROUP BY order_id
),
customer_order_counts AS (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS n_orders
    FROM orders o
    JOIN dim_customers c ON c.customer_id = o.customer_id
    GROUP BY c.customer_unique_id
)
SELECT
    CASE WHEN coc.n_orders >= 2 THEN 'repeat_customer'
         ELSE 'one_time_customer' END                    AS customer_type,
    COUNT(DISTINCT om.order_id)                          AS orders,
    ROUND(SUM(om.order_revenue)::numeric, 2)             AS revenue_brl,
    ROUND((100.0 * SUM(om.order_revenue)
           / SUM(SUM(om.order_revenue)) OVER ())::numeric, 1)
                                                       AS pct_of_revenue
FROM order_money om
JOIN orders o            ON o.order_id = om.order_id
JOIN dim_customers c     ON c.customer_id = o.customer_id
JOIN customer_order_counts coc
                         ON coc.customer_unique_id = c.customer_unique_id
GROUP BY 1
ORDER BY revenue_brl DESC;
