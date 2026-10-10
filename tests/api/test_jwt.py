"""Prod accepts only an Entra ID bearer token; dev and local keep the X-API-Key."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.settings import Settings, get_settings

PROD = Settings(app_env="prod", api_keys="test-key", auth_tenant_id="tenant-1", auth_audience="api-client-id")


@pytest.fixture
def prod(client):
    """The API as on prod, with FakeRepository; no API key header."""
    app.dependency_overrides[get_settings] = lambda: PROD
    return TestClient(app)


def assert_401(response):
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_no_token_is_401(prod):
    assert_401(prod.get("/metadata/metrics"))


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer "])
def test_not_a_bearer_token_is_401(prod, header):
    assert_401(prod.get("/metadata/metrics", headers={"Authorization": header}))


def test_api_key_is_not_enough_on_prod(prod):
    assert_401(prod.get("/metadata/metrics", headers={"X-API-Key": "test-key"}))


def test_health_needs_no_token_on_prod(prod):
    assert prod.get("/health").status_code == 200


def test_docs_offer_a_bearer_field():
    schemes = app.openapi()["components"]["securitySchemes"]
    assert any(s.get("scheme") == "bearer" for s in schemes.values())
