"""The 9 metrics the API serves: the 8 KPIs of the brief, with DTI two ways.

Each one is read from the Gold KPI tables, never recalculated from the facts. A rate is
sum(numerator) / sum(denominator) over the rows asked for; monthly rates are never averaged.
"""

METRICS: dict[str, dict] = {
    "applications": {
        "label": "Applications",
        "unit": "count",
        "definition": "number of loan applications",
        "numerator": "applications",
        "denominator": None,
    },
    "requested_amount": {
        "label": "Requested amount",
        "unit": "EUR",
        "definition": "total amount requested in the applications",
        "numerator": "requested_amount",
        "denominator": None,
    },
    "approval_rate": {
        "label": "Approval rate",
        "unit": "ratio",
        "definition": "approved / (approved + rejected)",
        "numerator": "approved_applications",
        "denominator": "decided_applications",
    },
    "avg_decision_days": {
        "label": "Average decision time",
        "unit": "days",
        "definition": "days from submission to decision, averaged over decided applications",
        "numerator": "decision_days_total",
        "denominator": "decided_applications",
    },
    "high_dti_share": {
        "label": "High DTI share",
        "unit": "ratio",
        "definition": "applications with a debt-to-income ratio of 35% or more / applications with a DTI",
        "numerator": "high_dti_applications",
        "denominator": "applications_with_dti",
    },
    "dti_band_share": {
        "label": "DTI band share",
        "unit": "ratio",
        "definition": "share of applications in each debt-to-income band (whole portfolio only)",
        "numerator": None,
        "denominator": None,
    },
    "delinquency_rate_30": {
        "label": "30-day delinquency rate",
        "unit": "ratio",
        "definition": "active loans 30 or more days past due / active loans",
        "numerator": "delinquent_loans_30",
        "denominator": "active_loans",
    },
    "outstanding_balance": {
        "label": "Outstanding balance",
        "unit": "EUR",
        "definition": "outstanding principal of the loans",
        "numerator": "outstanding_balance",
        "denominator": None,
    },
    "manual_review_rate": {
        "label": "Manual review rate",
        "unit": "ratio",
        "definition": "applications sent to manual review / applications",
        "numerator": "manual_reviews",
        "denominator": "applications",
    },
}


def metric_info(name: str) -> dict:
    """The public description of one metric: name, label, unit, definition."""
    m = METRICS[name]
    return {"name": name, "label": m["label"], "unit": m["unit"], "definition": m["definition"]}


def metric_catalogue() -> list[dict]:
    return [metric_info(name) for name in METRICS]
