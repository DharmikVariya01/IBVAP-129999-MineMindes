"""Unit tests for FastAPI Backend Foundation (Module 15).

Tests application initialization, metadata, lifespan lifecycle, CORS configuration,
centralized exception handling, structured logging filters, health/readiness endpoints,
and integration with the M13 database layer.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# Ensure backend path is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.api.router import api_router
from app.core.config import Settings, _parse_cors_origins, settings
from app.core.database import DatabaseConfigError, DatabaseConnectionError
from app.core.exceptions import register_exception_handlers
from app.core.logging import SensitiveDataFilter
from app.main import app, create_application


@pytest.fixture
def client():
    """Return a FastAPI TestClient instance."""
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# 1. APPLICATION METADATA & IMPORT TESTS
# ==============================================================================


def test_fastapi_app_imports_and_metadata():
    """Verify application metadata adheres to Module 15 requirements."""
    assert app is not None
    assert isinstance(app, FastAPI)
    assert app.title == "IBVAP — Intelligent Border Video Analysis Platform"
    assert "surveillance platform" in app.description
    assert app.version == "0.1.0"


def test_api_router_included():
    """Verify that centralized api_router is registered in the application."""
    route_paths = [getattr(r, "path", None) for r in app.routes if hasattr(r, "path")]
    # Root, health, and ready endpoints are present
    assert "/" in route_paths
    assert "/health" in route_paths
    assert "/ready" in route_paths

    # Verify api_router is included
    included_routers = [
        getattr(r, "original_router", None)
        for r in app.routes
        if hasattr(r, "original_router")
    ]
    assert api_router in included_routers
    assert api_router.prefix == "/api/v1"



# ==============================================================================
# 2. ROOT & HEALTH ENDPOINTS TESTS
# ==============================================================================


def test_root_endpoint_returns_200(client):
    """Verify GET / returns HTTP 200 with platform information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["platform"] == "IBVAP"
    assert data["version"] == "0.1.0"
    assert "description" in data


def test_health_endpoint_returns_200_and_structure(client):
    """Verify GET /health returns HTTP 200 with backend health status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ibvap-backend"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


# ==============================================================================
# 3. READINESS ENDPOINT TESTS
# ==============================================================================


def test_readiness_healthy_when_database_reachable(client):
    """Verify GET /ready returns HTTP 200 when database connection check succeeds."""
    mock_health = {
        "status": "healthy",
        "database": "ibvap_test_db",
        "server_version": "16.1",
        "driver": "psycopg2",
        "url": "postgresql+psycopg2://user:***@localhost:5432/ibvap_test_db",
        "error": None,
    }

    with patch.object(settings, "database_url", "postgresql+psycopg2://user:pass@localhost:5432/ibvap_test_db"):
        with patch("app.main.check_database_connection", return_value=mock_health):
            response = client.get("/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "reachable"
            assert data["database_name"] == "ibvap_test_db"
            assert data["server_version"] == "16.1"
            # Ensure no credentials or connection strings leaked in body
            assert "pass" not in response.text
            assert "postgresql" not in response.text


def test_readiness_unhealthy_when_database_unreachable(client):
    """Verify GET /ready returns HTTP 503 when database connection fails."""
    mock_health = {
        "status": "unhealthy",
        "database": "ibvap_test_db",
        "server_version": None,
        "driver": "psycopg2",
        "url": "postgresql+psycopg2://user:***@localhost:5432/ibvap_test_db",
        "error": "OperationalError: connection to server at localhost:5432 failed",
    }

    with patch.object(settings, "database_url", "postgresql+psycopg2://user:pass@localhost:5432/ibvap_test_db"):
        with patch("app.main.check_database_connection", return_value=mock_health):
            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "unreachable"
            assert "failed" in data["detail"].lower()
            # Guarantee password or URL string is not in response
            assert "pass" not in response.text
            assert "localhost" not in response.text


def test_readiness_when_database_unconfigured(client):
    """Verify GET /ready returns HTTP 503 when database_url is unset."""
    with patch.object(settings, "database_url", None):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "unconfigured"


def test_readiness_handles_unexpected_exception(client):
    """Verify GET /ready returns HTTP 503 and safe error message on unexpected exception."""
    with patch.object(settings, "database_url", "postgresql+psycopg2://user:pass@localhost:5432/ibvap_test_db"):
        with patch("app.main.check_database_connection", side_effect=RuntimeError("Internal db failure with secret_pass")):
            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "unreachable"
            assert "secret_pass" not in response.text


# ==============================================================================
# 4. CORS CONFIGURATION TESTS
# ==============================================================================


def test_cors_middleware_allows_configured_origin(client):
    """Verify CORS preflight and request headers accept development origins."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_env_parsing():
    """Verify CORS origin parsing supports comma-separated environment variables."""
    with patch.dict("os.environ", {"CORS_ORIGINS": "http://frontend.local:3000, https://surveillance.gov:8443"}):
        origins = _parse_cors_origins()
        assert "http://frontend.local:3000" in origins
        assert "https://surveillance.gov:8443" in origins
        assert len(origins) == 2


# ==============================================================================
# 5. CENTRALIZED EXCEPTION HANDLING TESTS
# ==============================================================================


def test_http_exception_handling(client):
    """Verify standard HTTP exceptions return uniform JSON structures."""
    response = client.get("/api/v1/nonexistent_route")
    assert response.status_code == 404
    data = response.json()
    assert data["status_code"] == 404
    assert data["detail"] == "Not Found"


def test_validation_error_handling():
    """Verify validation errors (422) return sanitized JSON error structure."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/items/{item_id}")
    def read_item(item_id: int):
        return {"item_id": item_id}

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/items/not-an-int")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "Validation Error"
    assert data["status_code"] == 422
    assert isinstance(data["detail"], list)


def test_database_config_error_handling():
    """Verify DatabaseConfigError is caught and returned as clean 500."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/trigger-db-config-error")
    def trigger_error():
        raise DatabaseConfigError("Invalid connection string: postgresql://admin:secretpass@db/test")

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/trigger-db-config-error")
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "Database Configuration Error"
    assert "secretpass" not in response.text


def test_database_connection_error_handling():
    """Verify DatabaseConnectionError is caught and returned as clean 503."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/trigger-db-conn-error")
    def trigger_error():
        raise DatabaseConnectionError("Failed to reach postgresql://admin:secretpass@db/test")

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/trigger-db-conn-error")
    assert response.status_code == 503
    data = response.json()
    assert data["error"] == "Database Unavailable"
    assert "secretpass" not in response.text


def test_unhandled_exception_handling():
    """Verify unhandled exceptions return generic 500 without exposing stack traces."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/trigger-unhandled")
    def trigger_unhandled():
        raise ZeroDivisionError("divide by zero secret_token_xyz")

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/trigger-unhandled")
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "Internal Server Error"
    assert data["detail"] == "An unexpected server error occurred."
    assert "ZeroDivisionError" not in response.text
    assert "secret_token_xyz" not in response.text


# ==============================================================================
# 6. LOGGING & SENSITIVE DATA FILTER TESTS
# ==============================================================================


def test_sensitive_data_filter_masks_credentials():
    """Verify SensitiveDataFilter redacts passwords and secrets from log messages."""
    filt = SensitiveDataFilter()

    # Test URL credentials masking
    record1 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Connecting to postgresql://ibvap_admin:SuperSecret123@10.0.0.1:5432/ibvap_prod",
        args=(), exc_info=None
    )
    filt.filter(record1)
    assert "SuperSecret123" not in record1.msg
    assert ":***@" in record1.msg

    # Test token/secret query parameter masking
    record2 = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Request query token=my_secret_token_9999 and password=userpassword",
        args=(), exc_info=None
    )
    filt.filter(record2)
    assert "my_secret_token_9999" not in record2.msg
    assert "userpassword" not in record2.msg


# ==============================================================================
# 7. LIFECYCLE TESTS
# ==============================================================================


def test_application_lifespan_startup_and_shutdown():
    """Verify application startup and shutdown lifecycle executes and disposes engine."""
    with patch("app.main.dispose_engine") as mock_dispose:
        with TestClient(app) as test_client:
            resp = test_client.get("/health")
            assert resp.status_code == 200

        # On exiting the context manager, shutdown lifecycle should trigger dispose_engine
        mock_dispose.assert_called_once()
