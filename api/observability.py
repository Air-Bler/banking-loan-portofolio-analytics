"""Correlation IDs (X-Correlation-ID in and out) and JSON logs that never contain secrets."""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request

HEADER = "X-Correlation-ID"
# Accept the caller's ID only if it is short and plain, so it can't inject lines into the logs.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
log = logging.getLogger("api.access")


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the request's correlation ID."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # The connector is chatty at INFO (connections, retries); keep only its warnings and errors.
    logging.getLogger("databricks").setLevel(logging.WARNING)


def register_correlation_id(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        incoming = request.headers.get(HEADER, "")
        cid = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex[:16]
        request.state.correlation_id = cid
        token = correlation_id.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers[HEADER] = cid
            # Method, path and status only: no headers, no query string, no body.
            log.info("request", extra={"fields": {
                "correlation_id": cid, "method": request.method, "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            }})
            return response
        finally:
            correlation_id.reset(token)
