-- ============================================================
-- KPI 11: PAYMENT TYPES (share of paid value)
-- Brief: "payment types"
-- NOTE on grain: dim_payments is per payment SEQUENTIAL, and an order
--   can have several payments (e.g. voucher + credit card). We aggregate
--   to payment level — NOT joined to fact_orders — so no item
--   duplication can distort the money. Orders counted DISTINCTLY.
-- ============================================================
SELECT
    p.payment_type,
    COUNT(DISTINCT p.order_id)                           AS orders,
    COUNT(*)                                             AS payment_rows,
    ROUND(SUM(p.payment_value)::numeric, 2)              AS paid_brl,
    ROUND((100.0 * SUM(p.payment_value)
           / SUM(SUM(p.payment_value)) OVER ())::numeric, 1) AS pct_of_value,
    ROUND(AVG(p.payment_installments)::numeric, 1)       AS avg_installments
FROM dim_payments p
GROUP BY p.payment_type
ORDER BY paid_brl DESC;
