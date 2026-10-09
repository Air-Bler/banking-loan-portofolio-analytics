import json
import logging

from fastapi.testclient import TestClient

from api.main import app
from api.observability import JsonFormatter
from api.queries import get_repository

HEADER = "X-Correlation-ID"


def test_sent_id_comes_back_in_header_and_body(client):
    response = client.post("/analytics/query", json={"metric": "applications"}, headers={HEADER: "6f1c2a9e"})
    assert response.status_code == 200
    assert response.headers[HEADER] == "6f1c2a9e"
    assert response.json()["correlation_id"] == "6f1c2a9e"


def test_sent_id_comes_back_in_the_error_body(client):
    response = client.get("/branches/BR099/summary", headers={HEADER: "abc-123"})
    assert response.status_code == 404
    assert response.headers[HEADER] == "abc-123"
    assert response.json()["error"]["correlation_id"] == "abc-123"


def test_id_is_generated_when_missing(client):
    response = client.get("/health")
    assert len(response.headers[HEADER]) == 16


def test_unsafe_id_is_replaced(client):
    response = client.get("/health", headers={HEADER: "bad id\twith spaces"})
    assert response.headers[HEADER] != "bad id\twith spaces"


def test_401_and_503_carry_the_id(client, broken_client):
    unauthorized = TestClient(app).get("/exceptions", headers={HEADER: "no-key"})
    assert unauthorized.headers[HEADER] == "no-key"
    assert unauthorized.json()["error"]["correlation_id"] == "no-key"
    down = broken_client.get("/exceptions", headers={HEADER: "down-1"})
    assert down.status_code == 503
    assert down.json()["error"]["correlation_id"] == "down-1"


class ExplodingRepository:
    def query_metric(self, *args, **kwargs):
        raise RuntimeError("boom")


def test_500_carries_the_id(client):
    app.dependency_overrides[get_repository] = lambda: ExplodingRepository()
    response = TestClient(app, headers={"X-API-Key": "test-key"}, raise_server_exceptions=False).post(
        "/analytics/query", json={"metric": "applications"}, headers={HEADER: "err-500"}
    )
    assert response.status_code == 500
    assert response.headers[HEADER] == "err-500"
    assert response.json()["error"]["correlation_id"] == "err-500"


def test_logs_are_json_with_the_id_and_no_secrets(client, caplog):
    with caplog.at_level(logging.INFO, logger="api.access"):
        client.get("/metadata/metrics", headers={HEADER: "log-1", "Authorization": "Bearer secret-token"})
    lines = [json.loads(JsonFormatter().format(r)) for r in caplog.records if r.name == "api.access"]
    assert lines[-1]["correlation_id"] == "log-1"
    assert lines[-1]["path"] == "/metadata/metrics"
    assert lines[-1]["status"] == 200
    text = json.dumps(lines)
    assert "test-key" not in text
    assert "secret-token" not in text
