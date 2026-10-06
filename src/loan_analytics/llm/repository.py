"""Read-only access to the approved Gold queries.

``GoldRepository`` is the seam the tools depend on, so business logic is testable without Databricks.
``DatabricksGoldRepository`` runs an ``ApprovedQuery`` on the configured SQL warehouse through the
Databricks SDK statement-execution API, with bound parameters. It never receives free text SQL and
never writes. Failures are mapped to a safe ``ToolExecutionError`` (no SQL, no payloads).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Protocol

from .errors import ToolExecutionError
from .queries import ApprovedQuery
from .settings import GoldSettings

log = logging.getLogger("loan_analytics.llm.repository")

_INT_TYPES = {"BYTE", "SHORT", "INT", "LONG"}
_FLOAT_TYPES = {"FLOAT", "DOUBLE", "DECIMAL"}


class GoldRepository(Protocol):
    def execute(self, query: ApprovedQuery) -> list[dict[str, Any]]: ...


def _convert(value: str | None, type_name: str) -> Any:
    """The SQL statement API returns every value as a string (or null); restore the column type."""
    if value is None:
        return None
    t = (type_name or "").upper()
    if t in _INT_TYPES:
        return int(value)
    if t in _FLOAT_TYPES:
        return float(Decimal(value))
    if t == "BOOLEAN":
        return value.lower() == "true"
    return value


class DatabricksGoldRepository:
    def __init__(self, settings: GoldSettings, client: Any | None = None):
        self._settings = settings
        self._client = client

    def _workspace(self):
        if self._client is None:
            from databricks.sdk import (
                WorkspaceClient,  # credentials come from the SDK's own env/profile handling
            )

            self._client = WorkspaceClient()
        return self._client

    def execute(self, query: ApprovedQuery) -> list[dict[str, Any]]:
        from databricks.sdk.service.sql import (
            ExecuteStatementRequestOnWaitTimeout,
            StatementParameterListItem,
            StatementState,
        )

        s = self._settings
        parameters = [StatementParameterListItem(name=n, value=str(v), type=t) for n, v, t in query.params]
        try:
            resp = self._workspace().statement_execution.execute_statement(
                statement=query.sql,
                warehouse_id=s.warehouse_id,
                catalog=s.catalog,
                schema=s.schema,
                parameters=parameters or None,
                wait_timeout=f"{min(max(s.timeout_seconds, 5), 50)}s",
                on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CANCEL,
                row_limit=query.max_rows,
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a safe, generic error
            log.warning("gold query failed: query=%s error=%s", query.name, type(exc).__name__)
            raise ToolExecutionError("The Gold data source could not be reached.") from None

        state = resp.status.state if resp.status else None
        if state != StatementState.SUCCEEDED:
            code = getattr(getattr(resp.status, "error", None), "error_code", None)
            log.warning("gold query not succeeded: query=%s state=%s code=%s", query.name, state, code)
            raise ToolExecutionError("The Gold query did not complete successfully.")
        if resp.result is not None and getattr(resp.result, "next_chunk_index", None) is not None:
            raise ToolExecutionError("The Gold result is larger than the approved row limit.")

        columns = [(c.name, c.type_name.value if c.type_name else "STRING") for c in resp.manifest.schema.columns]
        rows = resp.result.data_array if resp.result and resp.result.data_array else []
        return [{name: _convert(v, t) for (name, t), v in zip(columns, row)} for row in rows]
