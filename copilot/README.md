# RAG Business Copilot — How It Works

**Phase 5 of the E-commerce Intelligence project.**
Ask a question in plain English; get an answer built only from *our* data and
*our* documents, with the source shown underneath.

## The big idea in plain English

A normal chatbot guesses. This copilot is not allowed to guess:

1. **Route** — a tiny keyword router reads your question and decides where the
   answer can possibly live:
   - **numeric** questions (revenue, delivery %, scores, states, categories)
     → run a *pre-tested SQL query* against the warehouse. The LLM never
     writes SQL and never does math — it only explains the rows we fetched.
   - **document** questions (definitions, policies, recommendations, model
     explanations) → pgvector top-4 similarity search over our `docs/` corpus.
   - **mixed** questions → do both and hand the LLM everything.
2. **Retrieve evidence** — SQL result rows and/or document chunks, numbered
   `[E1] [E2] …`. If nothing is found, the copilot says so instead of guessing.
3. **Write** — Groq LLM (**`openai/gpt-oss-120b`**, listed as a *Production*
   model on [console.groq.com/docs/models](https://console.groq.com/docs/models))
   gets the question + evidence pack with hard rules:
   - every number must appear **verbatim** in the evidence (no arithmetic),
   - every factual sentence needs an `[E#]` citation,
   - handbook answers must be labeled **fictional policy**.
4. **Audit** — a parser pulls the citations back out, throws away any `[E#]`
   that we did not actually supply, and re-checks every number in the answer
   against the evidence. Anything suspicious is surfaced in the UI as a
   warning, not silently trusted.
   Two extra guardrails: every `X% of …` claim must state its **denominator
   with scope** (e.g. "32.8% of ALL one-star reviews, including undelivered
   orders" = 3,512/10,715, vs "37.9% of one-star reviews on DELIVERED orders
   only" = 3,512/9,258 — same numerator, different denominator), and any
   `% of` claim without one is flagged in the UI.

## Architecture diagram

```
                  user question (Streamlit "Ask the Copilot" tab)
                                   │
                          ┌────────▼────────┐
                          │  ROUTER (regex) │  numeric / document / mixed
                          └────────┬────────┘
              ┌────────────────────┼────────────────────┐
              ▼ numeric            ▼ document           ▼ mixed = both
     ┌────────────────┐   ┌───────────────────┐
     │ canned SQL     │   │ embed question    │   (all-MiniLM-L6-v2,
     │ (5 tested      │   │ all-MiniLM-L6-v2 │    local, 384 dims)
     │  queries)      │   │ pgvector top-4   │
     └───────┬────────┘   │ <=> rag_documents│
             │            └────────┬──────────┘
             └──────────┬──────────┘
                        ▼
             evidence pack [E1][E2]…
        (SQL rows +/or doc chunk titles+text)
                        │
                        ▼
        ┌───────────────────────────────────┐
        │ Groq  openai/gpt-oss-120b         │
        │ rules: only evidence numbers,     │
        │ cite [E#], say "fictional" when    │
        │ the handbook is cited             │
        └───────────────┬───────────────────┘
                        ▼
             parser + number audit
        (drop bogus [E#], flag any number
         not present in the evidence)
                        │
                        ▼
        answer + citations in small text
             under it (st.caption)
```

## Files

| File | What it does |
|---|---|
| `docs/kpi-definitions.md` | KPI definitions extracted from `business_brief.md` |
| `docs/recommendations.md` | Copy of `analysis/recommendations.md` |
| `docs/model-card.md` | Copy of `ml/model_card.md` |
| `docs/operations-handbook.md` | **Fictional** delivery/review/escalation policy |
| `copilot/chunk_docs.py` | Splits `docs/*.md` into ~500-char titled chunks |
| `copilot/ingest.py` | Embeds chunks → table `rag_documents` (vector(384)) |
| `copilot/db.py` | Shared Postgres connection (psycopg2 + SSL) |
| `copilot/copilot.py` | The engine: router → SQL/pgvector → Groq → audit |
| `copilot/test_questions.py` | The 8 acceptance questions + flag checks |
| `app.py` (tab 5) | Streamlit chat UI with citations under each answer |

## Run it

```bash
# rebuild the vector index (safe to re-run; drops + recreates the table)
./venv/Scripts/python.exe -m copilot.ingest

# one question from the terminal
./venv/Scripts/python.exe -m copilot.copilot "What was total revenue?"

# all 8 acceptance questions (exit 0 = no flags)
./venv/Scripts/python.exe -m copilot.test_questions

# the dashboard + chat tab
./venv/Scripts/python.exe -m streamlit run app.py
```

Credentials needed in `.env` / `Credentials.env` (both git-ignored):
`DATABASE_URL` and `GROQ_API_KEY` (a bare `gsk_…` line also works).

## Design notes / honest limitations

- **Routing is keyword-based, not an LLM call**: deterministic, free, and
  auditable. A rephrased question can route to the wrong bucket — the answer
  still can only cite real evidence, so it degrades to "here's what I found"
  rather than to a hallucination.
- **The LLM never writes SQL.** Five canned queries cover the brief's KPI
  questions; unknown numeric questions fall back to headline KPIs.
- **The number audit is a safety net, not a proof.** It catches numbers that
  appear nowhere in the evidence; it cannot catch a *misinterpretation* of a
  real number (e.g. the right number attached to the wrong entity).
- **Retrieval is top-4 by cosine similarity** — a question about a section
  that ranks 5th will miss it. Re-run `ingest.py` after editing `docs/`.
- Known noise: Streamlit's file watcher logs caught `torchvision` import
  errors to stderr on first model load. They are Streamlit-side, caught, and
  do not affect the copilot (verified: encoding and answers work).
