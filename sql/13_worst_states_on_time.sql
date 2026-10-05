-- ============================================================
-- KPI 13: WORST STATES FOR ON-TIME DELIVERY
-- Brief Section 3: "Which states ... have the worst delivery
--                   performance?"
-- One row per delivered ORDER (DISTINCT fixes item grain), joined to
--   customer state. Min 200 orders so tiny states with 3 orders don't
--   dominate the 'worst' list (small-sample noise).
-- Ranked WORST first (lowest on-time rate).
-- ============================================================
WITH delivered AS (
    SELECT DISTINCT order_id, customer_id, is_on_time, delivery_days
    FROM fact_orders
    WHERE is_delivered
)
SELECT
    c.customer_state,
    COUNT(*)                                             AS delivered_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE d.is_on_time)
          / COUNT(*), 1)                                 AS on_time_pct,
    ROUND(AVG(d.delivery_days)::numeric, 1)              AS avg_delivery_days
FROM delivered d
JOIN dim_customers c ON c.customer_id = d.customer_id
GROUP BY c.customer_state
HAVING COUNT(*) >= 200
ORDER BY on_time_pct ASC, delivered_orders DESC;
