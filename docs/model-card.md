# Model Card — Late-Delivery Risk Model

**Owner:** Nitish Poosarla · **Trained:** 2026-10-05 ·
**Artifact:** `ml/model.joblib` (scikit-learn 1.9.1)

## Intended use
Score each *incoming* order with the probability it arrives after the
promised date, so operations can intervene before the customer is
disappointed. **Exploratory / decision-support only** — not a commitment
engine, not a customer-facing SLA.

## Target
`is_late = 1` if the order's actual delivery date > its estimated delivery
date. Trained on **delivered orders only** (110,196 item rows;
undelivered orders are unlabeled and excluded).

## Class balance
**7.9% of delivered order items were late** — a minority class.
Accuracy alone would be misleading (a "always on-time" guesser scores
92.1%); that is why precision/recall/ROC-AUC are reported.

## Features (ALL known at order placement — no leakage)
| Feature | Type | Why it's allowed |
|---|---|---|
| purchase_month / hour / dow | numeric | calendar at order time |
| estimated_lead_days | numeric | **engineered**: promised arrival − purchase |
| freight_value, price | numeric | quoted at checkout |
| product_weight_g, L/H/W | numeric | in the catalog at purchase |
| customer_state | categorical | in the order record |
| seller_state | categorical | in the order record |
| product_category_en | categorical | in the order record |

Explicitly **excluded** (post-purchase = leakage): delivery timestamps,
delivery_days, is_delivered/is_on_time, review_score, order_status,
payment approval / carrier handoff times.

## Metrics (held-out 20% test set, stratified)
| Model | Accuracy | Precision | Recall | ROC-AUC |
|---|---|---|---|---|
| LogisticRegression | 0.9208 | 0.3333 | 0.0011 | 0.7009 |
| RandomForest | 0.9213 | 1.0 | 0.0052 | 0.8101 |

**Selected model:** `random_forest` (highest ROC-AUC; ROC-AUC ranks
probabilities and is the fairest metric under class imbalance).

## Band quality (the API's Low <30% / Medium 30-60% / High >60% cuts)
On the held-out test set the ≥0.30 cut flags **1.6%**
of orders; **61.5%** of flagged orders are truly
late — a **8x** lift over the
7.9% base rate — and it catches 12.4% of all
late orders. Think of ≥0.30 as a high-precision alert, not a safety net.
Probabilities are uncalibrated tree votes but honest in aggregate (mean
predicted 0.080 vs true late-rate 0.079 on the test set).

## Limitations (stated honestly, per brief §5)
1. **Historical data (2016–2018)** — decision support, NOT real-time
   forecasting; logistics and carriers have changed since.
2. **Correlations, not causes** — the model can rank risk, not tell you
   *why* an order is slow (see recommendations.md for the operational read).
3. **Class imbalance** — at the default 0.5 cut the model almost never
   flags anything (recall 0.0052): with only
   7.9% late orders, an 'always on-time' guesser already scores
   92.1% accuracy, and that is roughly what accuracy reports
   here. Ranking (ROC-AUC) and the 0.30 band cut are the meaningful
   operating points; lower the cut further for more recall at the cost of
   precision.
4. **No route/weather/carrier data** — unexplained variance is expected;
   ROC-AUC well below 0.9 is honest for these features.
5. **Item grain** — multi-item orders contribute several rows sharing one
   outcome; metrics are per item, not per order.
6. **Geography shift** — new states/categories unseen in training are
   one-hot-ignored (predictions fall back to intercept/prior).
