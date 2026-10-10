"""Who may call the API: an X-API-Key on local and dev, an Entra JWT on prod (phase 6).

Keys and tokens are compared, never logged.
"""

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from api.settings import Settings, get_settings

# auto_error=False: a missing key or token goes through our own 401, in the agreed error format.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer = HTTPBearer(auto_error=False, description="Entra ID access token (prod only)")


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
        # Token verification comes in the next commit; until then prod still fails closed.
        raise HTTPException(status_code=401, detail="A valid bearer token is required")
    if not api_key or not any(secrets.compare_digest(api_key, key) for key in settings.api_key_list):
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required")
