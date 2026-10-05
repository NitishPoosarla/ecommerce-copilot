-- ============================================================
-- KPI 1: REVENUE BY MONTH (BRL)
-- Brief §4: "Revenue: Sum of order value by month"
-- Grain note: fact_orders = 1 row per ORDER ITEM, so SUM(price+freight)
--   counts every BRL exactly once (no double counting).
-- Revenue = item price + freight charged to the customer.
-- ============================================================
SELECT
    d.year_month,
    COUNT(DISTINCT f.order_id)                          AS orders,
    ROUND(SUM(f.price + f.freight_value)::numeric, 2)   AS revenue_brl
FROM fact_orders f
JOIN dim_date d ON d.date_key = f.purchase_date_key
GROUP BY d.year_month
ORDER BY d.year_month;
