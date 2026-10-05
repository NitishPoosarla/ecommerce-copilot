-- ============================================================
-- KPI 6: AVERAGE REVIEW SCORE (1-5 stars)
-- Brief §4: "Avg review score: 1-5 stars per order"
-- One row per order (DISTINCT), only orders that actually have a review.
-- Overall average + distribution so we see if the mean hides skew.
-- ============================================================
SELECT
    COUNT(*)                                             AS reviewed_orders,
    ROUND(AVG(review_score)::numeric, 2)                 AS avg_review_score,
    COUNT(*) FILTER (WHERE review_score = 1)            AS score_1,
    COUNT(*) FILTER (WHERE review_score = 2)            AS score_2,
    COUNT(*) FILTER (WHERE review_score = 3)            AS score_3,
    COUNT(*) FILTER (WHERE review_score = 4)            AS score_4,
    COUNT(*) FILTER (WHERE review_score = 5)            AS score_5
FROM (
    SELECT DISTINCT order_id, review_score
    FROM fact_orders
    WHERE review_score IS NOT NULL
) r;
