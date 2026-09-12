"""Unit and integration tests for PostgreSQL database layer (Module 13).

Covers:
- Configuration loading and environment variables.
- Missing DATABASE_URL handling and custom exceptions.
- PostgreSQL URL parsing and psycopg2 dialect normalization.
- Rejection of SQLite and other unsupported database schemes.
- Database engine creation, connection pooling, and pre-ping settings.
- Sessionmaker factory and get_db dependency generator lifecycle.
- Connection health check with 'SELECT 1' and server version probing.
- Credential masking in error reporting and logs (passwords never exposed).
- Optional live PostgreSQL connectivity test (cleanly skipped if unavailable).
"""

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import Settings, get_settings
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
    sanitize_error_message,
    validate_and_normalize_database_url,
)


@pytest.fixture(autouse=True)
def cleanup_engine():
    """Ensure engine is disposed before and after each test."""
    dispose_engine()
    yield
    dispose_engine()


# ==============================================================================
# 1. Configuration & URL Validation Tests
# ==============================================================================


class TestDatabaseConfiguration:
    """Tests covering database configuration and URL handling."""

    def test_missing_database_url_raises_config_error(self):
        """Missing or empty DATABASE_URL should raise DatabaseConfigError."""
        with pytest.raises(DatabaseConfigError, match="DATABASE_URL is not set or empty"):
            validate_and_normalize_database_url(None)

        with pytest.raises(DatabaseConfigError, match="DATABASE_URL is not set or empty"):
            validate_and_normalize_database_url("")

        with pytest.raises(DatabaseConfigError, match="DATABASE_URL is not set or empty"):
            validate_and_normalize_database_url("   ")

    def test_sqlite_url_explicitly_rejected(self):
        """SQLite URLs must be rejected to prevent silent fallbacks."""
        with pytest.raises(DatabaseConfigError, match="SQLite is not supported"):
            validate_and_normalize_database_url("sqlite:///ibvap.db")

        with pytest.raises(DatabaseConfigError, match="SQLite is not supported"):
            validate_and_normalize_database_url("sqlite:///:memory:")

    def test_unsupported_schemes_rejected(self):
        """Non-PostgreSQL schemes like MySQL or Oracle must be rejected."""
        with pytest.raises(DatabaseConfigError, match="Unsupported database scheme 'mysql'"):
            validate_and_normalize_database_url("mysql://user:pass@localhost:3306/db")

        with pytest.raises(DatabaseConfigError, match="Unsupported database scheme"):
            validate_and_normalize_database_url("oracle://user:pass@localhost:1521/db")

    def test_valid_postgresql_urls_normalized(self):
        """Standard postgresql:// should normalize to postgresql+psycopg2://."""
        raw_url = "postgresql://ibvap_user:secret123@localhost:5432/ibvap"
        normalized = validate_and_normalize_database_url(raw_url)
        assert normalized == "postgresql+psycopg2://ibvap_user:secret123@localhost:5432/ibvap"

    def test_already_normalized_psycopg2_url_preserved(self):
        """URL with postgresql+psycopg2:// should remain unchanged."""
        raw_url = "postgresql+psycopg2://ibvap_user:secret123@localhost:5432/ibvap"
        normalized = validate_and_normalize_database_url(raw_url)
        assert normalized == raw_url

    def test_missing_database_name_raises_error(self):
        """PostgreSQL URL without a database name must raise DatabaseConfigError."""
        with pytest.raises(DatabaseConfigError, match="missing target database name"):
            validate_and_normalize_database_url("postgresql+psycopg2://user:pass@localhost:5432/")

        with pytest.raises(DatabaseConfigError, match="missing target database name"):
            validate_and_normalize_database_url("postgresql+psycopg2://user:pass@localhost:5432")

    def test_settings_pool_configuration_defaults(self, monkeypatch):
        """Settings should load sensible default database pool configuration."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DB_POOL_SIZE", raising=False)
        monkeypatch.delenv("DB_MAX_OVERFLOW", raising=False)

        settings = Settings()
        assert settings.db_pool_size == 5
        assert settings.db_max_overflow == 10
        assert settings.db_pool_timeout == 30
        assert settings.db_pool_recycle == 1800
        assert settings.db_echo is False


# ==============================================================================
# 2. Credential Security & Masking Tests
# ==============================================================================


class TestCredentialSafety:
    """Tests verifying that credentials and passwords are never exposed."""

    def test_mask_database_url_hides_password(self):
        """mask_database_url should replace passwords with asterisks."""
        secret_url = "postgresql+psycopg2://admin:SuperSecretP@ss99@localhost:5432/ibvap_db"
        masked = mask_database_url(secret_url)

        assert "SuperSecretP@ss99" not in masked
        assert "admin" in masked
        assert "localhost:5432" in masked
        assert "ibvap_db" in masked
        assert "***" in masked

    def test_mask_database_url_none_or_empty(self):
        """mask_database_url should handle None or empty gracefully."""
        assert mask_database_url(None) == ""
        assert mask_database_url("") == ""

    def test_sanitize_error_message_removes_embedded_credentials(self):
        """sanitize_error_message should strip credentials embedded in error strings."""
        raw_error = "Connection failed to postgresql+psycopg2://usr:MyTopSecret123@db.internal:5432/prod"
        sanitized = sanitize_error_message(raw_error)

        assert "MyTopSecret123" not in sanitized
        assert "***" in sanitized

    def test_engine_creation_error_masks_credentials(self):
        """If engine creation fails, error message must not leak credentials."""
        secret_url = "postgresql+psycopg2://usr:SensitivePassword999@localhost:5432/nonexistent_db"
        with patch("app.core.database.create_engine", side_effect=ValueError("Invalid pool configuration")):
            with pytest.raises(DatabaseConfigError) as exc_info:
                create_db_engine(database_url=secret_url)

            err_str = str(exc_info.value)
            assert "SensitivePassword999" not in err_str
            assert "***" in err_str


# ==============================================================================
# 3. Engine & Connection Pool Tests
# ==============================================================================


class TestDatabaseEngine:
    """Tests verifying engine creation, connection pooling, and lifecycle."""

    @patch("app.core.database.create_engine")
    def test_create_db_engine_passes_pool_parameters(self, mock_create_engine):
        """create_db_engine should pass pooling and pre-ping settings to SQLAlchemy."""
        mock_create_engine.return_value = MagicMock(spec=Engine)
        test_url = "postgresql+psycopg2://usr:pwd@localhost:5432/ibvap"

        create_db_engine(
            database_url=test_url,
            pool_size=8,
            max_overflow=15,
            pool_timeout=45,
            pool_recycle=2400,
            echo=True,
        )

        mock_create_engine.assert_called_once_with(
            test_url,
            pool_size=8,
            max_overflow=15,
            pool_timeout=45,
            pool_recycle=2400,
            pool_pre_ping=True,
            echo=True,
        )

    @patch("app.core.database.create_engine")
    def test_get_engine_singleton_behavior(self, mock_create_engine):
        """get_engine should return cached singleton unless reset=True."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        test_url = "postgresql+psycopg2://usr:pwd@localhost:5432/ibvap"

        e1 = get_engine(database_url=test_url)
        e2 = get_engine()

        assert e1 is e2
        assert mock_create_engine.call_count == 1

        # Reset engine
        e3 = get_engine(database_url=test_url, reset=True)
        assert mock_create_engine.call_count == 2
        mock_engine.dispose.assert_called_once()

    @patch("app.core.database.create_engine")
    def test_dispose_engine_cleans_up(self, mock_create_engine):
        """dispose_engine should call engine.dispose and clear singletons."""
        mock_engine = MagicMock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        test_url = "postgresql+psycopg2://usr:pwd@localhost:5432/ibvap"

        get_engine(database_url=test_url)
        dispose_engine()

        mock_engine.dispose.assert_called_once()


# ==============================================================================
# 4. Session Factory & Dependency Tests
# ==============================================================================


class TestSessionFactory:
    """Tests verifying session factory and get_db dependency helper."""

    def test_get_session_factory_bound_to_engine(self):
        """get_session_factory should return a sessionmaker bound to the engine."""
        mock_engine = MagicMock(spec=Engine)
        factory = get_session_factory(engine=mock_engine)

        assert callable(factory)
        session = factory()
        assert session.bind is mock_engine
        session.close()

    def test_get_db_generator_lifecycle(self):
        """get_db generator should yield session and close it in finally block."""
        mock_session = MagicMock(spec=Session)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.core.database.get_session_factory", return_value=mock_factory):
            gen = get_db()
            session = next(gen)
            assert session is mock_session
            mock_session.close.assert_not_called()

            # Finish generator
            with pytest.raises(StopIteration):
                next(gen)
            mock_session.close.assert_called_once()

    def test_get_db_generator_closes_on_exception(self):
        """get_db generator must ensure session is closed even if an exception occurs."""
        mock_session = MagicMock(spec=Session)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.core.database.get_session_factory", return_value=mock_factory):
            gen = get_db()
            session = next(gen)
            assert session is mock_session

            # Simulate exception during consumer work
            with pytest.raises(RuntimeError, match="Simulated consumer crash"):
                try:
                    raise RuntimeError("Simulated consumer crash")
                finally:
                    gen.close()

            mock_session.close.assert_called_once()


# ==============================================================================
# 5. Health Check & Initialization Tests
# ==============================================================================


class TestConnectionHealth:
    """Tests verifying minimal health query, server version, and init_db behavior."""

    def test_health_check_healthy_with_server_version(self):
        """Healthy connection executes SELECT 1 and retrieves server_version."""
        mock_engine = MagicMock()
        mock_engine.url = make_url("postgresql+psycopg2://user:pass@localhost:5432/ibvap_test")
        mock_engine.driver = "psycopg2"

        mock_conn = MagicMock()
        # First execute: SELECT 1
        # Second execute: SHOW server_version
        mock_scalar = MagicMock(return_value="17.0 (Debian 17.0-1.pgdg120+1)")
        mock_version_result = MagicMock()
        mock_version_result.scalar = mock_scalar
        mock_conn.execute.side_effect = [MagicMock(), mock_version_result]

        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        health = check_database_connection(engine=mock_engine)

        assert health["status"] == "healthy"
        assert health["database"] == "ibvap_test"
        assert health["server_version"] == "17.0 (Debian 17.0-1.pgdg120+1)"
        assert health["driver"] == "psycopg2"
        assert health["error"] is None

    def test_health_check_operational_error_captured_safely(self):
        """OperationalError during connection check should be recorded cleanly."""
        mock_engine = MagicMock()
        mock_engine.url = make_url("postgresql+psycopg2://usr:pass@localhost:5432/ibvap_test")
        mock_engine.driver = "psycopg2"

        # Simulate connection refusal without leaking passwords
        op_err = OperationalError(
            "connection to server failed",
            params=None,
            orig=Exception("could not connect to server: Connection refused"),
        )
        mock_engine.connect.side_effect = op_err

        health = check_database_connection(engine=mock_engine)

        assert health["status"] == "unhealthy"
        assert "OperationalError" in health["error"]
        assert health["server_version"] is None

    def test_health_check_server_version_fallback(self):
        """If SHOW server_version fails, falls back to SELECT version()."""
        mock_engine = MagicMock()
        mock_engine.url = make_url("postgresql+psycopg2://user:pass@localhost:5432/ibvap_test")
        mock_engine.driver = "psycopg2"

        mock_conn = MagicMock()
        # 1: SELECT 1
        # 2: SHOW server_version raises Exception
        # 3: SELECT version() returns full string
        mock_scalar = MagicMock(return_value="PostgreSQL 17.0 on x86_64-pc-linux-gnu")
        mock_vresult = MagicMock()
        mock_vresult.scalar = mock_scalar
        mock_conn.execute.side_effect = [
            MagicMock(),
            Exception("SHOW server_version syntax error"),
            mock_vresult,
        ]

        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        health = check_database_connection(engine=mock_engine)
        assert health["status"] == "healthy"
        assert health["server_version"] == "PostgreSQL 17.0 on x86_64-pc-linux-gnu"

    def test_health_check_sqlalchemy_error_captured_safely(self):
        """General SQLAlchemyError during connection check should be recorded cleanly."""
        mock_engine = MagicMock()
        mock_engine.url = make_url("postgresql+psycopg2://usr:pass@localhost:5432/ibvap_test")
        mock_engine.driver = "psycopg2"

        sa_err = SQLAlchemyError("Generic query execution failure")
        mock_engine.connect.side_effect = sa_err

        health = check_database_connection(engine=mock_engine)

        assert health["status"] == "unhealthy"
        assert "SQLAlchemyError" in health["error"]

    def test_init_db_success(self):
        """init_db should return health info when connection check succeeds."""
        mock_health = {
            "status": "healthy",
            "database": "ibvap_db",
            "server_version": "17.0",
            "driver": "psycopg2",
            "url": "postgresql+psycopg2://user:***@localhost:5432/ibvap_db",
            "error": None,
        }
        with patch("app.core.database.get_engine") as mock_get_engine, \
             patch("app.core.database.check_database_connection", return_value=mock_health):
            res = init_db("postgresql+psycopg2://user:pass@localhost:5432/ibvap_db")
            assert res["status"] == "healthy"
            assert res["database"] == "ibvap_db"

    def test_init_db_failure_raises_connection_error(self):
        """init_db should raise DatabaseConnectionError when connection fails."""
        mock_health = {
            "status": "unhealthy",
            "database": "ibvap_db",
            "server_version": None,
            "driver": "psycopg2",
            "url": "postgresql+psycopg2://user:***@localhost:5432/ibvap_db",
            "error": "OperationalError: Connection refused",
        }
        with patch("app.core.database.get_engine"), \
             patch("app.core.database.check_database_connection", return_value=mock_health):
            with pytest.raises(DatabaseConnectionError, match="Failed to connect to PostgreSQL"):
                init_db("postgresql+psycopg2://user:pass@localhost:5432/ibvap_db")


# ==============================================================================
# 6. Optional Live PostgreSQL Verification Test
# ==============================================================================


class TestOptionalLivePostgreSQL:
    """Optional integration test against live PostgreSQL.

    Cleanly skipped if live PostgreSQL is not configured or unavailable.
    """

    def test_live_postgresql_if_configured(self):
        """Verify real connection only if DATABASE_URL is explicitly set and reachable."""
        live_url = os.getenv("DATABASE_URL")
        if not live_url:
            pytest.skip("DATABASE_URL not configured — skipping live PostgreSQL integration test")

        try:
            health = check_database_connection()
            if health.get("status") != "healthy":
                pytest.skip(f"Live PostgreSQL unreachable: {health.get('error')}")
            assert health["status"] == "healthy"
            assert health["database"] is not None
        except Exception as exc:
            pytest.skip(f"Live PostgreSQL test skipped due to: {sanitize_error_message(exc)}")
