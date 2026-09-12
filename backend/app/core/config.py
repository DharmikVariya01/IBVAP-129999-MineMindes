"""Application configuration settings for IBVAP backend."""

import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env file from backend or project root if present
_backend_dir = Path(__file__).resolve().parent.parent.parent
_root_dir = _backend_dir.parent
load_dotenv(_backend_dir / ".env")
load_dotenv(_root_dir / ".env")


def _parse_cors_origins() -> List[str]:
    """Parse CORS origins from environment variable or provide development defaults."""
    raw = os.getenv("CORS_ORIGINS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


class Settings(BaseModel):
    """IBVAP platform configuration settings."""

    title: str = Field(
        default_factory=lambda: os.getenv(
            "APP_TITLE", "IBVAP — Intelligent Border Video Analysis Platform"
        )
    )
    description: str = Field(
        default_factory=lambda: os.getenv(
            "APP_DESCRIPTION",
            "AI-powered intelligent border video analysis and surveillance platform.",
        )
    )
    service_name: str = Field(
        default_factory=lambda: os.getenv("SERVICE_NAME", "ibvap-backend")
    )
    app_name: str = Field(
        default_factory=lambda: os.getenv(
            "APP_NAME", "IBVAP — Intelligent Border Video Analysis Platform"
        )
    )
    version: str = "0.1.0"
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "true").lower() in ("true", "1", "yes"))
    host: str = Field(default_factory=lambda: os.getenv("APP_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("APP_PORT", "8000")))
    cors_origins: List[str] = Field(default_factory=_parse_cors_origins)

    # Database Configuration (PostgreSQL)
    database_url: Optional[str] = Field(default_factory=lambda: os.getenv("DATABASE_URL"))
    db_pool_size: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "5")))
    db_max_overflow: int = Field(default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "10")))
    db_pool_timeout: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_TIMEOUT", "30")))
    db_pool_recycle: int = Field(default_factory=lambda: int(os.getenv("DB_POOL_RECYCLE", "1800")))
    db_echo: bool = Field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() in ("true", "1", "yes"))
    # Storage Configuration
    evidence_dir: str = Field(default_factory=lambda: os.getenv("EVIDENCE_DIR", str(_root_dir / "evidence")))


def get_settings() -> Settings:
    """Return a fresh Settings instance populated with current environment variables."""
    return Settings()


settings = get_settings()
