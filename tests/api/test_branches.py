def test_branch_summary(client):
    r = client.get("/branches/BR003/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["branch_code"] == "BR003"
    assert body["kpis"]["approval_rate"] == 0.592
    assert body["by_product"][0]["product_code"] == "PL-STD"
    assert body["as_of_date"] == "2025-12-31"


def test_unknown_branch_is_404(client):
    assert client.get("/branches/BR099/summary").status_code == 404


def test_malformed_branch_code_is_422(client):
    assert client.get("/branches/athens/summary").status_code == 422


def test_databricks_down_is_503(broken_client):
    assert broken_client.get("/branches/BR003/summary").status_code == 503
