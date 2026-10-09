from fastapi import APIRouter, Depends, Request

from api.metrics import metric_catalogue
from api.models import AnalyticsQuery, AnalyticsResponse, MetricCatalogue
from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["analytics"])


@router.post("/analytics/query", response_model=AnalyticsResponse)
def query_analytics(
    body: AnalyticsQuery, request: Request, repository: GoldRepository = Depends(get_repository)
) -> dict:
    """One KPI, optionally grouped by branch, product, month or year, and filtered."""
    filters = body.filters.model_dump(mode="json", exclude_none=True)
    result = repository.query_metric(body.metric, group_by=body.group_by, filters=filters, limit=body.limit)
    return {**result, "correlation_id": request.state.correlation_id}


@router.get("/metadata/metrics", response_model=MetricCatalogue)
def list_metrics() -> dict:
    """The 9 metrics with their definitions (a list in code: no Databricks call)."""
    return {"metrics": metric_catalogue()}
