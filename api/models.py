"""Pydantic request and response models: the shapes in docs/contracts.md."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricName = Literal[
    "applications",
    "requested_amount",
    "approval_rate",
    "avg_decision_days",
    "high_dti_share",
    "dti_band_share",
    "delinquency_rate_30",
    "outstanding_balance",
    "manual_review_rate",
]
GroupBy = Literal["branch", "product", "month", "year"]

BRANCH_CODE = r"^(BR\d{3}|UNKNOWN)$"
APPLICATION_ID = r"^LA\d{6}$"
RULE_ID = r"^(CUS|APP|REP|TRX|MAC)-\d{2}$"


# --- /analytics/query and /metadata/metrics ---


class AnalyticsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    branch_code: str | None = Field(default=None, pattern=BRANCH_CODE)


class AnalyticsQuery(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "metric": "approval_rate",
                    "group_by": "branch",
                    "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"},
                    "limit": 100,
                }
            ]
        },
    )

    metric: MetricName
    group_by: GroupBy | None = None
    filters: AnalyticsFilters = Field(default_factory=AnalyticsFilters)
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def check_combination(self):
        # Gold has dti_band_share only for the whole portfolio
        if self.metric == "dti_band_share" and (self.group_by or self.filters.model_dump(exclude_none=True)):
            raise ValueError("dti_band_share is only available for the whole portfolio: no group_by or filters")
        if self.filters.date_from and self.filters.date_to and self.filters.date_from > self.filters.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class MetricInfo(BaseModel):
    name: str
    label: str
    unit: str
    definition: str


class MetricRow(BaseModel):
    group: str | None = None  
    value: float | None
    numerator: float | None = None
    denominator: float | None = None


class AnalyticsResponse(BaseModel):
    metric: MetricInfo
    group_by: GroupBy | None
    filters: dict[str, str]  
    rows: list[MetricRow]
    as_of_date: date
    source: str
    correlation_id: str | None = None  


class MetricCatalogue(BaseModel):
    metrics: list[MetricInfo]





class ProductKpis(BaseModel):
    product_code: str
    kpis: dict[str, float | None]


class BranchSummary(BaseModel):
    branch_code: str
    branch_name: str
    kpis: dict[str, float | None]
    by_product: list[ProductKpis]
    as_of_date: date
    source: str





class DqException(BaseModel):
    exception_key: int
    rule_id: str
    dq_dimension: str | None = None
    action: Literal["FLAG", "REJECT"]
    description: str | None = None
    entity: str
    record_key: str  
    branch_code: str | None = None
    source_batch_id: str | None = None
    detected_at: datetime | None = None


class ExceptionPage(BaseModel):
    items: list[DqException]
    total: int
    limit: int
    offset: int
    as_of_date: date
    source: str





class ExposureApplication(BaseModel):
    customer_node: str
    application_id: str
    status_code: str | None = None
    outstanding_balance: float | None = None
    is_delinquent_30: int | None = None


class ConnectedExposure(BaseModel):
    application_id: str
    members: int
    applications: list[ExposureApplication]
    total_outstanding: float
    delinquent_loans: int
    as_of_date: date
    source: str
