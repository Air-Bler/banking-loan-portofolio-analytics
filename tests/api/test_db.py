import pytest
from fastapi.testclient import TestClient

from api import db
from api.errors import DataUnavailable
from api.main import app
from api.settings import Settings, get_settings

CONFIGURED = Settings(databricks_host="adb.example.net", databricks_warehouse_id="abc123", databricks_token="dapi-test")


@pytest.fixture
def warehouse_down(monkeypatch):
    """sql.connect fails as if the warehouse were asleep or unreachable."""
    def boom(**kwargs):
        raise TimeoutError("warehouse asleep")
    monkeypatch.setattr(db.sql, "connect", boom)


def test_retries_and_timeout_are_capped(monkeypatch):
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop")
    monkeypatch.setattr(db.sql, "connect", capture)
    with pytest.raises(DataUnavailable):
        db.run_query(CONFIGURED, "SELECT 1")
    assert seen["_retry_stop_after_attempts_count"] == 3
    assert seen["_socket_timeout"] == 30


def test_rows_come_back_as_dicts(monkeypatch):
    class Cursor:
        description = [("branch_code",), ("applications",)]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, query, params):
            self.params = params

        def fetchall(self):
            return [("BR003", 412)]

    class Connection(Cursor):
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(db.sql, "connect", lambda **kwargs: Connection())
    assert db.run_query(CONFIGURED, "SELECT ...", {"branch": "BR003"}) == [{"branch_code": "BR003", "applications": 412}]


@pytest.mark.parametrize("method, path, body", [
    ("post", "/analytics/query", {"metric": "applications"}),
    ("get", "/branches/BR003/summary", None),
    ("get", "/exceptions", None),
    ("get", "/graph/applications/LA000225/connected-exposure", None),
    ("get", "/ready", None),
])
def test_real_repository_with_warehouse_down_is_503(warehouse_down, method, path, body):
    """No FakeRepository here: the real GoldRepository runs, and Databricks is down."""
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev", api_keys="test-key")
    try:
        client = TestClient(app, headers={"X-API-Key": "test-key"})
        r = client.request(method, path, json=body)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "data_unavailable"


def test_missing_token_never_reaches_the_connector(monkeypatch):
    """Without a token the connector would open a browser login per query; fail fast with 503 instead."""
    def must_not_connect(**kwargs):
        raise AssertionError("sql.connect must not be called without a token")
    monkeypatch.setattr(db.sql, "connect", must_not_connect)
    settings = Settings(databricks_host="adb.example.net", databricks_warehouse_id="abc123", databricks_token="")
    with pytest.raises(DataUnavailable, match="DATABRICKS_TOKEN"):
        db.run_query(settings, "SELECT 1")
