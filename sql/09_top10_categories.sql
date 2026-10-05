-- ============================================================
-- KPI 9: TOP 10 CATEGORIES BY REVENUE (with cumulative share)
-- Brief §4: "Top categories" / Section 3: where to focus sales effort.
-- window function SUM(...) OVER (ORDER BY ...) = running total,
--   which tells us if revenue is concentrated in a few categories.
-- ============================================================
WITH cat_rev AS (
    SELECT
        p.product_category_en AS category,
        ROUND(SUM(f.price + f.freight_value)::numeric, 2) AS revenue_brl
    FROM fact_orders f
    JOIN dim_products p ON p.product_id = f.product_id
    GROUP BY p.product_category_en
)
SELECT
    category,
    revenue_brl,
    ROUND(100.0 * revenue_brl / SUM(revenue_brl) OVER (), 1)  AS pct_of_total,
    ROUND(100.0 * SUM(revenue_brl) OVER (ORDER BY revenue_brl DESC
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / SUM(revenue_brl) OVER (), 1)                      AS cumulative_pct
FROM cat_rev
ORDER BY revenue_brl DESC
LIMIT 10;
