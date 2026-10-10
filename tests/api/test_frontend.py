from fastapi.testclient import TestClient

from api.main import app


def test_frontend_is_served_without_a_key():
    """The page itself holds no data; every call it makes sends the user's key."""
    client = TestClient(app)
    page = client.get("/app/")
    assert page.status_code == 200
    assert "Loan Portfolio Analytics" in page.text
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/app/styles.css").status_code == 200


def test_root_redirects_to_the_frontend():
    response = TestClient(app).get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


def test_frontend_does_not_open_the_data_routes():
    assert TestClient(app).get("/exceptions").status_code == 401


def test_frontend_is_not_in_the_openapi_schema():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/" not in paths and not any(p.startswith("/app") for p in paths)
