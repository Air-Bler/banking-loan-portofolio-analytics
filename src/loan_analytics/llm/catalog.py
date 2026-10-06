"""The approved semantic vocabulary: measures, dimensions and their Gold definitions.

Everything that can appear as an identifier in SQL (table names, column names, expressions) is defined
HERE as a constant. User/model input only ever selects an entry by an enum value; it is never
interpolated into SQL. Definitions mirror pipelines/gold/kpis.sql and the Gold fact SQL.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- measures --------------------------------------------------------------------------------------------------
DELINQUENCY_NOTE = (
    "Open installments are never written off, so most 30+ day delinquency is old unresolved debt; "
    "read it together with the ageing buckets."
)


@dataclass(frozen=True)
class Measure:
    name: str
    kind: str                       # count | amount | rate | days
    label: str
    definition: str
    limitations: tuple[str, ...] = ()
    fact_expr: str | None = None    # over fact_loan_application alias f
    monthly_expr: str | None = None  # over kpi_portfolio_monthly alias m
    repayment_expr: str | None = None  # over fact_repayment alias r (open installments only)


_M = {}


def _add(m: Measure) -> None:
    _M[m.name] = m


_add(Measure("applications", "count", "Applications", "Number of loan applications.",
             fact_expr="COUNT(*)", monthly_expr="SUM(m.applications)"))
_add(Measure("requested_amount", "amount", "Requested amount (EUR)", "Sum of the amounts requested by applicants.",
             fact_expr="SUM(f.requested_amount)", monthly_expr="SUM(m.requested_amount)"))
_add(Measure("decided_applications", "count", "Decided applications", "Applications that are APPROVED or REJECTED.",
             fact_expr="SUM(f.is_decided)", monthly_expr="SUM(m.decided_applications)"))
_add(Measure("approved_applications", "count", "Approved applications", "Applications with status APPROVED.",
             fact_expr="SUM(f.is_approved)", monthly_expr="SUM(m.approved_applications)"))
_add(Measure("approval_rate", "rate", "Approval rate",
             "Approved / (approved + rejected); withdrawn and undecided applications are excluded.",
             fact_expr="TRY_DIVIDE(SUM(f.is_approved), SUM(f.is_decided))",
             monthly_expr="TRY_DIVIDE(SUM(m.approved_applications), SUM(m.decided_applications))"))
_add(Measure("avg_decision_days", "days", "Average decision time",
             "Average days from application to decision, over approved and rejected applications.",
             fact_expr="AVG(CASE WHEN f.is_decided = 1 THEN f.decision_days END)"))
_add(Measure("manual_review_rate", "rate", "Manual-review rate",
             "Share of all applications that required manual review.",
             fact_expr="AVG(f.is_manual_review)",
             monthly_expr="TRY_DIVIDE(SUM(m.manual_reviews), SUM(m.applications))"))
_add(Measure("active_loans", "count", "Active loans", "Approved loans that are not paid off.",
             fact_expr="SUM(f.is_active_loan)", monthly_expr="SUM(m.active_loans)"))
_add(Measure("delinquent_loans_30", "count", "Delinquent loans (30+ days)",
             "Active loans with at least one open installment 30 or more days past due.",
             limitations=(DELINQUENCY_NOTE,),
             fact_expr="SUM(f.is_delinquent_30)", monthly_expr="SUM(m.delinquent_loans_30)"))
_add(Measure("delinquency_rate_30", "rate", "Delinquency rate (30+ days)",
             "Active loans with an open installment 30+ days past due / active loans.",
             limitations=(DELINQUENCY_NOTE,),
             fact_expr="TRY_DIVIDE(SUM(f.is_delinquent_30), SUM(f.is_active_loan))",
             monthly_expr="TRY_DIVIDE(SUM(m.delinquent_loans_30), SUM(m.active_loans))"))
_add(Measure("outstanding_balance", "amount", "Outstanding balance (EUR)",
             "Approved amount minus principal paid, over approved loans, at the as-of date.",
             fact_expr="SUM(f.outstanding_balance)", monthly_expr="SUM(m.outstanding_balance)"))
_add(Measure("open_installments", "count", "Open installments",
             "Installments that are partially paid or missed (open).",
             repayment_expr="COUNT(*)"))
_add(Measure("loans", "count", "Loans with open installments",
             "Distinct loans that have at least one open installment.",
             repayment_expr="COUNT(DISTINCT r.application_id)"))
_add(Measure("amount_unpaid", "amount", "Unpaid amount (EUR)",
             "Total due minus total paid, over open installments.",
             repayment_expr="SUM(r.amount_unpaid)"))

MEASURES: dict[str, Measure] = _M
REPAYMENT_MEASURES = frozenset(n for n, m in MEASURES.items() if m.repayment_expr)

# headline KPIs: the column of the same name in kpi_portfolio_summary
SUMMARY_KPIS: dict[str, Measure] = {
    "applications": MEASURES["applications"],
    "requested_amount": MEASURES["requested_amount"],
    "approval_rate": MEASURES["approval_rate"],
    "avg_decision_days": MEASURES["avg_decision_days"],
    "delinquency_rate_30": MEASURES["delinquency_rate_30"],
    "outstanding_balance": MEASURES["outstanding_balance"],
    "manual_review_rate": MEASURES["manual_review_rate"],
    "dti_share_below_20": Measure("dti_share_below_20", "rate", "Share of applications with DTI below 20%",
                                  "Applications with DTI below 20% / applications with a DTI value."),
    "dti_share_20_35": Measure("dti_share_20_35", "rate", "Share of applications with DTI 20-35%",
                               "Applications with DTI from 20% to below 35% / applications with a DTI value."),
    "dti_share_35_50": Measure("dti_share_35_50", "rate", "Share of applications with DTI 35-50%",
                               "Applications with DTI from 35% to 50% / applications with a DTI value."),
    "dti_share_above_50": Measure("dti_share_above_50", "rate", "Share of applications with DTI above 50%",
                                  "Applications with DTI above 50% / applications with a DTI value."),
}


def format_value(kind: str, value) -> str:
    if value is None:
        return "n/a"
    if kind == "rate":
        return f"{float(value) * 100:.2f}%"
    if kind == "amount":
        return f"EUR {float(value):,.2f}"
    if kind == "days":
        return f"{float(value):.2f} days"
    return f"{round(float(value)):,}"


# ---- dimensions: one entry per group_by value -------------------------------------------------------------------
# dim table alias -> (table, key column on the facts)
DIM_JOINS = {
    "p": ("dim_product", "product_key"),
    "b": ("dim_branch", "branch_key"),
    "s": ("dim_customer_segment", "customer_segment_key"),
    "rb": ("dim_risk_band", "risk_band_key"),
    "st": ("dim_application_status", "status_key"),
}


@dataclass(frozen=True)
class Group:
    """How a group_by value maps to SQL: columns to select (alias -> expression) and the dim it needs."""

    columns: tuple[tuple[str, str], ...]     # (output name, expression)
    dim: str | None = None                   # alias in DIM_JOINS
    fact_only: bool = False                  # not available on fact_repayment / monthly
    application_only: bool = False
    repayment_only: bool = False
    monthly_ok: bool = False                 # available on kpi_portfolio_monthly


GROUPS: dict[str, Group] = {
    "month": Group((("month_key", "{month}"),), monthly_ok=True),
    "product": Group((("product_code", "p.product_code"), ("product_name", "p.product_name")), "p", monthly_ok=True),
    "product_family": Group((("product_family", "p.product_family"),), "p", monthly_ok=True),
    "branch": Group((("branch_code", "b.branch_code"), ("branch_name", "b.branch_name")), "b", monthly_ok=True),
    "city": Group((("city", "b.city"),), "b", monthly_ok=True),
    "region": Group((("region", "b.region"),), "b", monthly_ok=True),
    "customer_segment": Group((("segment_code", "s.segment_code"), ("segment_name", "s.segment_name")), "s"),
    "risk_band": Group((("risk_band_code", "rb.risk_band_code"), ("risk_band_name", "rb.risk_band_name")), "rb"),
    "application_status": Group((("status_code", "st.status_code"), ("status_name", "st.status_name")), "st", application_only=True),
    "channel": Group((("channel", "{fact}.channel"),), application_only=True),
    "employment_status": Group((("employment_status", "{fact}.employment_status_at_application"),), application_only=True),
    "dti_band": Group((("dti_band", "{fact}.dti_band"),), application_only=True),
    "ageing_bucket": Group((("ageing_bucket", "r.ageing_bucket"),), repayment_only=True),
}

# filters: field -> (SQL condition template, dim alias or None, scope)
#   scope: "both" = application and repayment measures, "app" = application measures only, "rep" = repayment only
FILTERS: dict[str, tuple[str, str | None, str]] = {
    "product_code": ("p.product_code = :product_code", "p", "both"),
    "product_family": ("p.product_family = :product_family", "p", "both"),
    "branch_code": ("b.branch_code = :branch_code", "b", "both"),
    "city": ("b.city = :city", "b", "both"),
    "region": ("b.region = :region", "b", "both"),
    "segment_code": ("s.segment_code = :segment_code", "s", "both"),
    "risk_band_code": ("rb.risk_band_code = :risk_band_code", "rb", "both"),
    "status_code": ("st.status_code = :status_code", "st", "app"),
    "channel": ("{fact}.channel = :channel", None, "app"),
    "employment_status": ("{fact}.employment_status_at_application = :employment_status", None, "app"),
    "dti_band": ("{fact}.dti_band = :dti_band", None, "app"),
    "ageing_bucket": ("r.ageing_bucket = :ageing_bucket", None, "rep"),
}

DTI_BAND_VALUES = {  # friendly value -> value stored in fact_loan_application.dti_band
    "below_20": "1. Below 20%",
    "20_35": "2. 20-35%",
    "35_50": "3. 35-50%",
    "above_50": "4. Above 50%",
    "unknown": "Unknown",
}

# filters the monthly KPI table can serve (its grain is month x branch x product)
MONTHLY_FILTERS = frozenset({"product_code", "product_family", "branch_code", "city", "region"})
