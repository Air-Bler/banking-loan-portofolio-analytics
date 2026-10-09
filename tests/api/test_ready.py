def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "as_of_date": "2025-12-31", "refreshed_at": "2026-10-05T09:44:49Z"}


def test_not_ready_when_databricks_is_down(broken_client):
    r = broken_client.get("/ready")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "data_unavailable"
