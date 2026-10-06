# KPI Definitions — E-commerce Intelligence

**Source:** extracted from `business_brief.md` (Section 4: KPIs measured every analysis).
**Currency:** BRL. **Data period:** 2016–2018 (Olist Brazilian e-commerce).

## Revenue
Sum of order value (BRL) by month / state / category.
Order value = price + freight. Because `fact_orders` has one row per order
ITEM, order-level revenue totals must be computed so each item is counted
once; the canonical platform total is **15,843,553.24 BRL**.

## On-time delivery %
Orders delivered on or before the estimated date ÷ delivered orders.
Measured per DISTINCT order (not per item) to avoid double counting.
Platform baseline: **91.89% on-time**.

## Avg delivery days
Purchase date → customer delivery date. National average: **12.6 days**.

## Avg review score
1–5 stars per order. Platform average: **4.11**.

## Repeat purchase rate
Customers with 2+ orders ÷ all customers. The stable person identifier is
`customer_unique_id` (the raw `customer_id` changes on every order).
Measured: **3.05%** (2,913 of 95,420 customers).

## Review–lateness link
Avg review score of late vs on-time orders. Measured: **2.57 late vs 4.30
on-time**; 46.1% of late orders are rated 1 star.

## Scope & limitations (stated honestly)
- Historical data (2016–2018): decision support, NOT real-time forecasting.
- No marketing-spend data → no ad ROI analysis.
- Mostly one-time buyers → churn modeling not credible; ML used only for
  late-delivery risk with order-time features.
- Currency: BRL.
