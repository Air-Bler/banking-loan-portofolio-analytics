"""The three approved analytical tools and their registry.

* ``get_portfolio_kpi``       - one headline KPI from kpi_portfolio_summary
* ``get_portfolio_breakdown`` - a filtered / grouped aggregate from approved Gold tables
* ``get_metadata``            - reference values from the approved dimension tables

The business logic lives in plain Python methods (testable without an LLM). The LangChain
``StructuredTool`` objects exist so the chat model can bind the typed schemas; the service executes
calls through ``ToolRegistry.execute`` which validates arguments first and never raises.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from .catalog import DTI_BAND_VALUES, MEASURES, SUMMARY_KPIS, format_value
from .errors import (
    AssistantError,
    ToolArgumentError,
    ToolExecutionError,
    UnsupportedRequestError,
)
from .models import (
    EvidenceItem,
    Filters,
    MetadataInput,
    PortfolioBreakdownInput,
    PortfolioKpiInput,
    ToolResult,
)
from .queries import (
    METADATA_SOURCES,
    build_breakdown_query,
    build_kpi_query,
    build_metadata_query,
)
from .repository import GoldRepository

_TIME_KEYS = ("year", "month", "month_from", "month_to")
_PASSTHROUGH = ("segment_code", "risk_band_code", "status_code", "channel", "employment_status", "ageing_bucket")


def _key(text: str) -> str:
    k = re.sub(r"[^a-z0-9]", "", text.lower())
    return k[:-1] if k.endswith("s") and len(k) > 3 else k   # tolerate simple plurals ("Mortgages")


class DimensionValues:
    """Distinct reference values from Gold, cached briefly, used to validate and canonicalise filters."""

    def __init__(self, repository: GoldRepository, ttl_seconds: float = 900.0, clock: Callable[[], float] = time.monotonic):
        self._repo, self._ttl, self._clock = repository, ttl_seconds, clock
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def rows(self, domain: str) -> list[dict[str, Any]]:
        hit = self._cache.get(domain)
        if hit and self._clock() - hit[0] < self._ttl:
            return hit[1]
        rows = self._repo.execute(build_metadata_query(domain))
        self._cache[domain] = (self._clock(), rows)
        return rows

    def _resolve(self, label: str, text: str, candidates: list[tuple[str, list[str]]]) -> str:
        """candidates: (canonical value, [accepted spellings])."""
        wanted = _key(text)
        hits = [canon for canon, names in candidates if any(_key(n) == wanted for n in names if n)]
        if len(hits) == 1:
            return hits[0]
        known = ", ".join(f"{c} ({n[0]})" if len(n) > 1 else c for c, n in candidates)
        if not hits:
            raise ToolArgumentError(f"Unknown {label} '{text}'. Known values: {known}.")
        raise ToolArgumentError(f"Ambiguous {label} '{text}'. Matches: {', '.join(hits)}.")

    def product_code(self, text: str) -> str:
        rows = self.rows("products")
        return self._resolve("product", text, [(r["product_code"], [r["product_code"], r["product_name"]]) for r in rows])

    def branch_code(self, text: str) -> str:
        rows = self.rows("branches")
        return self._resolve("branch", text, [(r["branch_code"], [r["branch_code"], r["branch_name"]]) for r in rows])

    def attribute(self, domain: str, column: str, text: str) -> str:
        values = sorted({r[column] for r in self.rows(domain) if r.get(column)})
        return self._resolve(column, text, [(v, [v]) for v in values])


@dataclass(frozen=True)
class Execution:
    """Outcome of one tool call, for the service and the trace."""

    result: ToolResult
    validated_args: dict[str, Any] | None
    duration_ms: float


class AnalyticsTools:
    def __init__(self, repository: GoldRepository, dimensions: DimensionValues | None = None):
        self._repo = repository
        self._dims = dimensions or DimensionValues(repository)

    # ---- tool 1 -------------------------------------------------------------------------------------------------
    def get_portfolio_kpi(self, args: PortfolioKpiInput) -> ToolResult:
        measure = SUMMARY_KPIS[args.metric]
        query = build_kpi_query(args.metric)
        rows = self._repo.execute(query)
        if not rows or rows[0].get("value") is None:
            return ToolResult(tool="get_portfolio_kpi", status="empty", measure=args.metric, source=list(query.sources),
                              definition=measure.definition,
                              message="The approved Gold KPI table returned no value for this measure.")
        value = rows[0]["value"]
        return ToolResult(tool="get_portfolio_kpi", status="ok", measure=args.metric, value=value,
                          display_value=format_value(measure.kind, value), source=list(query.sources),
                          definition=measure.definition, row_count=1,
                          limitations=["Current portfolio-level aggregate from the Gold KPI table.", *measure.limitations])

    # ---- tool 2 -------------------------------------------------------------------------------------------------
    def _resolve_filters(self, f: Filters | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if f is None:
            return out
        for name, value in f.applied().items():
            if name in _TIME_KEYS or name in _PASSTHROUGH:
                out[name] = value
            elif name == "product":
                out["product_code"] = self._dims.product_code(value)
            elif name == "branch":
                out["branch_code"] = self._dims.branch_code(value)
            elif name == "product_family":
                out[name] = self._dims.attribute("products", "product_family", value)
            elif name in ("city", "region"):
                out[name] = self._dims.attribute("branches", name, value)
            elif name == "dti_band":
                out[name] = DTI_BAND_VALUES[value]
        return out

    def get_portfolio_breakdown(self, args: PortfolioBreakdownInput) -> ToolResult:
        measure = MEASURES[args.metric]
        filters = self._resolve_filters(args.filters)
        query = build_breakdown_query(args.metric, args.group_by, filters, args.limit)
        rows = self._repo.execute(query)
        limitations = list(measure.limitations)
        base = {"tool": "get_portfolio_breakdown", "measure": args.metric, "group_by": args.group_by, "filters": filters,
                "source": list(query.sources), "definition": measure.definition}
        if not rows:
            return ToolResult(status="empty", message="No matching Gold data was found for these filters.",
                              limitations=limitations, **base)
        shaped = [{"group": {k: r[k] for k in query.group_columns}, "value": r["value"],
                   "display_value": format_value(measure.kind, r["value"])} for r in rows]
        if all(s["value"] is None for s in shaped):
            return ToolResult(status="empty", limitations=limitations, row_count=len(rows),
                              message="The measure is undefined for these filters (no applicable records or denominator).", **base)
        if args.group_by and len(rows) >= args.limit and args.group_by != "month":
            limitations.append(f"Only the top {args.limit} groups are shown.")
        if args.group_by is None:
            return ToolResult(status="ok", value=shaped[0]["value"], display_value=shaped[0]["display_value"],
                              limitations=limitations, row_count=1, **base)
        return ToolResult(status="ok", rows=shaped, limitations=limitations, row_count=len(shaped), **base)

    # ---- tool 3 -------------------------------------------------------------------------------------------------
    def get_metadata(self, args: MetadataInput) -> ToolResult:
        filters: dict[str, Any] = {}
        if args.product_family:
            filters["product_family"] = self._dims.attribute("products", "product_family", args.product_family)
        if args.city:
            filters["city"] = self._dims.attribute("branches", "city", args.city)
        if args.region:
            filters["region"] = self._dims.attribute("branches", "region", args.region)
        query = build_metadata_query(args.domain, filters)
        rows = self._repo.execute(query)
        base = {"tool": "get_metadata", "measure": args.domain, "filters": filters, "source": list(query.sources),
                "definition": f"Reference values from {METADATA_SOURCES[args.domain]}."}
        if not rows:
            return ToolResult(status="empty", message="No matching reference data was found.", **base)
        limitations = []
        if args.domain == "risk_bands":
            limitations.append("Band U means the risk score is missing or outside 300-850.")
        return ToolResult(status="ok", rows=rows, row_count=len(rows), limitations=limitations, **base)


# ---- evidence (deterministic, built from tool results; the model never writes evidence) ---------------------------------
def evidence_for(result: ToolResult, max_items: int = 25) -> list[EvidenceItem]:
    if result.status != "ok":
        return []
    source = ", ".join(result.source)
    if result.tool == "get_metadata":
        items = []
        for row in result.rows[:max_items]:
            values = list(row.values())
            if result.measure == "date_range":
                return [EvidenceItem(label="date_range", value=f"{row.get('min_date')} to {row.get('max_date')}", source=source)]
            items.append(EvidenceItem(label=f"{result.measure}:{values[0]}",
                                      value="; ".join(str(v) for v in values[1:] if v is not None) or str(values[0]),
                                      source=source))
        return items
    if result.rows:
        return [EvidenceItem(label=f"{result.measure} [{', '.join(f'{k}={v}' for k, v in r['group'].items())}]",
                             value=r["display_value"], source=source) for r in result.rows[:max_items]]
    return [EvidenceItem(label=str(result.measure), value=str(result.display_value), source=source)]


# ---- registry ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], ToolResult]


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors(include_url=False, include_input=False)[:5]:
        loc = ".".join(str(x) for x in e.get("loc", ())) or "arguments"
        parts.append(f"{loc}: {e.get('msg')}")
    return "Invalid tool arguments - " + "; ".join(parts)


def _unsupported_metric(exc: ValidationError, spec: ToolSpec) -> str | None:
    """A well-formed but unapproved metric name (e.g. 'profit') is 'unsupported', not 'malformed'."""
    for e in exc.errors(include_url=False):
        if e.get("loc") == ("metric",) and e.get("type") == "literal_error" and isinstance(e.get("input"), str):
            shown = str(e.get("input"))[:40]
            allowed = ", ".join(spec.input_model.model_fields["metric"].annotation.__args__)
            return (f"The measure '{shown}' is not available in the approved semantic layer, so no value can be given. "
                    f"Available measures: {allowed}.")
    return None


class ToolRegistry:
    def __init__(self, repository: GoldRepository):
        tools = AnalyticsTools(repository)
        self.tools = tools
        self._specs: dict[str, ToolSpec] = {s.name: s for s in (
            ToolSpec("get_portfolio_kpi",
                     "Retrieve ONE approved headline portfolio KPI (current, whole portfolio): applications, requested_amount, "
                     "approval_rate, avg_decision_days, dti_share_* bands, delinquency_rate_30, outstanding_balance, "
                     "manual_review_rate. Use for questions about the overall portfolio with no filters or grouping.",
                     PortfolioKpiInput, tools.get_portfolio_kpi),
            ToolSpec("get_portfolio_breakdown",
                     "Retrieve a filtered and/or grouped aggregate from approved Gold data. Choose a metric, optionally group_by "
                     "one dimension (month, product, product_family, branch, city, region, customer_segment, risk_band, "
                     "application_status, channel, employment_status, dti_band, ageing_bucket) and optional filters. "
                     "Repayment measures (open_installments, loans, amount_unpaid) cover open installments only.",
                     PortfolioBreakdownInput, tools.get_portfolio_breakdown),
            ToolSpec("get_metadata",
                     "List approved reference values: products, branches, customer_segments, risk_bands, application_statuses, "
                     "or the date_range of the data. Use to look up valid codes/names before filtering.",
                     MetadataInput, tools.get_metadata),
        )}

    @property
    def names(self) -> list[str]:
        return list(self._specs)

    def summary(self) -> str:
        return "\n".join(f"- {s.name}: {s.description}" for s in self._specs.values())

    def execute(self, name: str, raw_args: Any) -> Execution:
        """Validate and run one tool call. Never raises: every failure becomes an ``error`` ToolResult."""
        started = time.perf_counter()

        def done(result: ToolResult, validated=None) -> Execution:
            return Execution(result, validated, (time.perf_counter() - started) * 1000)

        spec = self._specs.get(name)
        if spec is None:
            return done(ToolResult(tool=name, status="error", error_category="unknown_tool",
                                   message=f"'{name}' is not an approved tool. Approved tools: {', '.join(self._specs)}."))
        if not isinstance(raw_args, dict):
            return done(ToolResult(tool=name, status="error", error_category=ToolArgumentError.category,
                                   message="Invalid tool arguments - expected a JSON object."))
        try:
            args = spec.input_model.model_validate(raw_args)
        except ValidationError as exc:
            unsupported = _unsupported_metric(exc, spec)
            if unsupported:
                return done(ToolResult(tool=name, status="error", error_category=UnsupportedRequestError.category,
                                       message=unsupported))
            return done(ToolResult(tool=name, status="error", error_category=ToolArgumentError.category,
                                   message=_validation_message(exc)))
        validated = args.model_dump(exclude_none=True)
        try:
            return done(spec.handler(args), validated)
        except AssistantError as exc:
            return done(ToolResult(tool=name, status="error", error_category=exc.category, message=exc.message), validated)
        except Exception:  # noqa: BLE001 - never leak internals to the model
            return done(ToolResult(tool=name, status="error", error_category=ToolExecutionError.category,
                                   message="The tool failed unexpectedly; the data could not be retrieved."), validated)

    def langchain_tools(self) -> list[StructuredTool]:
        def make(spec: ToolSpec) -> StructuredTool:
            def run(**kwargs) -> str:
                return self.execute(spec.name, kwargs).result.for_model()

            return StructuredTool.from_function(func=run, name=spec.name, description=spec.description,
                                                args_schema=spec.input_model)

        return [make(s) for s in self._specs.values()]
