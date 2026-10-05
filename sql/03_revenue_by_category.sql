-- ============================================================
-- KPI 3: REVENUE BY PRODUCT CATEGORY (BRL)
-- Brief §4: "Revenue ... by category"
-- Uses the English-translated category from dim_products.
-- A multi-item order can span several categories; revenue for each
--   item lands in that item's category (that's correct at item grain).
-- ============================================================
SELECT
    p.product_category_en                              AS category,
    COUNT(DISTINCT f.order_id)                         AS orders,
    ROUND(SUM(f.price + f.freight_value)::numeric, 2)  AS revenue_brl
FROM fact_orders f
JOIN dim_products p ON p.product_id = f.product_id
GROUP BY p.product_category_en
ORDER BY revenue_brl DESC;
