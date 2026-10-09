"""GoldRepository against a recording runner: checks the SQL it sends and the numbers it computes, without Databricks."""

from datetime import date, datetime, timezone

import pytest

from api import db
from api.errors import DataUnavailable
from api.queries import GoldRepository
from api.settings import Settings

SETTINGS = Settings(databricks_catalog="cat", databricks_schema="team2")
REFRESH = {"as_of_date": date(2025, 12, 31), "refreshed_at": datetime(2026, 10, 5, 9, 44, 49, tzinfo=timezone.utc)}


class Runner:
    """Records every query; answers refresh_info with REFRESH and anything else with the given rows."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, settings, query, params):
        self.calls.append((query, params))
        if "refresh_info" in query and "kpi_portfolio" not in query:
            return [REFRESH]
        return self.answers.pop(0) if self.answers else []

    @property
    def data_calls(self):
        return [c for c in self.calls if "refresh_info" not in c[0]]


def repo(*answers):
    runner = Runner(*answers)
    return GoldRepository(SETTINGS, run=runner), runner


def test_rate_is_sum_of_parts_not_an_average():
    r, runner = repo([
        {"grp": "BR001", "numerator": 30, "denominator": 40},
        {"grp": "BR002", "numerator": 0, "denominator": 0},
    ])
    out = r.query_metric("approval_rate", group_by="branch", filters={"date_from": "2025-01-01"})
    assert out["rows"] == [
        {"group": "BR001", "value": 0.75, "numerator": 30, "denominator": 40},
        {"group": "BR002", "value": None, "numerator": 0, "denominator": 0},  
    ]
    query, params = runner.data_calls[0]
    assert "SUM(k.approved_applications)" in query and "SUM(k.decided_applications)" in query
    assert "AVG" not in query
    assert params == {"month_from": 202501}
    assert out["as_of_date"] == "2025-12-31"


def test_request_values_are_parameters_never_sql():
    r, runner = repo([])
    r.query_metric("applications", group_by="month",
                   filters={"date_from": "2024-03-15", "date_to": "2025-02-01", "branch_code": "BR003"}, limit=7)
    query, params = runner.data_calls[0]
    assert "BR003" not in query
    assert params == {"month_from": 202403, "month_to": 202502, "branch_code": "BR003"}
    assert "LIMIT 7" in query
    assert "`cat`.`team2`.`kpi_portfolio_monthly`" in query


def test_count_metric_has_no_ratio():
    r, _ = repo([{"grp": None, "numerator": 29000, "denominator": None}])
    assert r.query_metric("applications")["rows"] == [{"group": None, "value": 29000}]


def test_dti_band_share_reads_the_summary():
    r, runner = repo([{"dti_share_below_20": 0.6352, "dti_share_20_35": 0.207,
                       "dti_share_35_50": 0.12, "dti_share_above_50": 0.0377}])
    out = r.query_metric("dti_band_share")
    assert out["source"] == "gold.kpi_portfolio_summary"
    assert [row["group"] for row in out["rows"]] == ["below_20", "20_35", "35_50", "above_50"]
    assert "kpi_portfolio_summary" in runner.data_calls[0][0]


def test_branch_summary_totals_and_by_product():
    parts = dict.fromkeys(["active_loans", "applications_with_dti", "decision_days_total", "delinquent_loans_30",
                           "high_dti_applications", "manual_reviews", "outstanding_balance", "requested_amount"], 0)
    r, _ = repo([
        {"branch_code": "BR003", "branch_name": "Thessaloniki", "product_code": "AUT-NEW", **parts,
         "applications": 10, "approved_applications": 3, "decided_applications": 4},
        {"branch_code": "BR003", "branch_name": "Thessaloniki", "product_code": "PL-STD", **parts,
         "applications": 30, "approved_applications": 6, "decided_applications": 16},
    ])
    out = r.branch_summary("BR003")
    assert out["kpis"]["applications"] == 40
    assert out["kpis"]["approval_rate"] == 9 / 20  
    assert [p["product_code"] for p in out["by_product"]] == ["AUT-NEW", "PL-STD"]


def test_unknown_branch_is_none():
    r, _ = repo([])
    assert r.branch_summary("BR099") is None


def test_exceptions_never_select_the_payload_and_hash_customers():
    r, runner = repo([{"exception_key": 1, "rule_id": "CUS-04", "record_key": "abc", "total": 571}])
    out = r.get_exceptions(rule_id="CUS-04", action="FLAG", limit=5, offset=10)
    query, params = runner.data_calls[0]
    assert "record_payload" not in query
    assert "SHA2(e.record_key, 256)" in query
    assert params == {"rule_id": "CUS-04", "action": "FLAG"}
    assert "LIMIT 5 OFFSET 10" in query
    assert out["total"] == 571
    assert "total" not in out["items"][0]


def test_empty_exceptions_page_counts_separately():
    r, runner = repo([], [{"total": 3}])
    assert r.get_exceptions(offset=100)["total"] == 3


def test_unknown_application_is_none():
    r, runner = repo([])
    assert r.connected_exposure("LA999999") is None
    assert runner.data_calls[0][1] == {"application_id": "LA999999"}


def test_connected_exposure_totals():
    r, _ = repo([
        {"customer_node": "customer:a", "application_id": "LA000225", "status_code": "WITHDRAWN",
         "outstanding_balance": 0.0, "is_delinquent_30": 0},
        {"customer_node": "customer:b", "application_id": "LA000318", "status_code": "APPROVED",
         "outstanding_balance": 8300.5, "is_delinquent_30": 1},
    ])
    out = r.connected_exposure("LA000225")
    assert out["members"] == 2
    assert out["total_outstanding"] == 8300.5
    assert out["delinquent_loans"] == 1


def test_refresh_info_is_iso_utc():
    r, _ = repo()
    assert r.refresh_info()["refreshed_at"] == "2026-10-05T09:44:49Z"


def test_bad_schema_name_never_reaches_sql():
    bad = GoldRepository(Settings(databricks_schema="team2; DROP TABLE x"), run=Runner())
    with pytest.raises(DataUnavailable):
        bad.refresh_info()


def test_connector_failure_becomes_data_unavailable(monkeypatch):
    def broken_connect(**kwargs):
        raise ConnectionError("warehouse unreachable")

    monkeypatch.setattr(db.sql, "connect", broken_connect)
    with pytest.raises(DataUnavailable):
        db.run_query(SETTINGS, "SELECT 1")
