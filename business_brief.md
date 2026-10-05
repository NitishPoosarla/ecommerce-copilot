# Business Brief: E-commerce Revenue & Customer Experience Intelligence Copilot

**Analyst:** Nitish Poosarla · **Date:** 05-10-2026 · **Data:** Olist Brazilian e-commerce, ~100k orders (2016–2018)

## 1. Business Problem
An online marketplace seller sees revenue but suspects customers are unhappy:
orders arrive late and buyers rarely purchase again. Leadership lacks a clear,
data-backed view of WHERE the experience breaks down and WHAT it costs.

## 2. Objective
Identify the operational and sales patterns that hurt customer experience and
repeat purchases, quantify their revenue impact, and recommend 3 actions.

## 3. Primary User
Operations Manager — needs answers to:
- Which states / product categories have the worst delivery performance?
- Does lateness actually drive bad reviews?
- How much revenue comes from repeat customers vs one-time buyers?

## 4. KPIs (measured every analysis)
| KPI | Definition |
|---|---|
| Revenue | Sum of order value (BRL) by month / state / category |
| On-time delivery % | Orders delivered on or before the estimated date ÷ delivered orders |
| Avg delivery days | Purchase date → customer delivery date |
| Avg review score | 1–5 stars per order |
| Repeat purchase rate | Customers with 2+ orders ÷ all customers |
| Review–lateness link | Avg review score of late vs on-time orders |

## 5. Scope & Limitations (stated honestly)
- Historical data (2016–2018): decision support, NOT real-time forecasting
- No marketing-spend data → no ad ROI analysis
- Mostly one-time buyers → churn modeling not credible; ML used only for
  late-delivery risk with order-time features
- Currency: BRL

## 6. Success Criteria
- [ ] Working SQL warehouse + 15 documented KPI queries
- [ ] Interactive dashboard answering Section 3 questions
- [ ] 3 evidence-backed recommendations with quantified impact
- [ ] Late-delivery risk model (documented limitations)
- [ ] RAG chatbot answering business questions with citations

## 7. Phases
Brief → SQL warehouse → Analysis+BI dashboard → API+ML → RAG chatbot → Publish
