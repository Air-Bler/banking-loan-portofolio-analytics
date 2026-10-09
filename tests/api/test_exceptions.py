import pytest


def test_first_page(client):
    r = client.get("/exceptions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["items"]) == 3
    assert "record_payload" not in body["items"][0]


def test_filters_and_paging(client):
    body = client.get("/exceptions", params={"action": "FLAG", "limit": 1, "offset": 1}).json()
    assert body["total"] == 2
    assert [item["rule_id"] for item in body["items"]] == ["TRX-04"]


def test_filter_by_rule(client):
    body = client.get("/exceptions", params={"rule_id": "APP-03"}).json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "REJECT"


@pytest.mark.parametrize("params", [
    {"limit": 0},
    {"limit": 101},
    {"offset": -1},
    {"action": "DELETE"},
    {"rule_id": "APP3"},
    {"branch_code": "BR1"},
])
def test_bad_parameters_are_422(client, params):
    assert client.get("/exceptions", params=params).status_code == 422


def test_databricks_down_is_503(broken_client):
    assert broken_client.get("/exceptions").status_code == 503
