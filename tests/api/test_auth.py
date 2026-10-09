import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.settings import Settings, get_settings

PROTECTED = [
    ("post", "/analytics/query", {"json": {"metric": "applications"}}),
    ("get", "/metadata/metrics", {}),
    ("get", "/branches/BR003/summary", {}),
    ("get", "/exceptions", {}),
    ("get", "/graph/applications/LA000225/connected-exposure", {}),
    ("get", "/ready", {}),
]


@pytest.mark.parametrize("method,path,kwargs", PROTECTED)
def test_missing_key_is_401(client, method, path, kwargs):
    response = getattr(TestClient(app), method)(path, **kwargs)  
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path,kwargs", PROTECTED)
def test_wrong_key_is_401(client, method, path, kwargs):
    response = getattr(TestClient(app, headers={"X-API-Key": "wrong"}), method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_health_needs_no_key():
    assert TestClient(app).get("/health").status_code == 200


def test_second_key_in_the_list_works(client):
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev", api_keys="first, second")
    assert TestClient(app, headers={"X-API-Key": "second"}).get("/metadata/metrics").status_code == 200


def test_no_keys_configured_rejects_everyone(client):
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev", api_keys="")
    assert TestClient(app, headers={"X-API-Key": ""}).get("/metadata/metrics").status_code == 401


def test_prod_does_not_accept_api_keys(client):
    """Until the JWT check exists (phase 6), prod fails closed."""
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="prod", api_keys="test-key")
    response = client.get("/metadata/metrics")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_secrets_are_hidden_when_settings_are_printed():
    settings = Settings(api_keys="test-key", databricks_token="dapi-secret")
    assert "test-key" not in repr(settings)
    assert "dapi-secret" not in repr(settings)
