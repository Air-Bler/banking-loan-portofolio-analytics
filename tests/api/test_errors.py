from fastapi.testclient import TestClient

from api.main import app
from api.queries import get_repository


def assert_error(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert set(error) == {"code", "message", "correlation_id", "details"}
    return error


def test_unknown_branch_is_404(client):
    error = assert_error(client.get("/branches/BR099/summary"), 404, "not_found")
    assert error["message"] == "Branch BR099 not found"


def test_unknown_route_is_404(client):
    assert_error(client.get("/nope"), 404, "not_found")


def test_bad_body_is_422_with_details(client):
    error = assert_error(client.post("/analytics/query", json={"metric": "profit"}), 422, "validation_error")
    assert [d["field"] for d in error["details"]] == ["metric"]


def test_bad_query_parameter_is_422(client):
    error = assert_error(client.get("/exceptions", params={"limit": 0}), 422, "validation_error")
    assert error["details"][0]["field"] == "query.limit"


def test_databricks_down_is_503(broken_client):
    error = assert_error(broken_client.post("/analytics/query", json={"metric": "applications"}), 503, "data_unavailable")
    assert "Databricks" not in error["message"]  


class ExplodingRepository:
    def query_metric(self, *args, **kwargs):
        raise RuntimeError("secret detail that must not leak")


def test_unexpected_error_is_500_without_stack_trace(client):
    app.dependency_overrides[get_repository] = lambda: ExplodingRepository()
    response = TestClient(app, headers={"X-API-Key": "test-key"}, raise_server_exceptions=False).post("/analytics/query", json={"metric": "applications"})
    error = assert_error(response, 500, "internal_error")
    assert "secret detail" not in response.text
    assert "Traceback" not in response.text
    assert error["message"] == "Something went wrong"

def test_wrong_method_is_405(client):
    assert_error(client.delete("/health"), 405, "method_not_allowed")
