from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.errors import DataUnavailable
from api.queries import GoldRepository


class FakeRepository(GoldRepository):
    """Small, deterministic Gold dataset for API tests."""

    as_of_date = "2025-12-31"
    source = "fake.gold"

    _metrics = [
        {"name": "approval_rate", "label": "Approval rate", "unit": "ratio",
         "definition": "approved / (approved + rejected)"},
        {"name": "applications", "label": "Applications", "unit": "count",
         "definition": "Number of applications"},
        {"name": "outstanding_balance", "label": "Outstanding balance", "unit": "EUR",
         "definition": "Outstanding loan balance"},
        {"name": "dti_band_share", "label": "DTI band share", "unit": "ratio",
         "definition": "Share of applications in a DTI band"},
    ]

    def __init__(self, fail: bool = False):
        self._fail = fail

    def _raise_if_fail(self) -> None:
        if self._fail:
            raise DataUnavailable("simulated test outage")

    def metric_catalogue(self) -> list[dict[str, Any]]:
        self._raise_if_fail()
        return deepcopy(self._metrics)

    def query_metric(
        self,
        metric: str,
        group_by: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._raise_if_fail()
        rows = {
            "approval_rate": [
                {"group": "BR001", "value": 0.75, "numerator": 15, "denominator": 20},
                {"group": "BR002", "value": 0.60, "numerator": 12, "denominator": 20},
            ],
            "applications": [
                {"group": "BR001", "value": 20},
                {"group": "BR002", "value": 20},
            ],
            "outstanding_balance": [
                {"group": "BR001", "value": 125000.0},
                {"group": "BR002", "value": 98000.0},
            ],
            "dti_band_share": [
                {"group": "below_20", "value": 0.30},
                {"group": "20_35", "value": 0.40},
                {"group": "35_50", "value": 0.20},
                {"group": "above_50", "value": 0.10},
            ],
        }
        return {
            "metric": next(
                (item for item in self._metrics if item["name"] == metric),
                {"name": metric},
            ),
            "group_by": group_by,
            "filters": filters or {},
            "rows": deepcopy(rows.get(metric, []))[:limit],
            "as_of_date": self.as_of_date,
            "source": self.source,
        }

    def branch_summary(self, branch_code: str) -> dict[str, Any] | None:
        self._raise_if_fail()
        summaries = {
            "BR001": {"branch_code": "BR001", "branch_name": "Athens Central",
                      "applications": 20, "approval_rate": 0.75,
                      "outstanding_balance": 125000.0},
            "BR002": {"branch_code": "BR002", "branch_name": "Thessaloniki",
                      "applications": 20, "approval_rate": 0.60,
                      "outstanding_balance": 98000.0},
        }
        result = summaries.get(branch_code)
        if result is None:
            return None
        return {**result, "as_of_date": self.as_of_date, "source": self.source}

    def get_exceptions(
        self,
        rule_id: str | None = None,
        action: str | None = None,
        branch_code: str | None = None,
        batch_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        self._raise_if_fail()
        items = [
            {"exception_key": 1, "rule_id": "DQ001", "action": "review",
             "description": "Missing requested amount", "branch_code": "BR001",
             "source_batch_id": "batch-001"},
            {"exception_key": 2, "rule_id": "DQ002", "action": "reject",
             "description": "Invalid term", "branch_code": "BR002",
             "source_batch_id": "batch-001"},
        ]
        filters = {
            "rule_id": rule_id, "action": action, "branch_code": branch_code,
            "source_batch_id": batch_id,
        }
        filtered = [
            item for item in items
            if all(value is None or item[key] == value for key, value in filters.items())
        ]
        return {
            "items": deepcopy(filtered[offset : offset + limit]),
            "total": len(filtered), "limit": limit, "offset": offset,
            "as_of_date": self.as_of_date, "source": self.source,
        }

    def connected_exposure(self, application_id: str) -> dict[str, Any] | None:
        self._raise_if_fail()
        exposures = {
            "APP-001": {
                "application_id": "APP-001",
                "nodes": [{"id": "APP-001", "type": "application", "label": "Application 001"}],
                "edges": [{"source": "APP-001", "target": "CUS-001",
                           "relationship": "belongs_to"}],
            }
        }
        result = exposures.get(application_id)
        if result is None:
            return None
        return {**result, "as_of_date": self.as_of_date, "source": self.source}

    def refresh_info(self) -> dict[str, Any]:
        self._raise_if_fail()
        return {
            "as_of_date": self.as_of_date,
            "refreshed_at": "2026-01-01T08:00:00Z",
            "source": self.source,
        }