"""Centralized exception handling for IBVAP FastAPI backend.

Provides custom exception handlers that sanitize error outputs, prevent leakage
of database credentials or internal stack traces, and return uniform JSON structures.
"""

import logging
from typing import Any, Dict, List, Union
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.database import (
    DatabaseConfigError,
    DatabaseConnectionError,
    sanitize_error_message,
)

logger = logging.getLogger("ibvap.exceptions")


HTTP_422 = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)



def _sanitize_validation_errors(raw_errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sanitize validation error messages to prevent potential leakages."""
    clean_errors = []
    for err in raw_errors:
        cleaned = dict(err)
        if "msg" in cleaned:
            cleaned["msg"] = sanitize_error_message(cleaned["msg"])
        clean_errors.append(cleaned)
    return clean_errors


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors with sanitized JSON error details."""
    clean_errors = _sanitize_validation_errors(exc.errors())
    logger.warning(
        "Request validation error on %s %s: %s",
        request.method,
        request.url.path,
        clean_errors,
    )
    return JSONResponse(
        status_code=HTTP_422,
        content={
            "error": "Validation Error",
            "detail": clean_errors,
            "status_code": 422,
        },
    )



async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle standard HTTP exceptions with clean JSON responses."""
    detail: Union[str, Any] = exc.detail
    if isinstance(detail, str):
        detail = sanitize_error_message(detail)

    logger.info(
        "HTTP exception on %s %s [Status %d]: %s",
        request.method,
        request.url.path,
        exc.status_code,
        detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": detail if isinstance(detail, str) else "HTTP Exception",
            "detail": detail,
            "status_code": exc.status_code,
        },
        headers=getattr(exc, "headers", None),
    )


async def database_config_exception_handler(
    request: Request, exc: DatabaseConfigError
) -> JSONResponse:
    """Handle database configuration errors safely without leaking credentials."""
    logger.error(
        "Database configuration error on %s %s: %s",
        request.method,
        request.url.path,
        sanitize_error_message(exc),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Database Configuration Error",
            "detail": "Database configuration error encountered.",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


async def database_connection_exception_handler(
    request: Request, exc: DatabaseConnectionError
) -> JSONResponse:
    """Handle database connection failures with safe 503 response."""
    logger.error(
        "Database connection error on %s %s: %s",
        request.method,
        request.url.path,
        sanitize_error_message(exc),
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "Database Unavailable",
            "detail": "Database service is currently unavailable.",
            "status_code": status.HTTP_503_SERVICE_UNAVAILABLE,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected backend exceptions without exposing stack traces to clients."""
    logger.error(
        "Unhandled server exception on %s %s: %s",
        request.method,
        request.url.path,
        sanitize_error_message(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected server error occurred.",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application instance."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(DatabaseConfigError, database_config_exception_handler)
    app.add_exception_handler(DatabaseConnectionError, database_connection_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
