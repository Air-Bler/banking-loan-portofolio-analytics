"""One error format for every error (docs/contracts.md, section 5):

    {"error": {"code": "not_found", "message": "...", "correlation_id": "...", "details": []}}
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

log = logging.getLogger("api.errors")

CODES = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed", 422: "validation_error"}


class DataUnavailable(Exception):
    """Databricks failed or timed out; the API answers 503 data_unavailable."""


def error_response(request: Request, status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None) 
    body = {"error": {"code": code, "message": message, "correlation_id": correlation_id, "details": details or []}}
    # Set the header here too: a 500 is answered outside the correlation-ID middleware.
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else None
    return JSONResponse(status_code=status, content=body, headers=headers)


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    
    return error_response(request, exc.status_code, CODES.get(exc.status_code, "http_error"), str(exc.detail))


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in err["loc"] if part != "body"), "message": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(request, 422, "validation_error", "The request is not valid", details)


async def data_unavailable(request: Request, exc: DataUnavailable) -> JSONResponse:
    log.warning("data unavailable: %s", type(exc.__cause__ or exc).__name__)  
    return error_response(request, 503, "data_unavailable", "The data source is unavailable, try again later")


async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    # The middleware has already reset its context here, so pass the ID explicitly.
    log.exception("unexpected error", extra={"fields": {"correlation_id": getattr(request.state, "correlation_id", None)}})  
    return error_response(request, 500, "internal_error", "Something went wrong")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(DataUnavailable, data_unavailable)
    app.add_exception_handler(Exception, internal_error)