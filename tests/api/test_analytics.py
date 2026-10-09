import pytest

from api.metrics import METRICS

QUERY = {"metric": "approval_rate", "group_by": "branch",
         "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"}, "limit": 100}


def test_query_grouped_by_branch(client):
    r = client.post("/analytics/query", json=QUERY)
    assert r.status_code == 200
    body = r.json()
    assert body["metric"]["name"] == "approval_rate"
    assert body["metric"]["unit"] == "ratio"
    assert body["group_by"] == "branch"
    assert body["filters"] == {"date_from": "2025-01-01", "date_to": "2025-12-31"}
    assert [row["group"] for row in body["rows"]] == ["BR001", "BR003"]
    assert body["as_of_date"] == "2025-12-31"
    assert body["source"] == "gold.kpi_portfolio_monthly"


@pytest.mark.parametrize("metric", sorted(METRICS))
def test_every_metric_is_accepted(client, metric):
    r = client.post("/analytics/query", json={"metric": metric})
    assert r.status_code == 200
    assert r.json()["metric"]["name"] == metric


def test_query_without_grouping(client):
    r = client.post("/analytics/query", json={"metric": "applications"})
    assert r.status_code == 200
    assert r.json()["rows"] == [{"group": None, "value": 0.6, "numerator": 60, "denominator": 100}]


def test_dti_band_share_for_whole_portfolio(client):
    r = client.post("/analytics/query", json={"metric": "dti_band_share"})
    assert r.status_code == 200
    assert r.json()["source"] == "gold.kpi_portfolio_summary"
    assert len(r.json()["rows"]) == 4


@pytest.mark.parametrize("body", [
    {"metric": "profit"},                                                   
    {"metric": "approval_rate", "limit": 0},                                
    {"metric": "approval_rate", "group_by": "risk_band"},                   
    {"metric": "approval_rate", "filters": {"branch_code": "x;DROP"}},      
    {"metric": "approval_rate", "filters": {"date_from": "2025-12-31", "date_to": "2025-01-01"}},
    {"metric": "approval_rate", "filters": {"customer": "x"}},            
    {"metric": "dti_band_share", "group_by": "branch"},                     
    {},                                                                     
])
def test_query_rejects_bad_input(client, body):
    assert client.post("/analytics/query", json=body).status_code == 422


def test_metric_catalogue_lists_nine_metrics(client):
    r = client.get("/metadata/metrics")
    assert r.status_code == 200
    names = [m["name"] for m in r.json()["metrics"]]
    assert len(names) == 9
    assert {"approval_rate", "high_dti_share", "dti_band_share"} <= set(names)


def test_metric_catalogue_needs_no_databricks(broken_client):
    assert broken_client.get("/metadata/metrics").status_code == 200
