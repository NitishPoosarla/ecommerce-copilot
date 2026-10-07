"""STEP 5 — The RAG Business Copilot engine.

Flow for one question:
  question ──► ROUTER (keywords decide numeric / document / mixed)
               ├─ numeric  ──► canned SQL against the warehouse
               ├─ document ──► pgvector top-4 similarity search
               └─ mixed    ──► both
                    │
                    ▼
        evidence pack (SQL rows +/or doc chunks, labeled E1..En)
                    │
                    ▼
        Groq LLM (openai/gpt-oss-120b) writes the answer,
        told to cite [E#] and NEVER invent numbers
                    │
                    ▼
        parser: extract citations, drop unknown [E#] refs,
        audit every number in the answer against the evidence

Run directly for a smoke test:  python -m copilot.copilot "What was total revenue?"
"""

import os
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from copilot.chunk_docs import build_corpus  # noqa: F401  (keeps package import path warm)
from copilot.db import get_engine

ROOT = Path(__file__).resolve().parent.parent

GROQ_MODEL = "openai/gpt-oss-120b"   # listed Production on console.groq.com/docs/models
TOP_K = 4                            # document chunks retrieved per question


# --------------------------------------------------------------------------
# 0. Credentials — tolerate .env, Credentials.env, or a bare `gsk_...` line
# --------------------------------------------------------------------------
def load_groq_key() -> str:
    if os.environ.get("GROQ_API_KEY", "").strip():
        return os.environ["GROQ_API_KEY"].strip()
    for name in (".env", "Credentials.env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.search(r"(gsk_[A-Za-z0-9]+)", line)
            if m:
                return m.group(1)
    raise RuntimeError("GROQ_API_KEY not found in .env or Credentials.env")


# --------------------------------------------------------------------------
# 1. SQL evidence: canned, tested queries (the LLM never writes SQL)
# --------------------------------------------------------------------------
SQL_INTENTS = [
    {
        "name": "total revenue",
        "pattern": r"revenue|how much (money|sales)|total sales|sales total",
        "sql": """
            SELECT SUM((price + freight_value)::numeric) AS total_revenue_brl,
                   COUNT(DISTINCT order_id)              AS orders
            FROM fact_orders
        """,
    },
    {
        "name": "on-time delivery by state (worst first)",
        "pattern": r"\bstate|province|worst state|best state",
        "sql": """
            SELECT c.customer_state,
                   COUNT(DISTINCT f.order_id) AS delivered_orders,
                   ROUND(100.0 * COUNT(DISTINCT f.order_id) FILTER (WHERE f.is_on_time)
                         / COUNT(DISTINCT f.order_id), 1) AS ontime_pct,
                   ROUND(AVG(f.delivery_days)::numeric, 1) AS avg_delivery_days
            FROM fact_orders f
            JOIN dim_customers c ON c.customer_id = f.customer_id
            WHERE f.is_delivered
            GROUP BY 1
            HAVING COUNT(DISTINCT f.order_id) >= 50
            ORDER BY ontime_pct ASC
            LIMIT 10
        """,
    },
    {
        "name": "review score of late vs on-time orders",
        "pattern": r"late.*review|review.*late|late vs|vs on-?time|on-?time vs|unhappy|dissatisf|complain|bad review|poor rating",
        "sql": [
            """
            SELECT CASE WHEN is_on_time THEN 'on-time' ELSE 'late' END AS delivery,
                   ROUND(AVG(review_score)::numeric, 2) AS avg_review_score,
                   COUNT(*) FILTER (WHERE review_score = 1) AS one_star_orders,
                   COUNT(*) AS reviewed_orders
            FROM (
                SELECT DISTINCT ON (order_id) order_id, is_on_time, review_score
                FROM fact_orders
                WHERE is_delivered AND review_score IS NOT NULL
                ORDER BY order_id
            ) t
            GROUP BY 1
            ORDER BY 1
        """,
            """
            SELECT COUNT(*) FILTER (WHERE review_score = 1)
                       AS one_star_ALL_reviewed_orders_incl_undelivered,
                   COUNT(*) FILTER (WHERE is_delivered AND review_score = 1)
                       AS one_star_DELIVERED_orders_only,
                   COUNT(*) FILTER (WHERE NOT is_delivered AND review_score = 1)
                       AS one_star_undelivered_orders,
                   ROUND(100.0 * COUNT(*) FILTER (
                             WHERE is_delivered AND is_on_time = false
                                   AND review_score = 1)
                         / NULLIF(COUNT(*) FILTER (WHERE review_score = 1), 0), 1)
                       AS late_one_star_pct_of_ALL_one_star_incl_undelivered,
                   ROUND(100.0 * COUNT(*) FILTER (
                             WHERE is_delivered AND is_on_time = false
                                   AND review_score = 1)
                         / NULLIF(COUNT(*) FILTER (
                             WHERE is_delivered AND review_score = 1), 0), 1)
                       AS late_one_star_pct_of_DELIVERED_one_star_only
            FROM (
                SELECT DISTINCT ON (order_id)
                       order_id, is_delivered, is_on_time, review_score
                FROM fact_orders
                WHERE review_score IS NOT NULL
                ORDER BY order_id
            ) t
        """,
        ],
        "extra_name": "one-star shares with explicit denominators",
    },
    {
        "name": "repeat purchase rate and revenue split",
        "pattern": r"repeat|second purchase|loyal|one-time|onetime|come back|returning customer",
        "sql": """
            SELECT COUNT(*) AS total_customers,
                   COUNT(*) FILTER (WHERE order_count >= 2) AS repeat_customers,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE order_count >= 2) / COUNT(*), 2)
                       AS repeat_pct
            FROM (
                SELECT c.customer_unique_id, COUNT(DISTINCT f.order_id) AS order_count
                FROM dim_customers c
                JOIN fact_orders f ON f.customer_id = c.customer_id
                GROUP BY 1
            ) t
        """,
    },
    {
        "name": "revenue by product category (top 10)",
        "pattern": r"categor|product|segment|which product",
        "sql": """
            SELECT p.product_category_en AS category,
                   SUM((f.price + f.freight_value)::numeric) AS revenue_brl
            FROM fact_orders f
            JOIN dim_products p ON p.product_id = f.product_id
            GROUP BY 1
            ORDER BY revenue_brl DESC
            LIMIT 10
        """,
    },
]

FALLBACK_SQL = {
    "name": "headline KPIs (fallback)",
    "sql": """
        SELECT SUM((price + freight_value)::numeric) AS revenue_brl,
               ROUND(100.0 * COUNT(*) FILTER (WHERE is_on_time) / COUNT(*), 2)
                   AS ontime_pct_delivered,
               ROUND(AVG(delivery_days)::numeric, 1) AS avg_delivery_days,
               ROUND(AVG(review_score)::numeric, 2) AS avg_review_score
        FROM fact_orders
        WHERE is_delivered
    """,
}


# --------------------------------------------------------------------------
# 2. Router — deterministic keyword rules, no LLM call
# --------------------------------------------------------------------------
# Absolute document patterns win over numeric words: a question that asks
# for a DEFINITION / POLICY / MODEL EXPLANATION is a document question even
# if it contains words like "delivery" (which look numeric).
DOC_ABSOLUTE = [
    (r"\bdefin(e|ed|ition|ing)\b", "definition"),
    (r"recommend", "recommendation"),
    (r"escalation|policy|policies|handbook|handbook|process|rules", "policy"),
    (r"\bmodel\b.*\b(how|work|limit|feature|metric|train)|"
     r"\b(how|what).*(\bmodel\b)|limitations\b", "model"),
    (r"how do we|how does (the|our)|according to", "process"),
]
NUMERIC_WORDS = re.compile(
    r"\brevenue\b|\bhow much\b|\btotal\b|\b%\b|percent|\bpercent\b|on-?time|"
    r"\bscore|\baverage\b|\bavg\b|\bstate|\bcategor|\brepeat\b|\bworst\b|"
    r"\bbest\b|\btop\b|\bkpi|\bsales\b|\bmoney\b|\bdelivery days\b|"
    r"\bwhich state\b|\bpeak\b|\bmonth\b|\bhow many\b|\brate\b",
    re.I,
)
DOC_WORDS = re.compile(
    r"\bdefin|\brecommend|\bpolic|\bescalation|\bmodel\b|\blimitation|"
    r"\bhow do we\b|\bhow does\b|\bexplain\b|\bdocument|\bhandbook\b|"
    r"\bwhat are the\b|\bprocess\b",
    re.I,
)


def route(question: str) -> str:
    """Return 'numeric' | 'document' | 'mixed'."""
    q = question.lower()
    doc_absolute = any(re.search(p, q) for p, _ in DOC_ABSOLUTE)
    if doc_absolute:
        return "document"
    num = bool(NUMERIC_WORDS.search(q))
    doc = bool(DOC_WORDS.search(q))
    if num and doc:
        return "mixed"
    if num:
        return "numeric"
    if doc:
        return "document"
    return "mixed"  # unknown -> gather both, the LLM can only cite what we give it


def pick_sql_intents(question: str) -> list[dict]:
    q = question.lower()
    hits = [i for i in SQL_INTENTS if re.search(i["pattern"], q)]
    if not hits:
        hits = [FALLBACK_SQL]
    return hits


# --------------------------------------------------------------------------
# 3. Evidence runners
# --------------------------------------------------------------------------
def run_sql(question: str) -> list[dict]:
    """Run the matched canned queries; return evidence entries."""
    entries = []
    with get_engine().connect() as conn:
        for intent in pick_sql_intents(question):
            sqls = intent["sql"] if isinstance(intent["sql"], list) else [intent["sql"]]
            for idx, sql in enumerate(sqls):
                name = intent["name"] if idx == 0 else intent.get(
                    "extra_name", intent["name"])
                rows = conn.execute(text(sql)).mappings().all()
                preview_rows = [dict(r) for r in rows[:10]]
                entries.append({
                    "kind": "sql",
                    "label": f"SQL: {name}",
                    "content": _format_sql(name, preview_rows),
                    "truncated": len(rows) > 10,
                })
    return entries


def _format_sql(name: str, rows: list[dict]) -> str:
    if not rows:
        return f"{name}: no rows returned"
    lines = [f"Result of query '{name}':"]
    for r in rows:
        lines.append("  " + ", ".join(f"{k}={v}" for k, v in r.items()))
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def search_docs(question: str, top_k: int = TOP_K) -> list[dict]:
    """pgvector top-k cosine search over rag_documents."""
    vec = _embedder().encode([question], normalize_embeddings=True)[0]
    vec_str = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, title, content,
                       1 - (embedding <=> CAST(:v AS vector)) AS similarity
                FROM rag_documents
                ORDER BY embedding <=> CAST(:v AS vector)
                LIMIT :k
            """),
            {"v": vec_str, "k": top_k},
        ).mappings().all()
    return [
        {
            "kind": "doc",
            "label": f"DOC: {r['title']}",
            "content": r["content"],
            "similarity": round(float(r["similarity"]), 3),
            "chunk_id": r["id"],
        }
        for r in rows
    ]


# --------------------------------------------------------------------------
# 4. Groq — the only thing that writes prose
# --------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the business intelligence copilot for a Brazilian \
e-commerce marketplace (Olist data, 2016-2018, currency BRL).

You will receive the user's question and an EVIDENCE PACK of numbered blocks \
[E1], [E2], ... Each block is either SQL query results or a document chunk.

Strict rules:
1. Use ONLY numbers that appear verbatim in the evidence blocks. Do NOT \
invent, estimate, or compute new numbers (no arithmetic, no rounding, no \
unit conversions). If the needed number is absent, write that you don't have \
it in the retrieved evidence.
2. Cite every factual sentence with the evidence block(s) it came from, \
using EXACTLY plain ASCII square brackets like [E1] or [E2][E5] - never \
unicode/fancy brackets, parentheses, or superscripts. At least one [E#] \
tag MUST appear in your ANSWER section. Never cite a block that was not \
provided.
3. If a block's title says FICTIONAL (the operations handbook), present it \
as FICTIONAL company policy and say explicitly it is fictional - never as \
a measured fact about the data.
4. PERCENTAGE DENOMINATORS: every "X% of ..." claim MUST name its \
denominator explicitly - the population AND its scope, exactly as the \
evidence names it. Example: "32.8% of ALL one-star reviews (across all \
reviewed orders, including undelivered ones)" vs "37.9% of one-star \
reviews on DELIVERED orders only". Never write a bare "% of them", \
"% of reviews", or any denominator without its scope.
5. If the evidence cannot answer the question, say so plainly and suggest \
what kind of evidence would.
6. Answer in 2-5 short sentences plus, when useful, a compact list. Plain \
text only - no markdown headers."""

GROQ_INSTRUCTIONS = """Format your reply as:

ANSWER:
<your answer, with [E#] citations inline>

CITATIONS:
<E1>
<E2>
<every block id you actually cited, one per line>

Reminder: if you cite an Operations Handbook block, state in your answer
that it is FICTIONAL company policy."""


def _evidence_pack(evidence: list[dict]) -> str:
    blocks = []
    for i, e in enumerate(evidence, start=1):
        blocks.append(f"[E{i}] {e['label']}\n{e['content']}")
    return "\n\n".join(blocks)


def call_groq(question: str, evidence: list[dict]) -> str:
    from groq import Groq

    client = Groq(api_key=load_groq_key())
    user_msg = (
        f"QUESTION: {question}\n\nEVIDENCE PACK:\n{_evidence_pack(evidence)}\n\n"
        + GROQ_INSTRUCTIONS
    )
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        max_completion_tokens=4000,  # gpt-oss reasons first; leave room
        reasoning_effort="low",
        temperature=0.1,
    )
    return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------
# 5. Parser — citations + number audit
# --------------------------------------------------------------------------
_NUM_RE = re.compile(r"\d[\d,]*\.?\d*%?")

# Models sometimes type fancy unicode brackets; citations must still parse.
_BRACKETS = str.maketrans({
    "［": "[", "【": "[", "「": "[", "〔": "[", "『": "[",
    "］": "]", "】": "]", "」": "]", "〕": "]", "』": "]",
})


def _norm_num(s: str) -> str:
    return s.replace(",", "").rstrip("%").lstrip("0") or "0"


def parse_answer(raw: str, evidence: list[dict]) -> dict:
    """Split the LLM reply, validate citations, audit numbers.

    Returns {answer, citations, unsupported_numbers, uncited, parse_ok}.
    """
    m = re.search(r"ANSWER:\s*(.*?)\s*CITATIONS:\s*(.*)$", raw, re.S | re.I)
    if m:
        answer, cit_block = m.group(1).strip(), m.group(2).strip()
    else:  # model ignored the format; treat everything as answer
        answer, cit_block = raw.strip(), ""
    answer = answer.translate(_BRACKETS)
    cit_block = cit_block.translate(_BRACKETS)

    # Citations: [E#] tags in the body, validated against provided evidence.
    # Tolerate inner spaces ("[ E1 ]") and unicode brackets (translated above).
    valid_ids = {str(i) for i in range(1, len(evidence) + 1)}
    found = re.findall(r"\[?\s*E\s*(\d+)\s*\]?", answer)
    cited = [i for i in dict.fromkeys(found) if i in valid_ids]
    bogus = sorted({i for i in found if i not in valid_ids})
    if bogus:  # hallucinated citation ids -> strip them from the display
        for b in bogus:
            answer = answer.replace(f"[E{b}] ", "[citation removed] ")
        answer = re.sub(r"\[citation removed\]\s*(?=[.,;:]|$)", "", answer)

    # Fallback: if the body has no tags but the model listed ids under
    # CITATIONS:, accept those (they reference blocks we actually supplied).
    listed = list(dict.fromkeys(re.findall(r"E(\d+)", cit_block)))
    if not cited:
        cited = [i for i in listed if i in valid_ids]
    bogus_listed = sorted({i for i in listed if i not in valid_ids})

    citations = [
        {**evidence[int(i) - 1], "eid": f"E{i}"} for i in cited
    ]
    # Blocks the model listed under CITATIONS but never used in the body
    uncited = [i for i in listed
               if i in valid_ids and i not in cited]

    # Number audit: every number in the answer must exist in the evidence
    # (strip [E#] citation tags - including spaced/bracketless ones - so "E1"
    #  isn't audited as the number 1, and strip markdown list enumerators
    #  like "1. " which are not data)
    answer_no_cit = re.sub(r"\[?\s*E\s*\d+\s*\]?", "", answer)
    answer_no_cit = re.sub(r"(?m)^\s*\d+\.\s*", "", answer_no_cit)
    answer_no_cit = re.sub(r"(?<=\s)\d+\.(?=\s)", "", answer_no_cit)
    evidence_text = " ".join(e["content"] for e in evidence)
    evidence_nums = {_norm_num(n) for n in _NUM_RE.findall(evidence_text)}
    unsupported = sorted({
        n for n in _NUM_RE.findall(answer_no_cit)
        if _norm_num(n) not in evidence_nums
    })

    # Denominator audit: every "X% of ..." claim must name a concrete,
    # scoped population (>= 2 words, no bare pronoun like "them"/"those")
    missing_denominator: list[str] = []
    for m_pct in re.finditer(r"\d[\d,.]*\s*%\s*of\b", answer_no_cit):
        tail = answer_no_cit[m_pct.end(): m_pct.end() + 80]
        tail = re.split(r"[.;:!?\n]", tail, maxsplit=1)[0]
        nouns = re.findall(r"[A-Za-z][A-Za-z'-]+", tail)
        weak = re.match(r"\s*(them|their|it|those|these|the same|this)\b",
                        tail, re.I)
        if len(nouns) < 2 or weak:
            snippet = (answer_no_cit[m_pct.start(): m_pct.end()]
                       + " " + tail.strip())
            missing_denominator.append(" ".join(snippet.split())[:100])

    return {
        "answer": answer,
        "citations": citations,
        "unsupported_numbers": unsupported,
        "missing_denominator": missing_denominator,
        "uncited_blocks": uncited,
        "unknown_citations": bogus + bogus_listed,
        "parse_ok": bool(cited),
    }


# --------------------------------------------------------------------------
# 6. Public entry point
# --------------------------------------------------------------------------
def ask(question: str, verbose: bool = True) -> dict:
    """Route -> retrieve -> Groq -> parse. Returns the full result dict."""
    r = route(question)
    evidence: list[dict] = []
    if r in ("numeric", "mixed"):
        evidence += run_sql(question)
    if r in ("document", "mixed"):
        evidence += search_docs(question)

    raw = call_groq(question, evidence)
    parsed = parse_answer(raw, evidence)
    result = {
        "question": question,
        "route": r,
        "evidence": evidence,
        **parsed,
    }
    if verbose:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            # Windows console (cp1252) can't print some LLM unicode (e.g.
            # U+202F narrow space) -> replace instead of crashing
            sys.stdout.reconfigure(errors="replace")
        print(f"route={r}  evidence_blocks={len(evidence)}")
        print(f"answer:\n{result['answer']}\n")
        for c in result["citations"]:
            preview = c["content"][:90].replace("\n", " ")
            print(f"  [{c['eid']}] {c['label']} | {preview}...")
        if result["unsupported_numbers"]:
            print(f"  !! numbers not found in evidence: "
                  f"{result['unsupported_numbers']}")
        if result["missing_denominator"]:
            print(f"  !! '%of' claims without explicit denominator: "
                  f"{result['missing_denominator']}")
        if not result["citations"]:
            print("  !! no citations parsed")
    return result


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What was total revenue?"
    ask(q)
