"""Core configuration, security, and global utilities for IBVAP backend."""

from app.core.config import get_settings, settings
from app.core.database import (
    DatabaseConfigError,
    DatabaseConnectionError,
    check_database_connection,
    create_db_engine,
    dispose_engine,
    get_db,
    get_engine,
    get_session_factory,
    init_db,
    mask_database_url,
    validate_and_normalize_database_url,
)
from app.core.exceptions import register_exception_handlers
from app.core.logging import SensitiveDataFilter, logger, setup_logging

__all__ = [
    "settings",
    "get_settings",
    "DatabaseConfigError",
    "DatabaseConnectionError",
    "mask_database_url",
    "validate_and_normalize_database_url",
    "create_db_engine",
    "get_engine",
    "dispose_engine",
    "get_session_factory",
    "get_db",
    "check_database_connection",
    "init_db",
    "register_exception_handlers",
    "setup_logging",
    "logger",
    "SensitiveDataFilter",
]
