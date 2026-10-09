"""FakeRepository: the same methods as GoldRepository over a few hand-made rows in the real Gold formats.

Tests never touch Databricks. FakeRepository(fail=True) raises DataUnavailable from every data method,
as if the warehouse were down.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.errors import DataUnavailable
from api.metrics import metric_catalogue, metric_info
from api.queries import GoldRepository

AS_OF = "2025-12-31"

BRANCHES = {"BR001": "Athens Centre", "BR003": "Thessaloniki"}
GROUPS = {
    None: [None],
    "branch": ["BR001", "BR003"],
    "product": ["PL-STD", "AUT-NEW"],
    "month": ["202511", "202512"],
    "year": ["2025"],
}
DTI_BANDS = {"below_20": 0.31, "20_35": 0.42, "35_50": 0.19, "above_50": 0.08}

EXCEPTIONS = [
    {"exception_key": 1, "rule_id": "APP-03", "dq_dimension": "validity", "action": "REJECT",
     "description": "Requested amount outside the product range", "entity": "loan_applications",
     "record_key": "LA000225", "branch_code": "BR001", "source_batch_id": "batch_001",
     "detected_at": "2026-10-05T09:40:00Z"},
    {"exception_key": 2, "rule_id": "CUS-02", "dq_dimension": "completeness", "action": "FLAG",
     "description": "Missing e-mail", "entity": "customers",
     "record_key": "3f9a1c0b7d2e4a51", "branch_code": "BR003", "source_batch_id": "batch_002",
     "detected_at": "2026-10-05T09:41:00Z"},
    {"exception_key": 3, "rule_id": "TRX-04", "dq_dimension": "consistency", "action": "FLAG",
     "description": "Duplicate transaction", "entity": "transactions",
     "record_key": "TX0001234", "branch_code": "BR001", "source_batch_id": "batch_002",
     "detected_at": "2026-10-05T09:42:00Z"},
]

EXPOSURE = {
    "LA000225": [
        {"customer_node": "customer:C00101", "application_id": "LA000225", "status_code": "APPROVED",
         "outstanding_balance": 12500.0, "is_delinquent_30": 0},
        {"customer_node": "customer:C00102", "application_id": "LA000318", "status_code": "APPROVED",
         "outstanding_balance": 8300.5, "is_delinquent_30": 1},
    ],
}


class FakeRepository(GoldRepository):
    """Small, deterministic Gold dataset for API tests."""

    def __init__(self, fail: bool = False):
        self._fail = fail

    def _raise_if_fail(self) -> None:
        if self._fail:
            raise DataUnavailable("simulated test outage")

    def metric_catalogue(self) -> list[dict[str, Any]]:
        return metric_catalogue()

    def query_metric(self, metric, group_by=None, filters=None, limit=100) -> dict[str, Any]:
        self._raise_if_fail()
        if metric == "dti_band_share":
            rows = [{"group": band, "value": share} for band, share in DTI_BANDS.items()]
            source = "gold.kpi_portfolio_summary"
        else:
            rows = [{"group": g, "value": 0.6, "numerator": 60, "denominator": 100} for g in GROUPS[group_by]]
            source = "gold.kpi_portfolio_monthly"
        return {
            "metric": metric_info(metric),
            "group_by": group_by,
            "filters": filters or {},
            "rows": rows[:limit],
            "as_of_date": AS_OF,
            "source": source,
        }

    def branch_summary(self, branch_code) -> dict[str, Any] | None:
        self._raise_if_fail()
        if branch_code not in BRANCHES:
            return None
        kpis = {"applications": 412, "approval_rate": 0.592, "delinquency_rate_30": 0.031}
        return {
            "branch_code": branch_code,
            "branch_name": BRANCHES[branch_code],
            "kpis": kpis,
            "by_product": [{"product_code": "PL-STD", "kpis": kpis}],
            "as_of_date": AS_OF,
            "source": "gold.kpi_portfolio_monthly",
        }

    def get_exceptions(self, rule_id=None, action=None, branch_code=None, batch_id=None, limit=20, offset=0):
        self._raise_if_fail()
        rows = [
            r for r in EXCEPTIONS
            if (rule_id is None or r["rule_id"] == rule_id)
            and (action is None or r["action"] == action)
            and (branch_code is None or r["branch_code"] == branch_code)
            and (batch_id is None or r["source_batch_id"] == batch_id)
        ]
        return {
            "items": deepcopy(rows[offset:offset + limit]),
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "as_of_date": AS_OF,
            "source": "gold.fact_dq_exception",
        }

    def connected_exposure(self, application_id) -> dict[str, Any] | None:
        self._raise_if_fail()
        rows = EXPOSURE.get(application_id)
        if not rows:
            return None
        return {
            "application_id": application_id,
            "members": len({r["customer_node"] for r in rows}),
            "applications": deepcopy(rows),
            "total_outstanding": sum(r["outstanding_balance"] for r in rows),
            "delinquent_loans": sum(r["is_delinquent_30"] for r in rows),
            "as_of_date": AS_OF,
            "source": "gold.kg_nodes, gold.kg_edges",
        }

    def refresh_info(self) -> dict[str, Any]:
        self._raise_if_fail()
        return {"as_of_date": AS_OF, "refreshed_at": "2026-10-05T09:44:49Z", "source": "gold.refresh_info"}
