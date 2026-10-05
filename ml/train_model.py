"""
Phase 4, STEP 2 — Late-delivery risk model.

Run:  ./venv/Scripts/python.exe ml/train_model.py

WHAT IT DOES
  1. Pulls delivered orders from the warehouse with ONLY order-time features
  2. Engineers 4 simple features (purchase month/hour/day-of-week + the
     delivery lead time we offered the customer)
  3. 80/20 stratified split, trains LogisticRegression AND RandomForest
  4. Reports accuracy / precision / recall / ROC-AUC for both
  5. Saves the winner to ml/model.joblib (+ feature list) and writes
     ml/model_card.md

DATA LEAKAGE RULE (the whole point of this exercise)
  The model scores an order at the MOMENT IT IS PLACED, so it may only use
  facts known at that moment: when/where it was placed, what was bought,
  from whom, price/freight, and the delivery estimate offered to the buyer.
  FORBIDDEN (they happen after purchase and would leak the answer):
    customer_delivery_ts, estimated-vs-actual gap, delivery_days,
    is_delivered, is_on_time (that IS the target), review_score,
    approved_ts / carrier_delivery_ts, order_status.

TARGET DEFINITION
  is_late = True when the order arrived after its estimated date.
  Only DELIVERED orders are used: undelivered orders have no known outcome
  (is_on_time is NULL for them) — we cannot label them late or on-time.
"""
import os
from datetime import datetime

import joblib
import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# --------------------------------------------------------------------------
# Feature schema — kept in one place; api/main.py must mirror this list.
# --------------------------------------------------------------------------
NUMERIC_FEATURES = [
    "purchase_month",        # seasonality (Nov = Black Friday chaos)
    "purchase_hour",         # time of day (weekend/night orders?)
    "purchase_dow",          # 0=Mon .. 6=Sun
    "estimated_lead_days",   # ENGINEERED: days between order and promised
                             # arrival — long promises correlate with remote
                             # destinations (the single strongest signal)
    "freight_value",         # shipping cost paid (remote = expensive)
    "price",                 # item value
    "product_weight_g",      # heavy items ship slower
    "length_cm", "height_cm", "width_cm",   # bulky items ship slower
]
CATEGORICAL_FEATURES = [
    "customer_state",        # destination (Northeast is slow — EDA finding)
    "product_category_en",
    "seller_state",          # origin (distance to destination matters)
]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "is_late"


def get_engine():
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    url = url.replace("postgres://", "postgresql+psycopg2://", 1) \
        if url.startswith("postgres://") else \
        url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return sa.create_engine(url)


def load_training_data() -> pd.DataFrame:
    """Delivered orders + ONLY order-time features. Item grain."""
    eng = get_engine()
    sql = """
        SELECT
            -- facts known at purchase time:
            f.purchase_ts,
            f.estimated_delivery_ts,   -- the promise made to the customer
            f.freight_value,
            f.price,
            f.is_on_time,              -- used ONLY to derive the target
            c.customer_state,
            p.product_category_en,
            p.product_weight_g,
            p.length_cm,
            p.height_cm,
            p.width_cm,
            s.seller_state
        FROM fact_orders f
        JOIN dim_customers c ON c.customer_id = f.customer_id
        JOIN dim_products  p ON p.product_id  = f.product_id
        JOIN dim_sellers   s ON s.seller_id   = f.seller_id
        WHERE f.is_delivered           -- undelivered = unlabeled, drop
          AND f.is_on_time IS NOT NULL -- belt & braces: need the label
    """
    df = pd.read_sql(sql, eng)
    print(f"loaded {len(df):,} delivered order items")

    # ---- feature engineering (all derived from order-time fields only) ----
    df["purchase_month"] = df["purchase_ts"].dt.month
    df["purchase_hour"] = df["purchase_ts"].dt.hour
    df["purchase_dow"] = df["purchase_ts"].dt.dayofweek
    df["estimated_lead_days"] = (
        (df["estimated_delivery_ts"] - df["purchase_ts"]).dt.total_seconds() / 86400
    ).round(1)

    # ---- target ----
    df[TARGET] = (~df["is_on_time"].astype("boolean")).astype(int)
    # is_on_time is never NULL here (WHERE clause), so this is safe.

    # categorical NaNs -> 'unknown' (OneHotEncoder can't take NaN)
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].fillna("unknown")

    # defense in depth: verify NO forbidden columns leaked into FEATURES
    forbidden = {"customer_delivery_ts", "delivery_days", "review_score",
                 "is_delivered", "is_on_time", "order_status",
                 "approved_ts", "carrier_delivery_ts"}
    assert not (set(FEATURES) & forbidden), \
        f"LEAKAGE: forbidden features present: {set(FEATURES) & forbidden}"
    return df


def build_pipelines():
    """Two candidate models sharing one preprocessing step.

    ColumnTransformer:
      - numeric: median-impute (product weight has nulls) + scale
                 (LogisticRegression needs scaling; trees don't mind it)
      - categorical: one-hot encode, ignore unseen states/categories
    """
    preprocessor = ColumnTransformer(transformers=[
        ("num", Pipeline([("impute", SimpleImputer(strategy="median")),
                          ("scale", StandardScaler())]), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return {
        "logistic_regression": Pipeline([
            ("prep", preprocessor),
            ("clf", LogisticRegression(max_iter=1000, random_state=42)),
        ]),
        "random_forest": Pipeline([
            ("prep", preprocessor),
            ("clf", RandomForestClassifier(
                # NO class_weight='balanced': it inflates predict_proba ~4x
                # (mean 0.35 vs a true late-rate of 0.079), which would break
                # the API's Low/Medium/High probability bands. The imbalance
                # is handled honestly instead — see model_card.md: recall at
                # the 0.5 cut is low, and the 0.30 band cut is the useful
                # operating point (high precision, 8x lift over base rate).
                n_estimators=200, min_samples_leaf=5,
                n_jobs=-1, random_state=42)),
        ]),
    }


def evaluate(name, model, X_test, y_test) -> dict:
    """Accuracy / precision / recall / ROC-AUC at the default 0.5 cut."""
    pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1]
    m = {
        "accuracy": round(accuracy_score(y_test, pred), 4),
        "precision": round(precision_score(y_test, pred, zero_division=0), 4),
        "recall": round(recall_score(y_test, pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_test, proba), 4),
    }
    print(f"  {name:<22} " + "  ".join(f"{k}={v}" for k, v in m.items()))
    return m


def write_model_card(metrics, late_rate, n_train, n_test, winner_name,
                     band_stats):
    """ml/model_card.md — required artifact; documents features + limits."""
    lines = f"""# Model Card — Late-Delivery Risk Model

**Owner:** Nitish Poosarla · **Trained:** {datetime.now():%Y-%m-%d} ·
**Artifact:** `ml/model.joblib` (scikit-learn {__import__('sklearn').__version__})

## Intended use
Score each *incoming* order with the probability it arrives after the
promised date, so operations can intervene before the customer is
disappointed. **Exploratory / decision-support only** — not a commitment
engine, not a customer-facing SLA.

## Target
`is_late = 1` if the order's actual delivery date > its estimated delivery
date. Trained on **delivered orders only** ({n_train + n_test:,} item rows;
undelivered orders are unlabeled and excluded).

## Class balance
**{late_rate:.1f}% of delivered order items were late** — a minority class.
Accuracy alone would be misleading (a "always on-time" guesser scores
{100 - late_rate:.1f}%); that is why precision/recall/ROC-AUC are reported.

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
| LogisticRegression | {metrics['logistic_regression']['accuracy']} | {metrics['logistic_regression']['precision']} | {metrics['logistic_regression']['recall']} | {metrics['logistic_regression']['roc_auc']} |
| RandomForest | {metrics['random_forest']['accuracy']} | {metrics['random_forest']['precision']} | {metrics['random_forest']['recall']} | {metrics['random_forest']['roc_auc']} |

**Selected model:** `{winner_name}` (highest ROC-AUC; ROC-AUC ranks
probabilities and is the fairest metric under class imbalance).

## Band quality (the API's Low <30% / Medium 30-60% / High >60% cuts)
On the held-out test set the ≥0.30 cut flags **{band_stats['flagged_pct']:.1f}%**
of orders; **{band_stats['flagged_precision']:.1f}%** of flagged orders are truly
late — a **{band_stats['flagged_precision'] / late_rate:.0f}x** lift over the
{late_rate:.1f}% base rate — and it catches {band_stats['late_caught_pct']:.1f}% of all
late orders. Think of ≥0.30 as a high-precision alert, not a safety net.
Probabilities are uncalibrated tree votes but honest in aggregate (mean
predicted {band_stats['mean_pred']:.3f} vs true late-rate {late_rate / 100:.3f} on the test set).

## Limitations (stated honestly, per brief §5)
1. **Historical data (2016–2018)** — decision support, NOT real-time
   forecasting; logistics and carriers have changed since.
2. **Correlations, not causes** — the model can rank risk, not tell you
   *why* an order is slow (see recommendations.md for the operational read).
3. **Class imbalance** — at the default 0.5 cut the model almost never
   flags anything (recall {metrics[winner_name]['recall']}): with only
   {late_rate:.1f}% late orders, an 'always on-time' guesser already scores
   {100 - late_rate:.1f}% accuracy, and that is roughly what accuracy reports
   here. Ranking (ROC-AUC) and the 0.30 band cut are the meaningful
   operating points; lower the cut further for more recall at the cost of
   precision.
4. **No route/weather/carrier data** — unexplained variance is expected;
   ROC-AUC well below 0.9 is honest for these features.
5. **Item grain** — multi-item orders contribute several rows sharing one
   outcome; metrics are per item, not per order.
6. **Geography shift** — new states/categories unseen in training are
   one-hot-ignored (predictions fall back to intercept/prior).
"""
    os.makedirs("ml", exist_ok=True)
    with open("ml/model_card.md", "w", encoding="utf-8") as fh:
        fh.write(lines)
    print("wrote ml/model_card.md")


def main():
    df = load_training_data()
    late_rate = df[TARGET].mean() * 100
    print(f"\nclass balance: {late_rate:.1f}% late "
          f"({df[TARGET].sum():,} late / {len(df):,})")
    if not 1 < late_rate < 50:
        print("  -> strong imbalance: accuracy is NOT a trustworthy metric alone")

    X = df[FEATURES]
    y = df[TARGET]
    # stratified 80/20 split keeps the late-rate identical in both halves
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y)
    print(f"\ntrain={len(X_train):,}  test={len(X_test):,}  "
          f"test late-rate={y_test.mean()*100:.1f}%")

    print("\nmodel comparison on held-out test set:")
    metrics, models = {}, {}
    for name, pipe in build_pipelines().items():
        pipe.fit(X_train, y_train)
        metrics[name] = evaluate(name, pipe, X_test, y_test)
        models[name] = pipe

    winner_name = max(metrics, key=lambda k: metrics[k]["roc_auc"])
    winner = models[winner_name]
    print(f"\nselected: {winner_name} (best ROC-AUC)")

    # Band quality: what the API's Low/Medium/High cuts actually deliver.
    proba = winner.predict_proba(X_test)[:, 1]
    flagged = proba >= 0.30
    band_stats = {
        "flagged_pct": flagged.mean() * 100,
        "flagged_precision": (y_test[flagged] == 1).mean() * 100
        if flagged.any() else 0.0,
        "late_caught_pct": (proba[y_test == 1] >= 0.30).mean() * 100,
        "mean_pred": proba.mean(),
    }
    print(f"band >=0.30: flags {band_stats['flagged_pct']:.1f}% of orders, "
          f"precision {band_stats['flagged_precision']:.1f}%, "
          f"catches {band_stats['late_caught_pct']:.1f}% of late orders")

    os.makedirs("ml", exist_ok=True)
    joblib.dump({
        "model": winner,
        "model_name": winner_name,
        "features": FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "metrics": metrics,
        "band_stats": {k: round(v, 3) for k, v in band_stats.items()},
        "test_late_rate_pct": round(late_rate, 2),
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }, "ml/model.joblib")
    print("saved ml/model.joblib")

    write_model_card(metrics, late_rate, len(X_train), len(X_test),
                     winner_name, band_stats)
    print("\ntrain_model complete.")


if __name__ == "__main__":
    main()
