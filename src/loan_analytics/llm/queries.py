"""Builders for the approved Gold queries.

No SQL is ever generated from free text. A query is assembled from constants in ``catalog`` selected by
validated enum values; every user-influenced VALUE is passed as a bound parameter (``:name``). Table
names are unqualified: the repository runs them in the configured catalog/schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .catalog import (
    DIM_JOINS,
    FILTERS,
    GROUPS,
    MEASURES,
    MONTHLY_FILTERS,
    REPAYMENT_MEASURES,
    SUMMARY_KPIS,
)
from .errors import ToolArgumentError, UnsupportedRequestError

Param = tuple[str, Any, str]   # (name, value, SQL type: STRING | INT)


@dataclass(frozen=True)
class ApprovedQuery:
    name: str                              # stable id, e.g. "kpi_summary:approval_rate"
    sql: str
    params: tuple[Param, ...] = ()
    sources: tuple[str, ...] = ()          # Gold tables read
    max_rows: int = 100
    group_columns: tuple[str, ...] = field(default=())   # output columns that identify a group


# ---- headline KPI ------------------------------------------------------------------------------------------------
def build_kpi_query(metric: str) -> ApprovedQuery:
    if metric not in SUMMARY_KPIS:                        # defence in depth; the enum already guarantees it
        raise UnsupportedRequestError(f"'{metric}' is not an approved headline KPI.")
    return ApprovedQuery(name=f"kpi_summary:{metric}", sql=f"SELECT {metric} AS value FROM kpi_portfolio_summary LIMIT 1",
                         sources=("kpi_portfolio_summary",), max_rows=1)


# ---- breakdown -----------------------------------------------------------------------------------------------------
def _month_bounds(filters: dict[str, Any]) -> tuple[int, int] | None:
    if filters.get("year") is not None:
        y = filters["year"]
        if filters.get("month") is not None:
            k = y * 100 + filters["month"]
            return k, k
        return y * 100 + 1, y * 100 + 12
    if filters.get("month_from") or filters.get("month_to"):
        lo = int(filters["month_from"].replace("-", "")) if filters.get("month_from") else 200001
        hi = int(filters["month_to"].replace("-", "")) if filters.get("month_to") else 210012
        return lo, hi
    return None


def build_breakdown_query(metric: str, group_by: str | None, filters: dict[str, Any], limit: int) -> ApprovedQuery:
    """``filters`` holds canonical, already-validated values (codes resolved against the dimensions)."""
    measure = MEASURES[metric]
    repayment = metric in REPAYMENT_MEASURES
    group = GROUPS[group_by] if group_by else None

    # ---- scope checks
    if group:
        if repayment and group.application_only:
            raise UnsupportedRequestError(f"'{group_by}' is not available for repayment measures like '{metric}'.")
        if not repayment and group.repayment_only:
            raise UnsupportedRequestError(f"'{group_by}' is only available for repayment measures "
                                          "(open_installments, loans, amount_unpaid).")
    for name in filters:
        if name in ("year", "month", "month_from", "month_to"):
            continue
        scope = FILTERS[name][2]
        if scope == "app" and repayment:
            raise UnsupportedRequestError(f"Filter '{name}' is not available for repayment measure '{metric}'.")
        if scope == "rep" and not repayment:
            raise UnsupportedRequestError(f"Filter '{name}' only applies to repayment measures.")

    bounds = _month_bounds(filters)
    params: list[Param] = []
    conditions: list[str] = []

    # ---- source selection
    ageing_only = (repayment and group_by == "ageing_bucket" and not filters)
    if ageing_only:
        col = metric
        sql = f"SELECT ageing_bucket, {col} AS value FROM kpi_open_installment_ageing ORDER BY ageing_bucket LIMIT {limit}"
        return ApprovedQuery(name=f"breakdown:{metric}:ageing", sql=sql, sources=("kpi_open_installment_ageing",),
                             max_rows=limit, group_columns=("ageing_bucket",))

    if repayment:
        table, alias, expr = "fact_repayment", "r", measure.repayment_expr
        month_expr = "CAST(r.due_date_key / 100 AS INT)"
        conditions.append("r.is_open = 1")
    else:
        filter_names = {k for k in filters if k not in ("year", "month", "month_from", "month_to")}
        monthly = (measure.monthly_expr is not None
                   and (group is None or group.monthly_ok)
                   and filter_names <= MONTHLY_FILTERS)
        if monthly:
            table, alias, expr, month_expr = "kpi_portfolio_monthly", "m", measure.monthly_expr, "m.month_key"
        else:
            table, alias, expr = "fact_loan_application", "f", measure.fact_expr
            month_expr = "CAST(f.application_date_key / 100 AS INT)"

    # ---- group columns
    select_cols: list[str] = []
    group_exprs: list[str] = []
    group_names: list[str] = []
    needed_dims: list[str] = []
    if group:
        for out, tmpl in group.columns:
            e = tmpl.format(month=month_expr, fact=alias)
            select_cols.append(f"{e} AS {out}")
            group_exprs.append(e)
            group_names.append(out)
        if group.dim:
            needed_dims.append(group.dim)

    # ---- filters (values are always bound parameters)
    for name, value in filters.items():
        if name in ("year", "month", "month_from", "month_to"):
            continue
        tmpl, dim, _scope = FILTERS[name]
        conditions.append(tmpl.format(fact=alias))
        params.append((name, value, "STRING"))
        if dim:
            needed_dims.append(dim)
    if bounds:
        conditions.append(f"{month_expr} BETWEEN :month_from AND :month_to")
        params += [("month_from", bounds[0], "INT"), ("month_to", bounds[1], "INT")]

    joins = []
    for dim_alias in ("p", "b", "s", "rb", "st"):
        if dim_alias in needed_dims:
            dim_table, key = DIM_JOINS[dim_alias]
            joins.append(f"JOIN {dim_table} {dim_alias} ON {alias}.{key} = {dim_alias}.{key}")

    sources = [table] + [DIM_JOINS[a][0] for a in ("p", "b", "s", "rb", "st") if a in needed_dims]
    sql = f"SELECT {', '.join(select_cols + [expr + ' AS value'])} FROM {table} {alias}"
    if joins:
        sql += " " + " ".join(joins)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if group:
        sql += " GROUP BY " + ", ".join(group_exprs)
        if group_by == "month":
            sql += " ORDER BY month_key ASC"
        else:
            sql += f" ORDER BY value DESC NULLS LAST, {group_names[0]} ASC"
        sql += f" LIMIT {limit}"
    else:
        sql += " LIMIT 1"
    return ApprovedQuery(name=f"breakdown:{metric}:{group_by or 'total'}", sql=sql, params=tuple(params),
                         sources=tuple(sources), max_rows=limit if group else 1, group_columns=tuple(group_names))


# ---- metadata ---------------------------------------------------------------------------------------------------------
METADATA_SOURCES = {
    "products": "dim_product", "branches": "dim_branch", "customer_segments": "dim_customer_segment",
    "risk_bands": "dim_risk_band", "application_statuses": "dim_application_status", "date_range": "dim_date",
}


def build_metadata_query(domain: str, filters: dict[str, Any] | None = None) -> ApprovedQuery:
    filters = filters or {}
    allowed = {"products": {"product_family"}, "branches": {"city", "region"}}.get(domain, set())
    extra = set(filters) - allowed
    if extra:
        raise ToolArgumentError(f"Filter(s) {sorted(extra)} do not apply to metadata domain '{domain}'.")
    params: list[Param] = []
    src = METADATA_SOURCES[domain]
    if domain == "products":
        sql = ("SELECT product_code, product_name, product_family, min_amount, max_amount, min_term_months, "
               "max_term_months, base_rate FROM dim_product WHERE product_key <> -1")
        if "product_family" in filters:
            sql += " AND product_family = :product_family"
            params.append(("product_family", filters["product_family"], "STRING"))
        sql += " ORDER BY product_code"
    elif domain == "branches":
        sql = "SELECT branch_code, branch_name, city, region, opened_date FROM dim_branch WHERE branch_key <> -1"
        for f in ("city", "region"):
            if f in filters:
                sql += f" AND {f} = :{f}"
                params.append((f, filters[f], "STRING"))
        sql += " ORDER BY branch_code"
    elif domain == "customer_segments":
        sql = ("SELECT segment_code, segment_name, description FROM dim_customer_segment "
               "WHERE customer_segment_key <> -1 ORDER BY segment_code")
    elif domain == "risk_bands":   # includes the 'U' (unknown / out of range) member on purpose
        sql = "SELECT risk_band_code, risk_band_name, min_score, max_score, sort_order FROM dim_risk_band ORDER BY sort_order"
    elif domain == "application_statuses":
        sql = ("SELECT status_code, status_name, is_final, is_decided, is_approved, sort_order "
               "FROM dim_application_status WHERE status_key <> -1 ORDER BY sort_order")
    else:  # date_range
        sql = "SELECT MIN(`date`) AS min_date, MAX(`date`) AS max_date FROM dim_date"
    return ApprovedQuery(name=f"metadata:{domain}", sql=sql, params=tuple(params), sources=(src,), max_rows=200)
