My dashboards said reviews were fine. The delivery data disagreed.

A marketplace had 15.8M BRL in revenue but no answer: where does delivery break down, does lateness drive bad reviews, does anyone buy twice?

I built the full stack to answer them:

- SQL star-schema warehouse: 112,650-row fact table + 6 dims from 9 raw CSVs
- Streamlit BI dashboard for the ops manager
- Late-delivery risk model trained ONLY on order-time features (zero leakage)
- FastAPI REST API with live Swagger docs
- RAG copilot that cites every number and refuses when data doesn't exist

3 findings from 2016-2018 Olist data:

1. 91.89% on-time nationally, but the worst state (AL) hits 76.1% — 492 excess late orders across 6 Northeast states
2. Late orders average 2.57 stars vs 4.30 on-time — lateness alone causes 32.8% of ALL 1-star reviews
3. Only 3.05% of customers buy twice, yet they're worth ~1.9x more — 94.3% of revenue rides on one-time buyers

The hardest part wasn't building it. It was making it honest: a denominator audit on every percentage, a refusal route for questions no table can answer, and a 9-question regression suite the copilot must pass.

Repo: https://github.com/NitishPoosarla/ecommerce-copilot

#DataEngineering #Python #SQL #MachineLearning #RAG #FastAPI #Streamlit
