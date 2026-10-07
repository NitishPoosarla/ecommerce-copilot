"""STEP 7 — Run the 9 acceptance questions through the copilot and print
question -> route -> answer -> citations -> audit flags.

Run: ./venv/Scripts/python.exe -m copilot.test_questions
"""

import re
import sys

from copilot.copilot import ask

# A "refuse" question must actually say the information is missing.
# Tolerate straight and unicode apostrophes (don't / don’t).
REFUSAL_RE = re.compile(
    r"do(es)?n['’]?t have|do not have|no evidence|cannot answer|"
    r"can['’]?t answer|not available in|no such (data|information|table)|"
    r"does not (exist|contain|include)|isn['’]?t (available|tracked)|"
    r"not tracked|no marketing-spend",
    re.I,
)

QUESTIONS = [
    ("numeric",  "What was total revenue?"),
    ("numeric",  "Which state has the worst on-time delivery?"),
    ("numeric",  "Average review score of late vs on-time orders?"),
    ("document", "How do we define on-time delivery?"),
    ("document", "What are the three recommendations?"),
    ("document", "How does the late-delivery model work and what are its limitations?"),
    ("mixed",    "Why are customers unhappy - summarize the main evidence?"),
    ("document", "What is our escalation policy for very late orders?"),
    # Refusal: 2019 is outside the 2016-2018 warehouse, and no table
    # tracks marketing spend. The copilot must NOT invent a budget.
    ("refuse",   "What was our marketing budget for Q3 2019?"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    problems = 0
    for i, (expected, q) in enumerate(QUESTIONS, 1):
        print("=" * 100)
        print(f"Q{i} [{expected}] {q}")
        res = ask(q, verbose=False)
        print(f"route={res['route']}  blocks={len(res['evidence'])}")
        print("ANSWER:", " ".join(res["answer"].split()))
        for c in res["citations"]:
            preview = " ".join(c["content"].split())[:110]
            print(f"   [{c['eid']}] {c['label']} | {preview}...")
        flags = []
        if res["route"] != expected:
            flags.append(f"route-mismatch (expected {expected})")
        if expected == "refuse" and not REFUSAL_RE.search(res["answer"]):
            flags.append("NOT-A-REFUSAL (never says the info is missing)")
        if not res["citations"]:
            flags.append("NO-CITATIONS")
        if res["unsupported_numbers"]:
            flags.append(f"INVENTED-NUMBERS {res['unsupported_numbers']}")
        if res.get("unknown_citations"):
            flags.append(f"BOGUS-CITATIONS {res['unknown_citations']}")
        if res.get("missing_denominator"):
            flags.append(f"MISSING-DENOMINATOR {res['missing_denominator']}")
        if flags:
            problems += 1
            print("   FLAGS:", "; ".join(flags))
        else:
            print("   OK")
    print("=" * 100)
    print(f"questions with flags: {problems}/{len(QUESTIONS)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
