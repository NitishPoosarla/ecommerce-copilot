-- ============================================================
-- KPI 14: WORST CATEGORIES FOR ON-TIME DELIVERY
-- Brief Section 3: "Which ... product categories have the worst
--                   delivery performance?"
-- Same pattern as KPI 13 but sliced by product category. Heavy/odd
--   shaped goods ship slower — this finds them.
-- Min 200 delivered orders to avoid small-sample noise.
-- ============================================================
WITH delivered AS (
    SELECT DISTINCT order_id, product_id, is_on_time, delivery_days
    FROM fact_orders
    WHERE is_delivered
)
SELECT
    p.product_category_en                               AS category,
    COUNT(*)                                             AS delivered_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE d.is_on_time)
          / COUNT(*), 1)                                 AS on_time_pct,
    ROUND(AVG(d.delivery_days)::numeric, 1)              AS avg_delivery_days
FROM delivered d
JOIN dim_products p ON p.product_id = d.product_id
GROUP BY p.product_category_en
HAVING COUNT(*) >= 200
ORDER BY on_time_pct ASC, delivered_orders DESC;
