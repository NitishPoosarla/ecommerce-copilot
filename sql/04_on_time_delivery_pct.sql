-- ============================================================
-- KPI 4: ON-TIME DELIVERY RATE (pct)
-- Brief §4: "Orders delivered on or before the estimated date
--           / delivered orders"
-- CRITICAL grain fix: fact is per-item, delivery is per-order.
--   COUNT(*) over items would overcount multi-item orders, so we
--   first collapse to DISTINCT order_id (one row per order).
-- Undelivered orders are excluded from both numerator and denominator.
-- ============================================================
SELECT
    COUNT(*)                                             AS delivered_orders,
    COUNT(*) FILTER (WHERE is_on_time)                   AS on_time_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_on_time)
          / NULLIF(COUNT(*), 0), 2)                      AS on_time_pct,
    COUNT(*) FILTER (WHERE NOT is_on_time)               AS late_orders
FROM (
    SELECT DISTINCT order_id, is_delivered, is_on_time
    FROM fact_orders
    WHERE is_delivered
) o;
