# Operations Handbook — Meridian Marketplace (FICTIONAL)

> **FICTIONAL DOCUMENT.** "Meridian Marketplace" is a made-up company created
> for this portfolio project. The delivery process, review policy, and
> escalation rules below are invented to demonstrate how an internal
> operations handbook is used in a RAG copilot. They are NOT real Olist
> policies and NOT real business facts.

## 1. Delivery process

1. **Order placed.** The customer checks out; the system stamps a promised
   delivery date (the "estimated delivery date") based on the carrier quote.
2. **Seller fulfils.** The seller has 48 hours to hand the parcel to the
   carrier. Marketplace operators check any order still unshipped after 36
   hours.
3. **In transit.** Standard domestic transit target is 12 days door-to-door.
   Parcels routed through the Northeast corridor (AL, MA, PI, CE, SE, BA)
   get an extra 5-day tolerance because of hub capacity.
4. **Delivery.** The carrier marks the parcel delivered; the customer has
   7 days to report a non-delivery before the order auto-closes.

## 2. Review policy

- Every delivered order may leave one 1–5 star review tied to the order.
- Reviews are public and cannot be edited after 30 days.
- Support may **not** offer incentives in exchange for rating changes; the
  only permitted goodwill gesture is a voucher issued *before* the customer
  reviews, as compensation for a demonstrable service failure (late
  delivery, damaged item).
- A 1-star review triggers an automatic support ticket so a human can
  follow up within 2 business days.

## 3. Escalation rules for very late orders

| Stage | Trigger | Owner | Action |
|---|---|---|---|
| **Stage 1 — Watch** | Predicted late probability ≥ 0.30, or parcel undelivered 2 days past estimate | Automated monitor | Proactive SMS/email to the customer with status + apology |
| **Stage 2 — Intervene** | Parcel ≥ 5 days past estimate | Support agent | Personal outreach + goodwill voucher (up to 10% of order value) |
| **Stage 3 — Escalate** | Parcel ≥ 10 days past estimate, OR customer contacts support twice, OR order is to a high-risk state (AL, MA, PI, CE, SE, BA) and ≥ 5 days late | Operations manager | Carrier query opened, replacement or full refund offered, case logged in the weekly carrier review |
| **Stage 4 — Post-mortem** | Any order reaching Stage 3, or any 1-star review citing lateness | Ops lead | Root-cause note added to the carrier scorecard; recurring carriers reviewed quarterly |

**Rule of thumb:** once an order passes its promised date, the customer must
hear from us *before* they contact us. Silence is treated as a policy breach
in internal QA.

## 4. What this handbook is not

- It does not define any KPI — see `kpi-definitions.md` for that.
- It does not describe model behavior — see `model-card.md`.
- Numbers here (targets, tolerances, percentages) are fictional policy
  values, not measured facts about the Olist dataset.
