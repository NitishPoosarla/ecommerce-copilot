-- ============================================================
-- KPI 15: ON-TIME DELIVERY RATE + REVIEW SCORE BY MONTH (trend)
-- Brief §4: combines "On-time delivery rate" and "Avg review score";
--   measured over time it shows whether experience is improving or
--   deteriorating — the trend leadership actually acts on.
-- One row per delivered+reviewed order (DISTINCT at order grain).
-- ============================================================
SELECT
    d.year_month,
    COUNT(*)                                             AS orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE o.is_on_time)
          / COUNT(*), 1)                                 AS on_time_pct,
    ROUND(AVG(o.review_score)::numeric, 2)               AS avg_review_score,
    ROUND(AVG(o.delivery_days)::numeric, 1)              AS avg_delivery_days
FROM (
    SELECT DISTINCT order_id, purchase_date_key,
                    is_on_time, review_score, delivery_days
    FROM fact_orders
    WHERE is_delivered
) o
JOIN dim_date d ON d.date_key = o.purchase_date_key
GROUP BY d.year_month
ORDER BY d.year_month;
