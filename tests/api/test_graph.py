def test_connected_exposure(client):
    r = client.get("/graph/applications/LA000225/connected-exposure")
    assert r.status_code == 200
    body = r.json()
    assert body["application_id"] == "LA000225"
    assert body["members"] == 2
    assert len(body["applications"]) == 2
    assert body["total_outstanding"] == 20800.5
    assert body["delinquent_loans"] == 1


def test_unknown_application_is_404(client):
    assert client.get("/graph/applications/LA999999/connected-exposure").status_code == 404


def test_malformed_application_id_is_422(client):
    assert client.get("/graph/applications/225/connected-exposure").status_code == 422


def test_databricks_down_is_503(broken_client):
    assert broken_client.get("/graph/applications/LA000225/connected-exposure").status_code == 503
