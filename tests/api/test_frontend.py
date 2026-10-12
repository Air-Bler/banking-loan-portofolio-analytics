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


def test_sign_in_scripts_are_served_from_the_app_itself():
    """MSAL is vendored (no CDN at demo time) and loads before the app."""
    client = TestClient(app)
    page = client.get("/app/").text
    scripts = ["vendor/msal-browser-3.30.0.min.js", "auth.js", "app.js"]
    assert [page.index(f'src="{s}"') for s in scripts] == sorted(page.index(f'src="{s}"') for s in scripts)
    assert "cdn" not in page.lower()
    msal = client.get("/app/vendor/msal-browser-3.30.0.min.js")
    assert msal.status_code == 200 and "msal-browser v3.30.0" in msal.text[:200]
    assert client.get("/app/auth.js").status_code == 200


def test_root_redirect_keeps_the_sign_in_response():
    """Entra returns sign-in to the site root; the redirect to /app/ must not add its own fragment,
    so the browser carries the #code=... fragment over to /app/ for MSAL to read."""
    location = TestClient(app).get("/", follow_redirects=False).headers["location"]
    assert "#" not in location


def test_app_js_never_shadows_the_auth_module():
    """auth.js defines the global `auth`. A local `const auth` in app.js hides it, and reading it inside
    its own initializer throws "Cannot access 'auth' before initialization" (the Status page on prod)."""
    import re
    from pathlib import Path

    app_js = (Path(__file__).parents[2] / "api" / "static" / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"\b(const|let|var|function)\s+auth\b", app_js)
