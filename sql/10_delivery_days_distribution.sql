-- ============================================================
-- KPI 10: DELIVERY DAYS DISTRIBUTION (buckets)
-- Brief: "delivery days distribution"
-- Management doesn't want a mean alone — they want to know what
--   customers EXPERIENCE: is delivery usually 3 days or 15?
-- Bucketed at order grain; pct computed over all delivered orders.
-- ============================================================
SELECT
    CASE
        WHEN delivery_days <= 3  THEN '1. 0-3 days (fast)'
        WHEN delivery_days <= 7  THEN '2. 4-7 days'
        WHEN delivery_days <= 14 THEN '3. 8-14 days'
        WHEN delivery_days <= 30 THEN '4. 15-30 days'
        WHEN delivery_days <= 60 THEN '5. 31-60 days'
        ELSE                            '6. 60+ days (very late)'
    END                                                  AS delivery_bucket,
    COUNT(*)                                             AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)   AS pct_of_delivered
FROM (
    SELECT DISTINCT order_id, delivery_days
    FROM fact_orders
    WHERE delivery_days IS NOT NULL
) o
GROUP BY 1
ORDER BY 1;
