"""IBVAP Backend Application Entrypoint.

Provides the FastAPI application instance with minimal root and health endpoints
to verify environment readiness and foundational server connectivity.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Intelligent Border Video Analysis Platform - Backend API Foundation",
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    """Health check endpoint to verify backend operational readiness."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
