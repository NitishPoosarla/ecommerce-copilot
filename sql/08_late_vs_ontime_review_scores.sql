-- ============================================================
-- KPI 8: LATE vs ON-TIME REVIEW SCORES  (the core hypothesis)
-- Brief §4: "Avg review score of late vs on-time orders"
-- This is the money question: does lateness actually drive bad reviews?
-- One row per reviewed+delivered order, grouped by on-time status.
-- ============================================================
SELECT
    o.is_on_time,
    COUNT(*)                                             AS orders,
    ROUND(AVG(o.review_score)::numeric, 2)               AS avg_review_score,
    ROUND(100.0 * COUNT(*) FILTER (WHERE review_score = 1)
          / COUNT(*), 1)                                 AS pct_1star
FROM (
    SELECT DISTINCT order_id, is_on_time, review_score
    FROM fact_orders
    WHERE is_on_time IS NOT NULL      -- delivered only (late or on-time)
      AND review_score IS NOT NULL    -- has a review
) o
GROUP BY o.is_on_time
ORDER BY o.is_on_time DESC;
-- Expected: is_on_time=true has a higher avg score than false.
