import pytest
from fakes import FakeRepository
from fastapi.testclient import TestClient

from api.main import app
from api.queries import get_repository
from api.settings import Settings, get_settings


@pytest.fixture
def client():
    """The API with FakeRepository and test settings swapped in: no Databricks, no real keys."""
    app.dependency_overrides[get_repository] = lambda: FakeRepository()
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev", api_keys="test-key")
    yield TestClient(app, headers={"X-API-Key": "test-key"})
    app.dependency_overrides.clear()


@pytest.fixture
def broken_client(client):
    """Like client, but every repository call raises DataUnavailable (Databricks down)."""
    app.dependency_overrides[get_repository] = lambda: FakeRepository(fail=True)
    return client