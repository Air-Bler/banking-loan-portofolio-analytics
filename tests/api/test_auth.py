import pytest
from fastapi.testclient import TestClient

from api.main import app

pytestmark = pytest.mark.skip(reason="the X-API-Key check comes in phase 4 (api/security.py)")

PROTECTED = [
    ("post", "/analytics/query", {"json": {"metric": "applications"}}),
    ("get", "/metadata/metrics", {}),
    ("get", "/branches/BR003/summary", {}),
    ("get", "/exceptions", {}),
    ("get", "/graph/applications/LA000225/connected-exposure", {}),
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