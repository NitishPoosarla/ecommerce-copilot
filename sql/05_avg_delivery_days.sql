-- ============================================================
-- KPI 5: AVERAGE DELIVERY DAYS (purchase -> customer door)
-- Brief §4: "Avg delivery days: purchase date -> customer delivery date"
-- Collapses to one row per order first (item grain would bias toward
--   multi-item orders), then averages overall AND by month to show trend.
-- ============================================================
SELECT
    d.year_month,
    COUNT(*)                                             AS delivered_orders,
    ROUND(AVG(o.delivery_days)::numeric, 1)              AS avg_delivery_days,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY o.delivery_days)
          ::numeric, 1)                                  AS median_delivery_days
FROM (
    SELECT DISTINCT order_id, purchase_date_key, delivery_days
    FROM fact_orders
    WHERE delivery_days IS NOT NULL
) o
JOIN dim_date d ON d.date_key = o.purchase_date_key
GROUP BY d.year_month
ORDER BY d.year_month;
