"""Who may call the API: an X-API-Key on local and dev, an Entra ID JWT on prod.

Keys and tokens are compared or verified, never logged.
"""

import secrets
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from api.settings import Settings, get_settings

ENTRA = "https://login.microsoftonline.com"

# auto_error=False: a missing key or token goes through our own 401, in the agreed error format.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer = HTTPBearer(auto_error=False, description="Entra ID access token (prod only)")


@lru_cache(maxsize=4)
def jwks_client(tenant_id: str) -> jwt.PyJWKClient:
    """The tenant's published signing keys, fetched once and cached for an hour."""
    return jwt.PyJWKClient(f"{ENTRA}/{tenant_id}/discovery/v2.0/keys", lifespan=3600, timeout=10)


def verify_entra_token(token: str, settings: Settings) -> dict:
    """Check signature, issuer, audience and expiry of a v2 access token; return its claims."""
    tenant, audience = settings.auth_tenant_id, settings.auth_audience
    if not tenant or not audience:
        raise HTTPException(status_code=401, detail="A valid bearer token is required")  # prod not configured
    try:
        signing_key = jwks_client(tenant).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],  # never "none" or HS256
            audience=[audience, f"api://{audience}"],
            issuer=f"{ENTRA}/{tenant}/v2.0",
            options={"require": ["exp", "iss", "aud"]},
            leeway=60,  # small clock skew
        )
    except jwt.PyJWTError:  # bad signature, expired, wrong aud/iss, keys unreachable, malformed
        raise HTTPException(status_code=401, detail="A valid bearer token is required") from None


def require_auth(
    request: Request,
    api_key: str | None = Depends(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    """Router dependency: every route except /health needs it."""
    if settings.app_env == "prod":
        if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
            raise HTTPException(status_code=401, detail="A valid bearer token is required")
        verify_entra_token(credentials.credentials, settings)
        return
    if not api_key or not any(secrets.compare_digest(api_key, key) for key in settings.api_key_list):
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required")
