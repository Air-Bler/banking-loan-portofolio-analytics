"""Shared fakes for the LLM assistant tests: no Databricks, no Azure OpenAI, no network.

Import these with `from llm_helpers import ...`, never from `conftest`: there is more than one
conftest.py under tests/, so `from conftest import ...` picks whichever one pytest loaded last.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from loan_analytics.llm.queries import ApprovedQuery

PRODUCTS = [
    {"product_code": "PL-STD", "product_name": "Personal Loan", "product_family": "Consumer", "min_amount": 1000.0,
     "max_amount": 30000.0, "min_term_months": 12, "max_term_months": 84, "base_rate": 0.089},
    {"product_code": "PL-GRN", "product_name": "Green Home Upgrade Loan", "product_family": "Consumer", "min_amount": 3000.0,
     "max_amount": 40000.0, "min_term_months": 24, "max_term_months": 96, "base_rate": 0.069},
    {"product_code": "AUT-NEW", "product_name": "New Car Loan", "product_family": "Auto", "min_amount": 8000.0,
     "max_amount": 60000.0, "min_term_months": 24, "max_term_months": 84, "base_rate": 0.059},
    {"product_code": "MTG-FIX", "product_name": "Fixed-rate Mortgage", "product_family": "Mortgage", "min_amount": 50000.0,
     "max_amount": 350000.0, "min_term_months": 120, "max_term_months": 360, "base_rate": 0.039},
    {"product_code": "SME-WCL", "product_name": "SME Working Capital", "product_family": "Business", "min_amount": 10000.0,
     "max_amount": 150000.0, "min_term_months": 12, "max_term_months": 60, "base_rate": 0.075},
]
BRANCHES = [
    {"branch_code": "BR001", "branch_name": "Syntagma", "city": "Athens", "region": "Attica", "opened_date": "1998-03-02"},
    {"branch_code": "BR003", "branch_name": "Kifisia", "city": "Athens", "region": "Attica", "opened_date": "2005-09-19"},
    {"branch_code": "BR005", "branch_name": "Aristotelous", "city": "Thessaloniki", "region": "Central Macedonia", "opened_date": "1999-04-12"},
]
RISK_BANDS = [
    {"risk_band_code": c, "risk_band_name": n, "min_score": lo, "max_score": hi, "sort_order": i}
    for i, (c, n, lo, hi) in enumerate([("A", "Excellent (800-850)", 800, 850), ("B", "Very good (740-799)", 740, 799),
                                         ("C", "Good (670-739)", 670, 739), ("D", "Fair (580-669)", 580, 669),
                                         ("E", "Poor (300-579)", 300, 579), ("U", "Unknown (score missing or out of range)", None, None)], 1)
]


class FakeGoldRepository:
    """Returns canned rows by ApprovedQuery.name (exact, or the part before the first ':'); records every call."""

    def __init__(self):
        self.calls: list[ApprovedQuery] = []
        self.responses: dict[str, Any] = {
            "metadata:products": PRODUCTS, "metadata:branches": BRANCHES, "metadata:risk_bands": RISK_BANDS,
        }

    def set(self, name: str, response: Any) -> FakeGoldRepository:
        """response: list of rows, an Exception to raise, or a callable(query) -> rows."""
        self.responses[name] = response
        return self

    def execute(self, query: ApprovedQuery) -> list[dict[str, Any]]:
        self.calls.append(query)
        resp = self.responses.get(query.name, self.responses.get(query.name.split(":")[0]))
        if isinstance(resp, Exception):
            raise resp
        if callable(resp):
            return resp(query)
        return [dict(r) for r in (resp or [])]

    @property
    def data_calls(self) -> list[ApprovedQuery]:
        """Calls other than the metadata look-ups used to validate filter values."""
        return [c for c in self.calls if not c.name.startswith("metadata:")]


class ScriptedChatModel:
    """A deterministic stand-in for a tool-calling chat model: replays a script of AIMessages (or exceptions)."""

    def __init__(self, script: list[AIMessage | Exception]):
        self._script = list(script)
        self.bound_tools: list[str] = []
        self.invocations: list[list[Any]] = []

    def bind_tools(self, tools, **_):
        self.bound_tools = [t.name for t in tools]
        return self

    def invoke(self, messages, **_):
        self.invocations.append(list(messages))
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])
