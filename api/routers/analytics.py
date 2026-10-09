from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["analytics"])


class AnalyticsQuery(BaseModel):
    metric: str = Field(min_length=1)
    group_by: Literal["branch", "product", "month", "year"] | None = None
    filters: dict[str, Any] | None = None
    limit: int = Field(default=100, ge=1, le=1000)


@router.post("/analytics/query")
def query_analytics(
    request: AnalyticsQuery,
    repository: GoldRepository = Depends(get_repository),
) -> dict[str, Any]:
    return repository.query_metric(
        request.metric,
        group_by=request.group_by,
        filters=request.filters,
        limit=request.limit,
    )


@router.get("/metadata/metrics")
def metric_catalogue(
    repository: GoldRepository = Depends(get_repository),
) -> dict[str, Any]:
    metrics = repository.metric_catalogue()
    return {"metrics": metrics}
