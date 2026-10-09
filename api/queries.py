from __future__ import annotations

from typing import Any

from api.errors import DataUnavailable


class GoldRepository:
    """Repository seam for Gold data.

    The concrete Databricks implementation will replace the method bodies in
    Phase 3. Keeping the seam here lets routers and tests use the same
    interface without opening a warehouse connection.
    """

    def metric_catalogue(self) -> list[dict[str, Any]]:
        raise DataUnavailable("Gold metric catalogue is unavailable")

    def query_metric(
        self,
        metric: str,
        group_by: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        raise DataUnavailable(f"Gold metric {metric!r} is unavailable")

    def branch_summary(self, branch_code: str) -> dict[str, Any] | None:
        raise DataUnavailable("Gold branch summary is unavailable")

    def get_exceptions(
        self,
        rule_id: str | None = None,
        action: str | None = None,
        branch_code: str | None = None,
        batch_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        raise DataUnavailable("Gold exceptions are unavailable")

    def connected_exposure(self, application_id: str) -> dict[str, Any] | None:
        raise DataUnavailable("Gold connected exposure is unavailable")

    def refresh_info(self) -> dict[str, Any]:
        raise DataUnavailable("Gold refresh information is unavailable")


_repository = GoldRepository()


def get_repository() -> GoldRepository:
    """FastAPI dependency shared by every data router."""

    return _repository