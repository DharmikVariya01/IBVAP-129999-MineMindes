"""PostgreSQL database engine, session management, and health checking for IBVAP.

This module provides the core database connectivity layer strictly for Module 13.
It implements:
- SQLAlchemy engine creation with connection pooling and pre-ping.
- Strict PostgreSQL validation (disallowing SQLite or unsupported schemes).
- Safe credential masking for logging and error reporting.
- Session factory and get_db session dependency generator.
- Connection health verification executing 'SELECT 1'.
- Custom exceptions: DatabaseConfigError, DatabaseConnectionError.

NOTE: Application data models (cameras, alerts, events, evidence) belong to
subsequent modules and are strictly not defined here.
"""

import logging
import os
import re
from typing import Any, Dict, Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger("ibvap.database")


class DatabaseConfigError(Exception):
    """Raised when database configuration is missing, invalid, or unsupported."""


class DatabaseConnectionError(Exception):
    """Raised when PostgreSQL database connection or health check fails."""


# Module-level singletons
_engine_instance: Optional[Engine] = None
_session_factory_instance: Optional[sessionmaker] = None


def mask_database_url(url: Optional[str]) -> str:
    """Mask credentials in a database connection string for safe logging/display.

    Ensures that usernames and passwords are never exposed in logs or exception messages.

    Args:
        url: Raw database connection URL string.

    Returns:
        Sanitized URL string with passwords hidden, or empty string if None.
    """
    if not url:
        return ""
    try:
        u = make_url(url)
        return u.render_as_string(hide_password=True)
    except Exception:
        # Fallback regex masking for malformed connection strings
        return re.sub(r":([^/@]+)@", ":***@", str(url))


def sanitize_error_message(error: Any) -> str:
    """Sanitize an exception message to ensure no passwords or secrets leak.

    Args:
        error: The exception or error string.

    Returns:
        Clean, sanitized error string.
    """
    msg = str(error)
    # Mask any password-like patterns in URLs embedded in error strings
    msg = re.sub(r":([^/@:\s]+)@", ":***@", msg)
    return msg


def validate_and_normalize_database_url(url: Optional[str]) -> str:
    """Validate that the URL is a syntactically valid PostgreSQL connection string.

    Enforces PostgreSQL usage and explicitly rejects SQLite or other unsupported dialects.
    Normalizes 'postgresql://' to 'postgresql+psycopg2://'.

    Args:
        url: Raw database connection URL.

    Returns:
        Normalized PostgreSQL connection URL with psycopg2 dialect.

    Raises:
        DatabaseConfigError: If URL is missing, invalid, or not PostgreSQL.
    """
    if not url or not str(url).strip():
        raise DatabaseConfigError(
            "DATABASE_URL is not set or empty. A valid PostgreSQL connection string is required."
        )

    clean_url = str(url).strip()

    # Disallow SQLite explicitly
    if clean_url.lower().startswith("sqlite"):
        raise DatabaseConfigError(
            "SQLite is not supported. IBVAP requires a PostgreSQL database (e.g. postgresql+psycopg2://...)."
        )

    # Validate scheme
    if not (clean_url.startswith("postgresql://") or clean_url.startswith("postgresql+psycopg2://")):
        # Check if it starts with another dialect
        scheme = clean_url.split("://", 1)[0] if "://" in clean_url else "unknown"
        raise DatabaseConfigError(
            f"Unsupported database scheme '{scheme}'. Only PostgreSQL ('postgresql+psycopg2://') is supported."
        )

    # Normalize postgresql:// to postgresql+psycopg2://
    if clean_url.startswith("postgresql://"):
        clean_url = "postgresql+psycopg2://" + clean_url[len("postgresql://") :]

    # Validate syntax via SQLAlchemy URL parser
    try:
        parsed = make_url(clean_url)
    except Exception as exc:
        safe_url = mask_database_url(clean_url)
        raise DatabaseConfigError(
            f"Invalid DATABASE_URL syntax ({safe_url}): {sanitize_error_message(exc)}"
        ) from exc

    if not parsed.database:
        safe_url = mask_database_url(clean_url)
        raise DatabaseConfigError(
            f"Invalid DATABASE_URL: missing target database name in '{safe_url}'."
        )

    return clean_url


def create_db_engine(
    database_url: Optional[str] = None,
    pool_size: Optional[int] = None,
    max_overflow: Optional[int] = None,
    pool_timeout: Optional[int] = None,
    pool_recycle: Optional[int] = None,
    echo: Optional[bool] = None,
) -> Engine:
    """Create a new SQLAlchemy engine for PostgreSQL.

    Configures connection pooling, pre-ping verification, and driver settings.

    Args:
        database_url: Raw or normalized PostgreSQL URL. If None, loaded from settings.
        pool_size: Connection pool size.
        max_overflow: Maximum connections allowed beyond pool_size.
        pool_timeout: Timeout in seconds for obtaining a connection from pool.
        pool_recycle: Seconds after which connections are recycled.
        echo: If True, SQLAlchemy logs SQL statements.

    Returns:
        SQLAlchemy Engine configured for PostgreSQL.

    Raises:
        DatabaseConfigError: If configuration is invalid.
    """
    settings = get_settings()

    raw_url = database_url or settings.database_url
    normalized_url = validate_and_normalize_database_url(raw_url)

    _pool_size = pool_size if pool_size is not None else settings.db_pool_size
    _max_overflow = max_overflow if max_overflow is not None else settings.db_max_overflow
    _pool_timeout = pool_timeout if pool_timeout is not None else settings.db_pool_timeout
    _pool_recycle = pool_recycle if pool_recycle is not None else settings.db_pool_recycle
    _echo = echo if echo is not None else settings.db_echo

    try:
        engine = create_engine(
            normalized_url,
            pool_size=_pool_size,
            max_overflow=_max_overflow,
            pool_timeout=_pool_timeout,
            pool_recycle=_pool_recycle,
            pool_pre_ping=True,
            echo=_echo,
        )
        return engine
    except Exception as exc:
        safe_url = mask_database_url(normalized_url)
        raise DatabaseConfigError(
            f"Failed to create database engine for '{safe_url}': {sanitize_error_message(exc)}"
        ) from exc


def get_engine(database_url: Optional[str] = None, reset: bool = False, **kwargs: Any) -> Engine:
    """Retrieve or create the singleton SQLAlchemy database engine.

    Args:
        database_url: Optional override connection URL.
        reset: If True, disposes existing engine and creates a fresh instance.
        **kwargs: Additional engine keyword arguments.

    Returns:
        Cached or newly created Engine instance.
    """
    global _engine_instance, _session_factory_instance

    if reset or _engine_instance is None or database_url is not None:
        if _engine_instance is not None:
            dispose_engine()
        _engine_instance = create_db_engine(database_url=database_url, **kwargs)
        _session_factory_instance = None

    return _engine_instance


def dispose_engine() -> None:
    """Safely dispose of the singleton database engine and reset session factory."""
    global _engine_instance, _session_factory_instance

    if _engine_instance is not None:
        try:
            _engine_instance.dispose()
        except Exception as exc:
            logger.warning("Error disposing database engine: %s", sanitize_error_message(exc))
        _engine_instance = None
    _session_factory_instance = None


def get_session_factory(
    engine: Optional[Engine] = None, reset: bool = False
) -> sessionmaker:
    """Return a SQLAlchemy sessionmaker factory bound to the engine.

    Args:
        engine: Optional Engine instance. Defaults to singleton engine.
        reset: If True, recreate the factory instance.

    Returns:
        Configured sessionmaker instance.
    """
    global _session_factory_instance

    target_engine = engine or get_engine()

    if engine is not None:
        return sessionmaker(
            bind=target_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    if reset or _session_factory_instance is None:
        _session_factory_instance = sessionmaker(
            bind=target_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    return _session_factory_instance


try:
    from fastapi import Depends
    _engine_default: Any = Depends(lambda: None)
except ImportError:  # pragma: no cover
    _engine_default = None


def get_db(engine: Optional[Engine] = _engine_default) -> Generator[Session, None, None]:
    """Database session dependency generator for FastAPI or background workers.

    Yields a SQLAlchemy Session and guarantees that the session is closed upon completion.

    Args:
        engine: Optional Engine override.

    Yields:
        Active SQLAlchemy Session.
    """
    actual_engine = None if hasattr(engine, "dependency") else engine
    factory = get_session_factory(engine=actual_engine)
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


def check_database_connection(engine: Optional[Engine] = None) -> Dict[str, Any]:
    """Execute a minimal PostgreSQL health query and return structured status.

    Executes 'SELECT 1' and retrieves database name and PostgreSQL server version.
    Never exposes passwords in returned diagnostics or logs.

    Args:
        engine: Optional Engine to check. Defaults to singleton engine.

    Returns:
        dict containing:
            - status: "healthy" | "unhealthy"
            - database: database name string or None
            - server_version: PostgreSQL server version string or None
            - driver: driver name string or None
            - url: masked URL string
            - error: sanitized error string if failed, else None
    """
    target_engine = engine or get_engine()
    masked_url = mask_database_url(str(target_engine.url))

    result: Dict[str, Any] = {
        "status": "unhealthy",
        "database": target_engine.url.database,
        "server_version": None,
        "driver": target_engine.driver,
        "url": masked_url,
        "error": None,
    }

    try:
        with target_engine.connect() as conn:
            # Minimal health probe
            conn.execute(text("SELECT 1"))

            # Server version check (PostgreSQL specific)
            try:
                version_val = conn.execute(text("SHOW server_version")).scalar()
                result["server_version"] = str(version_val) if version_val is not None else None
            except Exception:
                try:
                    version_val = conn.execute(text("SELECT version()")).scalar()
                    result["server_version"] = str(version_val) if version_val is not None else None
                except Exception:
                    result["server_version"] = "unknown"

            result["status"] = "healthy"
            return result

    except OperationalError as op_err:
        err_msg = sanitize_error_message(op_err)
        result["error"] = f"OperationalError: {err_msg}"
        logger.error("PostgreSQL connection check failed: %s", result["error"])
        return result
    except SQLAlchemyError as sa_err:
        err_msg = sanitize_error_message(sa_err)
        result["error"] = f"SQLAlchemyError: {err_msg}"
        logger.error("PostgreSQL query check failed: %s", result["error"])
        return result
    except Exception as exc:
        err_msg = sanitize_error_message(exc)
        result["error"] = f"Unexpected error: {err_msg}"
        logger.error("Unexpected error during connection check: %s", result["error"])
        return result


def init_db(database_url: Optional[str] = None) -> Dict[str, Any]:
    """Initialize the database engine and verify connectivity.

    Reads DATABASE_URL (or parameter), creates/validates the engine, and performs
    a connectivity health check. Raises DatabaseConnectionError if unavailable.

    Args:
        database_url: Optional PostgreSQL connection URL.

    Returns:
        Dict with connection health information on success.

    Raises:
        DatabaseConfigError: If configuration is missing or invalid.
        DatabaseConnectionError: If connection cannot be established.
    """
    engine = get_engine(database_url=database_url, reset=True)
    health = check_database_connection(engine=engine)

    if health.get("status") != "healthy":
        safe_url = health.get("url", "unknown")
        err = health.get("error", "Unknown connection failure")
        raise DatabaseConnectionError(
            f"Failed to connect to PostgreSQL database at {safe_url}: {err}"
        )

    logger.info(
        "Successfully connected to PostgreSQL database '%s' (server version: %s)",
        health.get("database"),
        health.get("server_version"),
    )
    return health
