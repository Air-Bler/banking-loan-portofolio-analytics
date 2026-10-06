"""Pydantic models: typed tool inputs, tool results, the structured final response and the trace.

Tool inputs use Literal enums for every measure / dimension / flag name, so the model can only choose
from the approved vocabulary. Free text is limited to product and branch names or codes and is checked
against the Gold dimensions before it is used (and is always passed to SQL as a bound parameter).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# ---- approved vocabulary ---------------------------------------------------------------------------------
KpiMetric = Literal[
    "applications", "requested_amount", "approval_rate", "avg_decision_days",
    "dti_share_below_20", "dti_share_20_35", "dti_share_35_50", "dti_share_above_50",
    "delinquency_rate_30", "outstanding_balance", "manual_review_rate",
]
BreakdownMetric = Literal[
    "applications", "requested_amount", "decided_applications", "approved_applications", "approval_rate",
    "avg_decision_days", "manual_review_rate", "active_loans", "delinquent_loans_30", "delinquency_rate_30",
    "outstanding_balance", "open_installments", "loans", "amount_unpaid",
]
GroupBy = Literal[
    "month", "product", "product_family", "branch", "city", "region", "customer_segment", "risk_band",
    "application_status", "channel", "employment_status", "dti_band", "ageing_bucket",
]
MetadataDomain = Literal[
    "products", "branches", "customer_segments", "risk_bands", "application_statuses", "date_range",
]
DtiBand = Literal["below_20", "20_35", "35_50", "above_50", "unknown"]
AgeingBucket = Literal["Settled", "0-29", "30-59", "60-89", "90-179", "180-365", "365+"]

# a name or code typed by the user/model: letters, digits and a few punctuation marks only
SafeText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80,
                                            pattern=r"^[A-Za-z0-9 .,'&()/+_-]+$")]
MonthLabel = Annotated[str, StringConstraints(pattern=r"^(20\d\d)-(0[1-9]|1[0-2])$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortfolioKpiInput(_Strict):
    """Headline portfolio KPI from the governed summary table."""

    metric: KpiMetric = Field(description="The headline KPI to retrieve.")


class Filters(_Strict):
    """Optional filters. Every field is validated; unknown fields are rejected."""

    year: int | None = Field(default=None, ge=2000, le=2100, description="Calendar year of the application (or of the due date for repayment measures).")
    month: int | None = Field(default=None, ge=1, le=12, description="Month number 1-12; requires year.")
    month_from: MonthLabel | None = Field(default=None, description="Start month, format YYYY-MM.")
    month_to: MonthLabel | None = Field(default=None, description="End month, format YYYY-MM.")
    product: SafeText | None = Field(default=None, description="Product code (e.g. PL-STD) or product name (e.g. Personal Loan).")
    product_family: SafeText | None = Field(default=None, description="Product family, e.g. Consumer, Auto, Mortgage, Business.")
    branch: SafeText | None = Field(default=None, description="Branch code (e.g. BR001) or branch name.")
    city: SafeText | None = None
    region: SafeText | None = None
    segment_code: Literal["MASS", "AFFLUENT", "PREMIER", "SME", "UNKNOWN"] | None = None
    risk_band_code: Literal["A", "B", "C", "D", "E", "U"] | None = None
    status_code: Literal["SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "WITHDRAWN", "UNKNOWN"] | None = None
    channel: Literal["BRANCH", "ONLINE", "MOBILE", "PHONE"] | None = None
    employment_status: Literal["EMPLOYED", "SELF_EMPLOYED", "RETIRED", "UNEMPLOYED", "STUDENT", "OTHER"] | None = None
    dti_band: DtiBand | None = Field(default=None, description="Debt-to-income band at application time.")
    ageing_bucket: AgeingBucket | None = Field(default=None, description="Days-past-due bucket of repayment installments.")

    @model_validator(mode="after")
    def _time_consistency(self):
        if self.month is not None and self.year is None:
            raise ValueError("'month' requires 'year'")
        if (self.month_from or self.month_to) and (self.year is not None or self.month is not None):
            raise ValueError("use either year/month or month_from/month_to, not both")
        if self.month_from and self.month_to and self.month_from > self.month_to:
            raise ValueError("'month_from' must not be after 'month_to'")
        return self

    def applied(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class PortfolioBreakdownInput(_Strict):
    """A filtered aggregate, optionally grouped by one approved dimension."""

    metric: BreakdownMetric
    group_by: GroupBy | None = Field(default=None, description="Optional dimension to break the measure down by.")
    filters: Filters | None = None
    limit: int = Field(default=50, ge=1, le=100, description="Maximum number of groups returned.")


class MetadataInput(_Strict):
    """Reference/metadata values from the approved dimension tables."""

    domain: MetadataDomain
    city: SafeText | None = None
    region: SafeText | None = None
    product_family: SafeText | None = None


# ---- results ---------------------------------------------------------------------------------------------------
class ToolResult(BaseModel):
    """What an approved tool returns to the model (as a ToolMessage) and to the application."""

    tool: str
    status: Literal["ok", "empty", "error"]
    measure: str | None = None
    value: float | int | str | None = None
    display_value: str | None = None
    group_by: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    source: list[str] = Field(default_factory=list)
    definition: str | None = None
    limitations: list[str] = Field(default_factory=list)
    error_category: str | None = None
    message: str | None = None
    row_count: int = 0

    def for_model(self) -> str:
        return self.model_dump_json(exclude_none=True, exclude_defaults=False)


class EvidenceItem(BaseModel):
    label: str
    value: str | int | float
    source: str


class AnalyticsResponse(BaseModel):
    """The structured answer returned to the caller."""

    answer: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    source: list[str] = Field(default_factory=list)
    measure: str | None = None
    limitations: list[str] = Field(default_factory=list)


class TraceEntry(BaseModel):
    """Deterministic, application-side record of one step of the execution path."""

    step: str                                   # e.g. "scope_guard", "model_call", "tool_call"
    tool: str | None = None
    tool_call_id: str | None = None
    raw_args: dict[str, Any] | None = None
    validated_args: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list)
    status: str | None = None                   # ok | empty | error | refused
    error_category: str | None = None
    row_count: int | None = None
    duration_ms: float | None = None
