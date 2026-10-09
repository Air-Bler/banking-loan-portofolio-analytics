"""Databricks SQL warehouse access: one connection per call, bounded retries and timeout.

Every failure becomes DataUnavailable, which the API answers as 503 data_unavailable.
"""

import re
from datetime import datetime, timezone
from decimal import Decimal

from databricks import sql

from api.errors import DataUnavailable
from api.settings import Settings

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def table(settings: Settings, name: str) -> str:
    """The fully qualified name of a Gold table. Catalog and schema come from settings, never from a request."""
    for part in (settings.databricks_catalog, settings.databricks_schema, name):
        if not _IDENTIFIER.match(part):
            raise DataUnavailable("invalid catalog, schema or table name in the settings")
    return f"`{settings.databricks_catalog}`.`{settings.databricks_schema}`.`{name}`"


def _plain(value):
    """Make a warehouse value JSON-ready: Decimal to float, timestamps to UTC."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)  
    return value


def run_query(settings: Settings, query: str, params: dict | None = None) -> list[dict]:
    """Run one parameterised query (values as :name) and return the rows as dicts."""
    try:
        with sql.connect(
            server_hostname=settings.databricks_host,
            http_path=settings.databricks_http_path,
            access_token=settings.databricks_token.get_secret_value(),
            _retry_stop_after_attempts_count=3,  
            _socket_timeout=30,
        ) as conn, conn.cursor() as cur:
            cur.execute(query, params or {})
            columns = [c[0] for c in cur.description]
            return [{col: _plain(v) for col, v in zip(columns, row)} for row in cur.fetchall()]
    except DataUnavailable:
        raise
    except Exception as exc:
        raise DataUnavailable(str(exc)) from exc
