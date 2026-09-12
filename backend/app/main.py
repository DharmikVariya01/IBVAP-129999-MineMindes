"""IBVAP Backend Application Entrypoint.

Provides the FastAPI application instance with lifecycle management,
centralized API routing, CORS configuration, exception handling,
and operational health/readiness endpoints.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.database import (
    check_database_connection,
    dispose_engine,
    sanitize_error_message,
)
from app.core.exceptions import register_exception_handlers
from app.core.logging import logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    # Startup lifecycle
    setup_logging(log_level="DEBUG" if settings.debug else "INFO")
    logger.info(
        "Starting %s v%s (environment: %s, debug: %s)",
        settings.title,
        settings.version,
        settings.environment,
        settings.debug,
    )

    # Note: Database tables are NOT automatically created here.
    # YOLO models and AI pipelines are strictly decoupled from backend startup.
    yield

    # Shutdown lifecycle
    logger.info("Shutting down %s, releasing backend resources...", settings.title)
    dispose_engine()
    logger.info("Backend resources and database engine disposed safely.")


def create_application() -> FastAPI:
    """Factory function to build and configure the FastAPI application."""
    application = FastAPI(
        title=settings.title,
        description=settings.description,
        version=settings.version,
        lifespan=lifespan,
    )

    # Cross-Origin Resource Sharing (CORS)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register centralized exception handlers
    register_exception_handlers(application)

    # Include centralized API router (for M16+ endpoint expansions)
    application.include_router(api_router)

    return application


app = create_application()


@app.get("/", tags=["System"])
async def root():
    """Root endpoint verifying API availability and basic platform metadata."""
    return {
        "status": "online",
        "platform": "IBVAP",
        "description": "Intelligent Border Video Analysis Platform",
        "version": settings.version,
    }


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint verifying backend operational readiness."""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.version,
        "environment": settings.environment,
    }


@app.get("/ready", tags=["System"])
async def readiness_check():
    """Readiness check verifying backend and PostgreSQL database availability.

    Executes a connection health check via the M13 database interface.
    Returns HTTP 200 if reachable, or HTTP 503 without leaking credentials or secrets.
    """
    try:
        if not settings.database_url:
            logger.warning("Readiness probe failed: DATABASE_URL is not configured.")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "database": "unconfigured",
                    "detail": "Database connection is not configured.",
                },
            )

        health = check_database_connection()
        if health.get("status") == "healthy":
            return {
                "status": "ready",
                "database": "reachable",
                "database_name": health.get("database"),
                "server_version": health.get("server_version"),
            }
        else:
            safe_error = sanitize_error_message(health.get("error", "Connection test failed"))
            logger.warning("Readiness probe database check unhealthy: %s", safe_error)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "database": "unreachable",
                    "detail": "Database connection check failed.",
                },
            )
    except Exception as exc:
        safe_msg = sanitize_error_message(exc)
        logger.error("Readiness check exception: %s", safe_msg)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "unreachable",
                "detail": "Database service is unavailable.",
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
