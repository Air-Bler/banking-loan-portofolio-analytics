"""Who may call the API: an X-API-Key on local and dev, an Entra JWT on prod (phase 6).

Keys and tokens are compared, never logged.
"""

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from api.settings import Settings, get_settings

# auto_error=False: a missing key goes through our own 401, in the agreed error format.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_auth(
    request: Request,
    api_key: str | None = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """Router dependency: every route except /health needs it."""
    if settings.app_env == "prod":
        # JWT validation comes in phase 6; until then prod fails closed.
        raise HTTPException(status_code=401, detail="A valid bearer token is required")
    if not api_key or not any(secrets.compare_digest(api_key, key) for key in settings.api_key_list):
        raise HTTPException(status_code=401, detail="A valid X-API-Key header is required")
