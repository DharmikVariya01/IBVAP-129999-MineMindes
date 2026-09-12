"""Structured logging configuration for IBVAP backend application.

Provides centralized logger setup with sensitive information sanitization
to prevent passwords, full DATABASE_URLs, and tokens from leaking into log records.
"""

import logging
import re
import sys
from typing import Optional


class SensitiveDataFilter(logging.Filter):
    """Filter that sanitizes passwords, credentials, and connection strings from log messages."""

    # Pattern to match credentials in URLs (e.g. postgresql://user:pass@host)
    URL_CREDENTIALS_REGEX = re.compile(r":([^/@:\s]+)@")
    # Pattern to match token-like query params or fields
    TOKEN_REGEX = re.compile(r"(token|secret|password|api_key)=([^\s&]+)", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.URL_CREDENTIALS_REGEX.sub(r":***@", record.msg)
            record.msg = self.TOKEN_REGEX.sub(r"\1=***", record.msg)
        return True


def setup_logging(log_level: Optional[str] = None) -> logging.Logger:
    """Configure structured logging for the IBVAP backend.

    Args:
        log_level: Optional logging level name (e.g. 'INFO', 'DEBUG', 'WARNING').

    Returns:
        Configured root logger for the IBVAP backend.
    """
    level_name = (log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    backend_logger = logging.getLogger("ibvap")
    backend_logger.setLevel(level)

    # Prevent duplicate handlers if setup_logging is called multiple times
    if not backend_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        backend_logger.addHandler(handler)

    return backend_logger


# Default module-level logger
logger = logging.getLogger("ibvap.backend")
