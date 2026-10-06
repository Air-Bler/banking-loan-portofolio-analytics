"""Deterministic first line of defence against out-of-scope requests.

The system prompt tells the model to refuse consequential actions, but refusal must not depend on the
model alone. Requests that ask the assistant to change or decide something, or to run raw SQL, are
refused before the model is called. Analytical questions never match (an action verb must be followed
by a banking object, and phrases like 'change in approval rate' are analytical).
"""
from __future__ import annotations

import re

_ACTION = re.compile(
    r"^\s*(?:please\s+|can you\s+|could you\s+|would you\s+|i want you to\s+|go ahead and\s+)?"
    r"(approve|reject|decline|deny|cancel|delete|remove|update|change|modify|edit|set|override|waive|disburse|"
    r"close|freeze|block|insert|drop|truncate|alter|write[- ]off|increase|decrease|lower|raise)\b(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL)
_OBJECT = re.compile(
    r"\b(application|applicant|customer|loan|account|interest rate|rate|limit|record|row|table|data|decision|"
    r"credit|mortgage|installment|repayment|branch|product|LA\d+|CU\d+)\b", re.IGNORECASE)
_ANALYTICAL_LEAD = re.compile(r"^\s*(changes?|increase|decrease)\s+(in|of|over)\b", re.IGNORECASE)
_SQL = re.compile(r"\b(select\s.+\sfrom|drop\s+table|delete\s+from|insert\s+into|update\s+\w+\s+set|run\s+(this\s+)?sql)\b",
                  re.IGNORECASE | re.DOTALL)

REFUSAL = ("I can only provide analytics from approved BankEasy Gold data. I can't approve, reject, change or delete "
           "applications, customers or rates, take any other business action, or run arbitrary SQL. "
           "I can answer questions about portfolio KPIs, breakdowns by product, branch, segment or risk band, "
           "and reference data.")


def detect_out_of_scope(question: str) -> str | None:
    """Return a short reason if the question asks for an action or raw SQL, otherwise None."""
    if _SQL.search(question):
        return "raw SQL request"
    m = _ACTION.match(question)
    if m and not _ANALYTICAL_LEAD.match(question) and _OBJECT.search(m.group("rest")):
        return f"consequential action request ({m.group(1).lower()})"
    return None
