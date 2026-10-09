"""The shared query module: one method per question the API answers.

Routes and the assistant's tools call the same methods. Each returns a JSON-ready dict with
`source` and `as_of_date`; a look-up of one item returns None when it doesn't exist; any
Databricks failure raises DataUnavailable (from api.db.run_query).

Rules (docs/contracts.md): Gold tables only; KPIs come from the Gold KPI tables, never from the facts;
a rate is sum(numerator) / sum(denominator), never an average of rates; table and column names come
from the fixed dicts below, and every value from a request is a :name parameter.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends

from api.db import run_query, table
from api.metrics import METRICS, metric_catalogue, metric_info
from api.settings import Settings, get_settings

GROUP_EXPRESSIONS = {
    None: "CAST(NULL AS STRING)",
    "branch": "COALESCE(b.branch_code, 'UNKNOWN')",  
    "product": "COALESCE(p.product_code, 'UNKNOWN')",
    "month": "CAST(k.month_key AS STRING)",
    "year": "CAST(k.month_key DIV 100 AS STRING)",
}
KPI_METRICS = [name for name, m in METRICS.items() if m["numerator"]]
PART_COLUMNS = sorted({m[c] for m in METRICS.values() for c in ("numerator", "denominator") if m[c]})
DTI_BANDS = {
    "below_20": "dti_share_below_20",
    "20_35": "dti_share_20_35",
    "35_50": "dti_share_35_50",
    "above_50": "dti_share_above_50",
}


def month_key(iso_date: str) -> int:
    """'2025-03-15' -> 202503, the yyyyMM key of kpi_portfolio_monthly."""
    d = date.fromisoformat(iso_date)
    return d.year * 100 + d.month


def ratio(numerator, denominator) -> float | None:
    if denominator is None:
        return numerator
    if not denominator:
        return None  
    return numerator / denominator


def kpis_from_parts(parts: dict) -> dict[str, float | None]:
    """Every KPI from summed additive parts."""
    out = {}
    for name in KPI_METRICS:
        m = METRICS[name]
        out[name] = ratio(parts.get(m["numerator"]) or 0, (parts.get(m["denominator"]) or 0) if m["denominator"] else None)
    return out


def iso_utc(value) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


class GoldRepository:
    def __init__(self, settings: Settings, run=run_query):
        self.settings = settings
        self._run = run  

    def _t(self, name: str) -> str:
        return table(self.settings, name)

    def _query(self, query: str, params: dict | None = None) -> list[dict]:
        return self._run(self.settings, query, params or {})

    def metric_catalogue(self) -> list[dict[str, Any]]:
        return metric_catalogue()  

    def query_metric(
        self,
        metric: str,
        group_by: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if metric == "dti_band_share":
            return self._dti_band_share()
        m = METRICS[metric]
        filters = filters or {}

        where, params = [], {}
        if filters.get("date_from"):
            where.append("k.month_key >= :month_from")
            params["month_from"] = month_key(filters["date_from"])
        if filters.get("date_to"):
            where.append("k.month_key <= :month_to")
            params["month_to"] = month_key(filters["date_to"])
        if filters.get("branch_code"):
            where.append("COALESCE(b.branch_code, 'UNKNOWN') = :branch_code")
            params["branch_code"] = filters["branch_code"]

        denominator = f"SUM(k.{m['denominator']})" if m["denominator"] else "CAST(NULL AS DOUBLE)"
        rows = self._query(
            f"""
            SELECT {GROUP_EXPRESSIONS[group_by]} AS grp,
                   SUM(k.{m['numerator']}) AS numerator,
                   {denominator} AS denominator
            FROM {self._t('kpi_portfolio_monthly')} k
            LEFT JOIN {self._t('dim_branch')} b ON k.branch_key = b.branch_key
            LEFT JOIN {self._t('dim_product')} p ON k.product_key = p.product_key
            {'WHERE ' + ' AND '.join(where) if where else ''}
            GROUP BY 1
            ORDER BY 1
            LIMIT {int(limit)}
            """,
            params,
        )
        result_rows = []
        for r in rows:
            row = {"group": r["grp"], "value": ratio(r["numerator"], r["denominator"])}
            if m["denominator"]:
                row |= {"numerator": r["numerator"], "denominator": r["denominator"]}
            result_rows.append(row)
        return {
            "metric": metric_info(metric),
            "group_by": group_by,
            "filters": filters,
            "rows": result_rows,
            "as_of_date": self.refresh_info()["as_of_date"],
            "source": "gold.kpi_portfolio_monthly",
        }

    def _dti_band_share(self) -> dict[str, Any]:
        columns = ", ".join(DTI_BANDS.values())
        summary = self._query(f"SELECT {columns} FROM {self._t('kpi_portfolio_summary')}")
        row = summary[0] if summary else {}
        return {
            "metric": metric_info("dti_band_share"),
            "group_by": None,
            "filters": {},
            "rows": [{"group": band, "value": row.get(column)} for band, column in DTI_BANDS.items()],
            "as_of_date": self.refresh_info()["as_of_date"],
            "source": "gold.kpi_portfolio_summary",
        }

    def branch_summary(self, branch_code: str) -> dict[str, Any] | None:
        parts = ",\n                   ".join(f"SUM(k.{c}) AS {c}" for c in PART_COLUMNS)
        rows = self._query(
            f"""
            SELECT b.branch_code, b.branch_name, p.product_code,
                   {parts}
            FROM {self._t('dim_branch')} b
            LEFT JOIN {self._t('kpi_portfolio_monthly')} k ON k.branch_key = b.branch_key
            LEFT JOIN {self._t('dim_product')} p ON k.product_key = p.product_key
            WHERE b.branch_code = :branch_code
            GROUP BY b.branch_code, b.branch_name, p.product_code
            ORDER BY p.product_code
            """,
            {"branch_code": branch_code},
        )
        if not rows:
            return None
        totals = {c: sum(r[c] or 0 for r in rows) for c in PART_COLUMNS}
        return {
            "branch_code": rows[0]["branch_code"],
            "branch_name": rows[0]["branch_name"] or "Unknown",
            "kpis": kpis_from_parts(totals),
            "by_product": [
                {"product_code": r["product_code"], "kpis": kpis_from_parts(r)} for r in rows if r["product_code"]
            ],
            "as_of_date": self.refresh_info()["as_of_date"],
            "source": "gold.kpi_portfolio_monthly",
        }

    def get_exceptions(
        self,
        rule_id: str | None = None,
        action: str | None = None,
        branch_code: str | None = None,
        batch_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        where, params = [], {}
        for value, condition, name in (
            (rule_id, "e.rule_id = :rule_id", "rule_id"),
            (action, "e.action = :action", "action"),
            (branch_code, "COALESCE(b.branch_code, 'UNKNOWN') = :branch_code", "branch_code"),
            (batch_id, "e.source_batch_id = :batch_id", "batch_id"),
        ):
            if value is not None:
                where.append(condition)
                params[name] = value
        frm = (
            f"FROM {self._t('fact_dq_exception')} e "
            f"LEFT JOIN {self._t('dim_branch')} b ON e.branch_key = b.branch_key "
            + ("WHERE " + " AND ".join(where) if where else "")
        )
    
        rows = self._query(
            f"""
            SELECT e.exception_key, e.rule_id, e.dq_dimension, e.action, e.description, e.entity,
                   CASE WHEN e.entity = 'customers' THEN SUBSTRING(SHA2(e.record_key, 256), 1, 16)
                        ELSE e.record_key END AS record_key,
                   b.branch_code, e.source_batch_id, e.detected_at,
                   COUNT(*) OVER () AS total
            {frm}
            ORDER BY e.rule_id, e.record_key
            LIMIT {int(limit)} OFFSET {int(offset)}
            """,
            params,
        )
        if rows:
            total = rows[0]["total"]
        else:  
            total = self._query(f"SELECT COUNT(*) AS total {frm}", params)[0]["total"]
        items = [{k: v for k, v in r.items() if k != "total"} for r in rows]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "as_of_date": self.refresh_info()["as_of_date"],
            "source": "gold.fact_dq_exception",
        }

    def connected_exposure(self, application_id: str) -> dict[str, Any] | None:
        
        edges, nodes = self._t("kg_edges"), self._t("kg_nodes")
        rows = self._query(
            f"""
            WITH applicant AS (
                SELECT source_id AS customer_id FROM {edges}
                WHERE relationship = 'APPLIED_FOR' AND target_id = CONCAT('application:', :application_id)
            ), households AS (
                SELECT e.target_id AS household_id FROM {edges} e JOIN applicant a ON e.source_id = a.customer_id
                WHERE e.relationship = 'MEMBER_OF'
            ), members AS (
                SELECT e.source_id AS customer_id FROM {edges} e JOIN households h ON e.target_id = h.household_id
                WHERE e.relationship = 'MEMBER_OF'
                UNION
                SELECT customer_id FROM applicant  -- an applicant with no household still counts
            )
            SELECT m.customer_id AS customer_node, n.label AS application_id,
                   get_json_object(n.properties, '$.status_code') AS status_code,
                   CAST(get_json_object(n.properties, '$.outstanding_balance') AS DECIMAL(14, 2)) AS outstanding_balance,
                   CAST(get_json_object(n.properties, '$.is_delinquent_30') AS INT) AS is_delinquent_30
            FROM members m
            JOIN {edges} e ON e.source_id = m.customer_id AND e.relationship = 'APPLIED_FOR'
            JOIN {nodes} n ON n.node_id = e.target_id
            ORDER BY application_id
            """,
            {"application_id": application_id},
        )
        if not rows:
            return None
        return {
            "application_id": application_id,
            "members": len({r["customer_node"] for r in rows}),
            "applications": rows,
            "total_outstanding": round(sum(r["outstanding_balance"] or 0 for r in rows), 2),
            "delinquent_loans": sum(r["is_delinquent_30"] or 0 for r in rows),
            "as_of_date": self.refresh_info()["as_of_date"],
            "source": "gold.kg_nodes, gold.kg_edges",
        }

    def refresh_info(self) -> dict[str, Any]:
        rows = self._query(f"SELECT as_of_date, refreshed_at FROM {self._t('refresh_info')} LIMIT 1")
        row = rows[0] if rows else {}
        as_of = row.get("as_of_date")
        return {
            "as_of_date": as_of.isoformat() if as_of is not None else None,
            "refreshed_at": iso_utc(row.get("refreshed_at")),
            "source": "gold.refresh_info",
        }


def get_repository(settings: Settings = Depends(get_settings)) -> GoldRepository:
    """FastAPI dependency shared by every data router; tests swap in FakeRepository."""
    return GoldRepository(settings)
