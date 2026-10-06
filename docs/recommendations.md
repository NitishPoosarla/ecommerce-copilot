# Recommendations for the Operations Manager

**Prepared:** 05-10-2026 · **Data:** Olist 2016–2018 · **Source:** `analysis/outputs/*.csv`
(Every number below traces to a CSV produced by `analysis/eda.py`.)

**Scope caveat (stated honestly):** historical decision support, not forecasting.
No marketing-spend data, so no ROI claims; revenue impact figures are
arithmetic projections from observed averages, not forecasts.

---

## Recommendation 1 — Fix the Northeast delivery corridor (6 states)

**Finding.** Delivery failure is regional, not platform-wide. The platform is
91.89% on-time overall, but six Northeast states fall far below that line, and
they are slow on top of it.

**The numbers** (`03b_ontime_by_state.csv`, `04_delivery_days_by_state.csv`,
national baseline `03a_ontime_overall.csv`):

| State | On-time % | Avg delivery days | Late orders above national benchmark |
|---|---|---|---|
| AL | 76.1% | 24.5 | 63 |
| MA | 80.3% | 21.6 | 83 |
| PI | 84.0% | 19.5 | 38 |
| CE | 84.7% | 21.3 | 92 |
| SE | 84.8% | 21.5 | 24 |
| BA | 86.0% | 19.3 | 192 |
| **Total** | vs **91.89%** | vs **12.6 days** national | **492 excess late orders** |

AL takes **24.5 days — 11.9 days more than the 12.6-day national average**.

**Suggested action.** Audit the carrier/fulfilment path for AL, MA, PI, CE, SE,
BA specifically: negotiate a regional carrier SLA or add a Northeast sorting
hub, with a target of ≥90% on-time in these states within one quarter. Closing
just this gap eliminates **~492 late orders per observed period** — and per
Recommendation 2, each avoided late order is a 1-star review avoided with
~46% probability.

---

## Recommendation 2 — Get proactive with at-risk orders (protect the rating)

**Finding.** Lateness doesn't just disappoint customers — it actively poisons
public ratings, and it is the single largest identifiable source of 1-star
reviews.

**The numbers** (`05b_late_vs_ontime_reviews.csv`, `05a_review_score_distribution.csv`):

| | Avg review score | Share rated 1 star |
|---|---|---|
| On-time orders | **4.30** | 6.6% |
| Late orders | **2.57** | **46.1%** |

- 7,620 late orders were reviewed; 46.1% of them ≈ **3,513 one-star reviews**.
- Total 1-star reviews in the dataset: **10,715** → **32.8% of ALL 1-star
  reviews come from late deliveries alone** (3,513 / 10,715).

**Suggested action.** Trigger a proactive message (email/SMS) the moment an
order's predicted delivery slips past its estimate — status explanation plus a
small goodwill voucher. Even if this only converts *half* of would-be 1-star
ratings into 3-star, it removes ~**1,750 one-star reviews per period** from the
public score. Pair with Recommendation 1: the same 6 states are both the
worst-performing delivery region and the biggest review liability.

---

## Recommendation 3 — Run a second-purchase program for first-time buyers

**Finding.** The marketplace is ~97% one-time buyers, and repeat customers are
worth almost twice per customer — but they're so rare that 94.3% of revenue
hangs on non-repeat behavior.

**The numbers** (`06_repeat_purchase_rate.csv`, `07_revenue_repeat_vs_onetime.csv`):

- Repeat purchase rate: **3.05%** (2,913 of 95,420 customers), avg **1.034
  orders/customer**.
- Revenue share: one-time **94.3%** (14,939,300 BRL) vs repeat **5.7%**
  (904,445 BRL).
- Revenue per customer: repeat **≈310 BRL** (904,445 / 2,913) vs one-time
  **≈161 BRL** (14,939,300 / 92,507) → a repeat customer is worth **~1.9×**.
- Top-10 categories = **9,874,221 BRL ≈ 62% of all revenue** (`02_category_rank_top_bottom.csv`)
  → they are where a second purchase is most likely.

**Suggested action.** Add an automated post-purchase flow: a personalized
second-purchase offer 14–30 days after delivery, targeted first at buyers of
the top-10 categories (62% of revenue lives there). **Quantified upside:**
converting just +1 percentage point of customers to repeat (+954 customers) at
the average order value (~161 BRL) adds **≈154,000 BRL per observed period**;
each converted customer's lifetime runs to the repeat average of ~310 BRL.
Note the brief's own limitation: with only 3.05% repeat behavior, treat this
as a test-and-measure experiment, not a churn model.

---

### How these three compose

1 fixes *where* delivery breaks (492 excess late orders), 2 mitigates *what
lateness costs* (32.8% of all 1-star reviews), 3 attacks the *structural*
revenue risk (94.3% one-time revenue). All three cite Phase-2/3 outputs; no
claim above is unsourced.
