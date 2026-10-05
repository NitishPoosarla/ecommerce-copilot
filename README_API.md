# API Documentation — E-commerce Intelligence API

FastAPI service exposing warehouse KPIs and the late-delivery risk model
(Phase 4 of the brief). Interactive Swagger docs ship with the service.

## Run it

```bash
./venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
```

| URL | What it is |
|---|---|
| http://localhost:8000/docs | **Swagger UI** — click "Try it out" to call endpoints in the browser |
| http://localhost:8000/redoc | ReDoc (alternative documentation view) |
| http://localhost:8000/openapi.json | Machine-readable OpenAPI 3.1 schema |

Connection settings come from `.env` (`DATABASE_URL`). The model artifact
`ml/model.joblib` must exist (run `ml/train_model.py` first).

---

## GET /health

Liveness probe for uptime monitors.

**Request**
```bash
curl http://localhost:8000/health
```
**Response** — `200 OK`
```json
{"status": "ok"}
```

---

## GET /kpis

The four headline KPIs from `business_brief.md` §4, computed live from the
warehouse. Order-level metrics collapse to one row per order first, so
multi-item orders are never double counted.

**Request**
```bash
curl http://localhost:8000/kpis
```
**Response** — `200 OK`
```json
{
  "total_revenue_brl": 15843553.24,
  "on_time_pct": 91.89,
  "avg_review_score": 4.11,
  "repeat_purchase_rate_pct": 3.05
}
```

| Field | Definition |
|---|---|
| `total_revenue_brl` | Σ (item price + freight), all orders, exact decimal |
| `on_time_pct` | delivered orders arriving on/before estimate ÷ delivered |
| `avg_review_score` | mean star rating over reviewed orders (1–5) |
| `repeat_purchase_rate_pct` | customers (person-level `customer_unique_id`) with 2+ orders ÷ all customers |

---

## GET /kpis/by-state

On-time % and average delivery days for every customer state, worst first —
the Operations Manager's "where is delivery worst" question as JSON.

**Request**
```bash
curl http://localhost:8000/kpis/by-state
```
**Response** — `200 OK` (27 states; first entries shown)
```json
[
  {"customer_state": "AL", "delivered_orders": 397,  "on_time_pct": 76.1, "avg_delivery_days": 24.5},
  {"customer_state": "MA", "delivered_orders": 717,  "on_time_pct": 80.3, "avg_delivery_days": 21.6},
  {"customer_state": "PI", "delivered_orders": 476,  "on_time_pct": 84.0, "avg_delivery_days": 19.5},
  {"customer_state": "CE", "delivered_orders": 1279, "on_time_pct": 84.7, "avg_delivery_days": 21.3}
]
```
States are sorted by `on_time_pct` ascending (worst at the top).

---

## POST /predict

Scores the probability that an order arrives **after** its promised date.

Send **only facts known at checkout** — timestamps, states, category, price,
freight, package dimensions. The service derives purchase month/hour/
day-of-week and the promised lead time exactly as training did (see
`ml/model_card.md`).

**Risk bands:** `Low` < 0.30 · `Medium` 0.30–0.60 · `High` > 0.60

**Request**
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "purchase_ts": "2017-11-20T14:00:00",
    "estimated_delivery_ts": "2017-12-15T00:00:00",
    "customer_state": "AL",
    "seller_state": "SP",
    "product_category_en": "furniture_decor",
    "price": 899.9,
    "freight_value": 120.0,
    "product_weight_g": 30000,
    "length_cm": 120,
    "height_cm": 60,
    "width_cm": 90
  }'
```

**Response** — `200 OK`
```json
{
  "late_probability": 0.2387,
  "risk_band": "Low",
  "model": "random_forest"
}
```

### Field reference (request)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `purchase_ts` | ISO datetime | yes | when the customer ordered |
| `estimated_delivery_ts` | ISO datetime | yes | delivery date promised at checkout (must be ≥ `purchase_ts`) |
| `customer_state` | string | yes | destination state, e.g. `"SP"` |
| `seller_state` | string | yes | origin state, e.g. `"RJ"` |
| `product_category_en` | string | yes | English category name |
| `price` | number > 0 | yes | item price, BRL |
| `freight_value` | number ≥ 0 | yes | shipping cost, BRL |
| `product_weight_g` | number ≥ 0 | no | product weight in grams |
| `length_cm`, `height_cm`, `width_cm` | number ≥ 0 | no | package dimensions |

### Reading the output honestly

- `late_probability` comes from a RandomForest trained on 2016–2018 data
  (ROC-AUC 0.81, 7.9% late base rate). On the test set, the ≥0.30 cut flags
  1.6% of orders with **61.5% precision** — a high-precision alert, not a
  safety net (see `ml/model_card.md` → *Band quality*).
- Bands fire rarely because most orders *are* on time; a `Low` result is the
  expected answer for typical orders, not a broken model.

### Errors

**`422 Unprocessable Entity`** — validation failed:
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "purchase_ts"],
      "msg": "Field required",
      "input": {"price": 50}
    }
  ]
}
```
Also returned when `estimated_delivery_ts < purchase_ts`:
```json
{"detail": "estimated_delivery_ts must be on or after purchase_ts"}
```

---

## Typical workflow

```bash
curl http://localhost:8000/health                 # 1. is it up?
curl http://localhost:8000/kpis                   # 2. headline numbers
curl http://localhost:8000/kpis/by-state          # 3. where delivery breaks
curl -X POST .../predict -d '{...}'               # 4. score a specific order
```
