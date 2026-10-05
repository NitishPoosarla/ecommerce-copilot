-- ============================================================
-- KPI 2: REVENUE BY CUSTOMER STATE (BRL)
-- Brief §4: "Revenue ... by state"
-- Answers Section 3: which states matter most commercially.
-- Ranked descending with each state's share of total revenue.
-- ============================================================
SELECT
    c.customer_state,
    COUNT(DISTINCT f.order_id)                          AS orders,
    ROUND(SUM(f.price + f.freight_value)::numeric, 2)   AS revenue_brl,
    ROUND((100.0 * SUM(f.price + f.freight_value)
           / SUM(SUM(f.price + f.freight_value)) OVER ())::numeric, 1)
                                                       AS pct_of_total
FROM fact_orders f
JOIN dim_customers c ON c.customer_id = f.customer_id
GROUP BY c.customer_state
ORDER BY revenue_brl DESC;
