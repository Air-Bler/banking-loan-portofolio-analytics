from fastapi.testclient import TestClient

from api.main import app
from api.queries import get_repository
from tests.api.fakes import FakeRepository


def client() -> TestClient:
    app.dependency_overrides[get_repository] = FakeRepository
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_query_metric_uses_fake_repository() -> None:
    response = client().post(
        "/analytics/query",
        json={"metric": "approval_rate", "group_by": "branch"},
    )

    assert response.status_code == 200
    assert response.json()["rows"][0]["group"] == "BR001"
    assert response.json()["source"] == "fake.gold"


def test_metric_catalogue_returns_fake_metrics() -> None:
    response = client().get("/metadata/metrics")

    assert response.status_code == 200
    assert {metric["name"] for metric in response.json()["metrics"]} >= {
        "approval_rate",
        "applications",
    }


def test_branch_summary_and_not_found() -> None:
    assert client().get("/branches/BR001/summary").status_code == 200
    assert client().get("/branches/BR099/summary").status_code == 404


def test_exceptions_support_filters_and_pagination() -> None:
    response = client().get("/exceptions", params={"rule_id": "DQ002"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["branch_code"] == "BR002"


def test_connected_exposure_and_not_found() -> None:
    response = client().get(
        "/graph/applications/APP-001/connected-exposure"
    )
    assert response.status_code == 200
    assert response.json()["nodes"][0]["id"] == "APP-001"
    assert client().get(
        "/graph/applications/APP-999/connected-exposure"
    ).status_code == 404
