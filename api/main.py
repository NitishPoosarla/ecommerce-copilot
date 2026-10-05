"""
Phase 4, STEP 3 — REST API for the E-commerce Intelligence Copilot.

Run:  ./venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
Docs: http://localhost:8000/docs   (Swagger UI — auto-generated from docstrings)

Endpoints
  GET  /health         liveness probe
  GET  /kpis           4 headline KPIs, straight from the warehouse
  GET  /kpis/by-state  on-time % and avg delivery days per customer state
  POST /predict        late-delivery risk probability + Low/Medium/High band

Design notes
  - DATABASE_URL comes from .env (same connection as every other phase).
  - The model artifact + feature list are loaded once and cached.
  - /predict re-derives purchase month/hour/dow and estimated_lead_days from
    the raw timestamps, mirroring ml/train_model.py EXACTLY — the API must
    never ask callers to hand-compute training features.
"""
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="E-commerce Revenue & Customer Experience Intelligence API",
    description=(
        "KPI reporting and late-delivery risk scoring for the Olist "
        "Brazilian e-commerce warehouse (2016-2018, BRL). "
        "The /predict endpoint uses ONLY features known at order placement."
    ),
    version="1.0.0",
)

MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "model.joblib"


# ---------------------------------------------------------------- connections
@lru_cache(maxsize=1)
def get_engine() -> sa.Engine:
    """Create the Postgres engine once per process (cached)."""
    load_dotenv()
    url = __import__("os").environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL missing from .env")
    url = url.replace("postgres://", "postgresql+psycopg2://", 1) \
        if url.startswith("postgres://") else \
        url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return sa.create_engine(url)


@lru_cache(maxsize=1)
def get_model() -> dict:
    """Load the trained model artifact once per process (cached)."""
    if not MODEL_PATH.exists():
        raise RuntimeError("ml/model.joblib not found — run ml/train_model.py first")
    return joblib.load(MODEL_PATH)


# ------------------------------------------------------------ response models
class KPIs(BaseModel):
    """Headline KPIs computed from the warehouse (order-level grain)."""
    total_revenue_brl: float = Field(description="Sum of item price + freight, all orders")
    on_time_pct: float = Field(description="Delivered orders arriving on/before estimate")
    avg_review_score: float = Field(description="Mean star rating, reviewed orders (1-5)")
    repeat_purchase_rate_pct: float = Field(description="Customers with 2+ orders / all customers")


class StateKPI(BaseModel):
    """Delivery performance for one customer state."""
    customer_state: str
    delivered_orders: int
    on_time_pct: float | None = Field(None, description="Null when no delivered orders")
    avg_delivery_days: float | None = Field(None, description="Mean purchase -> arrival days")


class PredictRequest(BaseModel):
    """Order features, ALL known at the moment the order is placed."""
    purchase_ts: datetime = Field(description="When the customer placed the order")
    estimated_delivery_ts: datetime = Field(
        description="Delivery date promised to the customer at checkout")
    customer_state: str = Field(description="Destination state, e.g. 'SP'")
    seller_state: str = Field(description="Seller (origin) state, e.g. 'RJ'")
    product_category_en: str = Field(description="English product category")
    price: float = Field(gt=0, description="Item price in BRL")
    freight_value: float = Field(ge=0, description="Shipping cost in BRL")
    product_weight_g: float | None = Field(None, ge=0, description="Product weight (grams)")
    length_cm: float | None = Field(None, ge=0, description="Package length")
    height_cm: float | None = Field(None, ge=0, description="Package height")
    width_cm: float | None = Field(None, ge=0, description="Package width")


class PredictResponse(BaseModel):
    """Risk score output. Bands: Low < 30%, Medium 30-60%, High > 60%."""
    late_probability: float = Field(description="P(order arrives after estimate), 0-1")
    risk_band: str = Field(description="Low | Medium | High")
    model: str = Field(description="Name of the model that produced the score")


# ------------------------------------------------------------------ endpoints
@app.get("/health", summary="Liveness probe")
def health() -> dict:
    """Returns service status. Use it in uptime monitors and load balancers."""
    return {"status": "ok"}


@app.get("/kpis", response_model=KPIs, summary="Headline business KPIs")
def kpis() -> KPIs:
    """The four brief-mandated KPIs, computed live from the warehouse:
    total revenue (BRL), on-time delivery %, avg review score (1-5), and
    repeat purchase rate. Order-level metrics collapse to DISTINCT order_id
    so multi-item orders are never double counted."""
    sql = """
        WITH og AS (
            SELECT DISTINCT order_id, is_delivered, is_on_time, review_score
            FROM fact_orders
        ),
        cust AS (
            SELECT c.customer_unique_id,
                   COUNT(DISTINCT f.order_id) AS n_orders
            FROM fact_orders f
            JOIN dim_customers c ON c.customer_id = f.customer_id
            GROUP BY c.customer_unique_id
        )
        SELECT
            (SELECT ROUND(COALESCE(SUM((price + freight_value)::numeric), 0), 2)
             FROM fact_orders) AS total_revenue_brl,
            (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE is_on_time)
                          / NULLIF(COUNT(*) FILTER (WHERE is_delivered), 0), 2)
             FROM og) AS on_time_pct,
            (SELECT ROUND(AVG(review_score)::numeric, 2)
             FROM og WHERE review_score IS NOT NULL) AS avg_review_score,
            (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE n_orders >= 2)
                          / NULLIF(COUNT(*), 0), 2)
             FROM cust) AS repeat_purchase_rate_pct
    """
    with get_engine().connect() as conn:
        row = conn.exec_driver_sql(sql).mappings().first()
    return KPIs(
        total_revenue_brl=float(row["total_revenue_brl"]),
        on_time_pct=float(row["on_time_pct"]),
        avg_review_score=float(row["avg_review_score"]),
        repeat_purchase_rate_pct=float(row["repeat_purchase_rate_pct"]),
    )


@app.get("/kpis/by-state", response_model=list[StateKPI], summary="Delivery KPIs by state")
def kpis_by_state() -> list[StateKPI]:
    """On-time delivery % and average delivery days for every customer state.
    The Operations Manager's 'where is delivery worst' question, as JSON.
    States with zero delivered orders return null percentages."""
    sql = """
        WITH og AS (
            SELECT DISTINCT order_id, customer_id,
                            is_delivered, is_on_time, delivery_days
            FROM fact_orders
        )
        SELECT c.customer_state,
               COUNT(*) FILTER (WHERE o.is_delivered) AS delivered_orders,
               ROUND(100.0 * COUNT(*) FILTER (WHERE o.is_on_time)
                     / NULLIF(COUNT(*) FILTER (WHERE o.is_delivered), 0), 1)
                   AS on_time_pct,
               ROUND(AVG(o.delivery_days)::numeric, 1) AS avg_delivery_days
        FROM og o
        JOIN dim_customers c ON c.customer_id = o.customer_id
        GROUP BY c.customer_state
        ORDER BY on_time_pct ASC NULLS LAST, c.customer_state
    """
    with get_engine().connect() as conn:
        rows = conn.exec_driver_sql(sql).mappings().all()
    return [StateKPI(
        customer_state=r["customer_state"],
        delivered_orders=r["delivered_orders"],
        on_time_pct=float(r["on_time_pct"]) if r["on_time_pct"] is not None else None,
        avg_delivery_days=float(r["avg_delivery_days"])
        if r["avg_delivery_days"] is not None else None,
    ) for r in rows]


@app.post("/predict", response_model=PredictResponse, summary="Late-delivery risk")
def predict(req: PredictRequest) -> PredictResponse:
    """Score the probability that an order arrives AFTER its promised date.

    Send only facts known at checkout (timestamps, states, category, price,
    freight, package dimensions). The service derives purchase month/hour/
    day-of-week and the promised lead time exactly as training did.

    Risk bands: Low < 0.30, Medium 0.30-0.60, High > 0.60.
    """
    if req.estimated_delivery_ts < req.purchase_ts:
        raise HTTPException(
            status_code=422,
            detail="estimated_delivery_ts must be on or after purchase_ts",
        )

    artifact = get_model()
    lead_days = (req.estimated_delivery_ts - req.purchase_ts).total_seconds() / 86400

    # Mirror ml/train_model.py feature engineering — keep both in sync.
    features = pd.DataFrame([{
        "purchase_month": req.purchase_ts.month,
        "purchase_hour": req.purchase_ts.hour,
        "purchase_dow": req.purchase_ts.weekday(),    # stdlib: 0=Mon .. 6=Sun
        "estimated_lead_days": round(lead_days, 1),
        "freight_value": req.freight_value,
        "price": req.price,
        "product_weight_g": req.product_weight_g,
        "length_cm": req.length_cm,
        "height_cm": req.height_cm,
        "width_cm": req.width_cm,
        "customer_state": req.customer_state,
        "product_category_en": req.product_category_en,
        "seller_state": req.seller_state,
    }])

    proba = float(artifact["model"]
                  .predict_proba(features[artifact["features"]])[:, 1][0])
    band = "Low" if proba < 0.30 else ("Medium" if proba <= 0.60 else "High")
    return PredictResponse(
        late_probability=round(proba, 4),
        risk_band=band,
        model=artifact["model_name"],
    )
