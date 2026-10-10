"""Prod accepts only a valid Entra ID bearer token; dev and local keep the X-API-Key.

Tokens are signed with a key pair made in the test, and the tenant's key endpoint is replaced
by a fake, so nothing reaches Entra ID.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from api import security
from api.main import app
from api.settings import Settings, get_settings

TENANT, AUDIENCE = "tenant-1", "api-client-id"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
PROD = Settings(app_env="prod", api_keys="test-key", auth_tenant_id=TENANT, auth_audience=AUDIENCE)

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    """Stands in for jwt.PyJWKClient: always hands back the test public key."""

    def __init__(self, error: Exception | None = None):
        self.error = error

    def get_signing_key_from_jwt(self, token):
        if self.error:
            raise self.error
        return jwt.PyJWK.from_dict(jwt.algorithms.RSAAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True))


def token(key=SIGNING_KEY, algorithm="RS256", **claims) -> str:
    now = int(time.time())
    body = {"aud": AUDIENCE, "iss": ISSUER, "iat": now, "exp": now + 600, "sub": "user-1"} | claims
    return jwt.encode({k: v for k, v in body.items() if v is not None}, key, algorithm=algorithm)


@pytest.fixture
def prod(client, monkeypatch):
    """The API as on prod, with FakeRepository and the fake key endpoint; no API key header."""
    app.dependency_overrides[get_settings] = lambda: PROD
    monkeypatch.setattr(security, "jwks_client", lambda tenant: FakeJwks())
    return TestClient(app)


def get(client, bearer_token):
    return client.get("/metadata/metrics", headers={"Authorization": f"Bearer {bearer_token}"})


def assert_401(response):
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- accepted ---


def test_valid_token_is_200(prod):
    assert get(prod, token()).status_code == 200


def test_app_id_uri_audience_is_200(prod):
    assert get(prod, token(aud=f"api://{AUDIENCE}")).status_code == 200


def test_every_protected_route_accepts_the_token(prod):
    headers = {"Authorization": f"Bearer {token()}"}
    assert prod.get("/ready", headers=headers).status_code == 200
    assert prod.post("/analytics/query", json={"metric": "applications"}, headers=headers).status_code == 200


# --- rejected ---


def test_no_token_is_401(prod):
    assert_401(prod.get("/metadata/metrics"))


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer", "Bearer "])
def test_not_a_bearer_token_is_401(prod, header):
    assert_401(prod.get("/metadata/metrics", headers={"Authorization": header}))


def test_api_key_is_not_enough_on_prod(prod):
    assert_401(prod.get("/metadata/metrics", headers={"X-API-Key": "test-key"}))


def test_expired_token_is_401(prod):
    past = int(time.time()) - 3600
    assert_401(get(prod, token(iat=past - 600, exp=past)))


def test_wrong_audience_is_401(prod):
    assert_401(get(prod, token(aud="someone-else")))


def test_wrong_issuer_is_401(prod):
    assert_401(get(prod, token(iss="https://login.microsoftonline.com/other-tenant/v2.0")))


def test_token_signed_with_another_key_is_401(prod):
    assert_401(get(prod, token(key=OTHER_KEY)))


@pytest.mark.parametrize("missing", ["exp", "aud", "iss"])
def test_token_without_a_required_claim_is_401(prod, missing):
    assert_401(get(prod, token(**{missing: None})))


def test_unsigned_token_is_401(prod):
    assert_401(get(prod, token(key=None, algorithm="none")))


def test_hs256_token_is_401(prod):
    assert_401(get(prod, token(key="a-shared-secret-that-is-long-enough-for-hs256", algorithm="HS256")))


def test_garbage_is_401(prod):
    assert_401(get(prod, "not.a.jwt"))


def test_keys_unreachable_is_401(prod, monkeypatch):
    monkeypatch.setattr(security, "jwks_client", lambda tenant: FakeJwks(jwt.PyJWKClientError("unreachable")))
    assert_401(get(prod, token()))


def test_prod_without_auth_settings_fails_closed(prod):
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="prod", api_keys="test-key")
    assert_401(get(prod, token()))


# --- unchanged ---


def test_health_needs_no_token_on_prod(prod):
    assert prod.get("/health").status_code == 200


def test_dev_still_uses_the_api_key(client):
    assert client.get("/metadata/metrics").status_code == 200


def test_docs_offer_a_bearer_field():
    schemes = app.openapi()["components"]["securitySchemes"]
    assert any(s.get("scheme") == "bearer" for s in schemes.values())


def test_token_never_reaches_the_logs(prod, caplog):
    secret = token()
    with caplog.at_level("DEBUG"):
        get(prod, secret)
        get(prod, token(aud="someone-else"))
    assert secret not in caplog.text
    assert "Bearer" not in caplog.text
