"""The assistant's typed tools and the function that runs one tool call.

Every tool calls one method of the shared GoldRepository (api/queries.py): no SQL lives here, and the KPI
definitions stay in api/metrics.py. The model can only pick a tool and fill its arguments; metrics, groupings
and patterns are fixed lists, so it can only ask for what exists.

run_tool is the step the brief grades (detect -> validate -> run -> ToolMessage): it validates the arguments
again with the same Pydantic model, never raises, and always returns exactly one ToolMessage carrying the
tool_call_id (Azure rejects the next request with a 400 if one is missing).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from typing import Any, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from api.errors import DataUnavailable

log = logging.getLogger("api.assistant")

Metric = Literal[
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

BRANCH = r"^BR\d{3}$"  # BR001-BR012 in dim_branch
RULE_ID = r"^(CUS|APP|REP|TRX|MAC)-\d{2}$"
APPLICATION_ID = r"^LA\d{6}$"
ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
MAX_ROWS = 50  # every tool result goes back into the next model call, so keep it small


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KpiArgs(_Strict):
    metric: Metric = Field(description="The KPI to read. dti_band_share only works for the whole portfolio.")
    group_by: GroupBy | None = Field(default=None, description="Break the KPI down by branch, product, month or year. No other breakdown exists.")
    date_from: str | None = Field(default=None, pattern=ISO_DATE, description="First day, YYYY-MM-DD (data is monthly).")
    date_to: str | None = Field(default=None, pattern=ISO_DATE, description="Last day, YYYY-MM-DD (data is monthly).")
    branch_code: str | None = Field(default=None, pattern=BRANCH, description="Only this branch, e.g. BR003.")
    limit: int = Field(default=20, ge=1, le=MAX_ROWS, description="Maximum number of rows returned.")

    @field_validator("date_from", "date_to")
    @classmethod
    def _real_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError("not a real calendar date") from None
        return value

    @model_validator(mode="after")
    def _combination(self) -> KpiArgs:
        if self.metric == "dti_band_share" and (self.group_by or self.date_from or self.date_to or self.branch_code):
            raise ValueError("dti_band_share is only available for the whole portfolio: no group_by or filters")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class ExceptionArgs(_Strict):
    rule_id: str | None = Field(default=None, pattern=RULE_ID, description="Data-quality rule, e.g. APP-03.")
    action: Literal["FLAG", "REJECT"] | None = Field(default=None, description="What the pipeline did with the record.")
    branch_code: str | None = Field(default=None, pattern=BRANCH, description="Only this branch, e.g. BR003.")
    limit: int = Field(default=10, ge=1, le=MAX_ROWS, description="Maximum number of exceptions returned.")


class ExposureArgs(_Strict):
    application_id: str = Field(pattern=APPLICATION_ID, description="Loan application ID, e.g. LA000225.")


class MetadataArgs(_Strict):
    """No arguments."""


def build_tools(repo) -> list[BaseTool]:
    """The approved tools, bound to one repository. Tests pass FakeRepository, the API passes GoldRepository."""

    @tool("get_portfolio_kpi", args_schema=KpiArgs)
    def get_portfolio_kpi(
        metric: str,
        group_by: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        branch_code: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Read one portfolio KPI from Gold, overall or broken down by branch, product, month or year.
        Metrics: applications, requested_amount (EUR), approval_rate, avg_decision_days, high_dti_share
        (DTI of 35% or more), dti_band_share (whole portfolio only), delinquency_rate_30, outstanding_balance (EUR),
        manual_review_rate. Rates are ratios between 0 and 1. Use for any question about a KPI.
        Only these metrics exist. If the user asks for another one (rejection rate, profit ...), do not compute it
        yourself: say it is not available and give the closest listed metric instead.
        Only four breakdowns exist: branch, product, month and year. If the user asks for another one (segment,
        risk band, channel, region ...), do not substitute a different breakdown: say it is not available."""
        filters = {
            key: value
            for key, value in {"date_from": date_from, "date_to": date_to, "branch_code": branch_code}.items()
            if value
        }
        return repo.query_metric(metric, group_by=group_by, filters=filters, limit=limit)

    @tool("get_dq_exceptions", args_schema=ExceptionArgs)
    def get_dq_exceptions(
        rule_id: str | None = None, action: str | None = None, branch_code: str | None = None, limit: int = 10
    ) -> dict:
        """List data-quality exceptions (records the pipeline flagged or rejected), filtered by rule, action
        (FLAG or REJECT) or branch. Returns a short list plus the total. Use for questions about data quality."""
        return repo.get_exceptions(rule_id=rule_id, action=action, branch_code=branch_code, limit=limit)

    @tool("get_metadata", args_schema=MetadataArgs)
    def get_metadata() -> dict:
        """List the available metrics with their definitions and units, and the as-of date of the data.
        Use for questions about what the assistant can answer or do, which KPIs exist, how a KPI is defined,
        or how recent the data is."""
        info = repo.refresh_info()
        return {
            "metrics": repo.metric_catalogue(),
            "as_of_date": info["as_of_date"],
            "refreshed_at": info["refreshed_at"],
            "source": "api.metrics, gold.refresh_info",
        }

    @tool("get_connected_exposure", args_schema=ExposureArgs)
    def get_connected_exposure(application_id: str) -> dict | None:
        """Find the borrowers in the same household as the applicant of one loan application, and their total
        outstanding exposure (knowledge graph; it holds household links only). Needs an application ID like LA000225.
        Always call it when the user names an application ID, even one that looks unusual: an unknown ID comes
        back as "not found", and that is the answer to give."""
        return repo.connected_exposure(application_id)

    return [get_portfolio_kpi, get_dq_exceptions, get_metadata, get_connected_exposure]


def _problems(exc: ValidationError) -> list[dict[str, str]]:
    """Field and message only: the rejected value is never echoed back."""
    out = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False)[:5]:
        field = ".".join(str(part) for part in error["loc"]) or "arguments"
        out.append({"field": field, "message": error["msg"].removeprefix("Value error, ")})
    return out


def run_tool(call: dict, tools: dict[str, BaseTool]) -> tuple[ToolMessage, dict | None]:
    """Run one entry of AIMessage.tool_calls ({"name", "args", "id"}). Never raises.

    Success: (ToolMessage(status="success"), {"tool", "arguments", "result"}).
    Failure: (ToolMessage(status="error", content='{"error": ...}'), None) so the model can read it and react.
    """
    name = str(call.get("name", ""))[:60]
    call_id = str(call.get("id") or uuid.uuid4().hex)

    def reply(content: dict, status: str = "success") -> ToolMessage:
        return ToolMessage(content=json.dumps(content, default=str), tool_call_id=call_id, name=name, status=status)

    selected = tools.get(name)
    if selected is None:
        return reply({"error": "unknown tool", "tool": name, "approved_tools": sorted(tools)}, "error"), None

    raw = call.get("args")
    if not isinstance(raw, dict):
        return reply({"error": "invalid arguments", "details": [{"field": "arguments", "message": "expected a JSON object"}]}, "error"), None
    try:
        arguments = selected.args_schema.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        return reply({"error": "invalid arguments", "details": _problems(exc)}, "error"), None

    try:
        result: Any = selected.invoke(arguments)
    except DataUnavailable:
        return reply({"error": "data source unavailable, try again later"}, "error"), None
    except Exception as exc:  # noqa: BLE001 - nothing internal may reach the model
        log.warning("tool %s failed: %s", name, type(exc).__name__)
        return reply({"error": "the tool failed unexpectedly"}, "error"), None

    if result is None:
        return reply({"error": "not found", "arguments": arguments}, "error"), None
    return reply(result), {"tool": name, "arguments": arguments, "result": result}
