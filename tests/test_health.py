"""Foundation health and module import verification tests."""

import asyncio
import sys
from pathlib import Path
import unittest

# Ensure backend and ai_engine paths are in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class TestIBVAPFoundation(unittest.TestCase):
    """Verifies foundation imports, clean dependency structure, and health endpoint."""

    def test_backend_imports(self):
        """Verify all backend packages and app instance import cleanly."""
        import app
        import app.core.config
        import app.api
        import app.models
        import app.schemas
        import app.services
        from app.main import app as fastapi_app

        self.assertIsNotNone(fastapi_app)
        self.assertEqual(app.__version__, "0.1.0")

    def test_ai_engine_imports(self):
        """Verify all ai_engine modules import cleanly without circular dependencies."""
        import ai_engine
        import ai_engine.video_input
        import ai_engine.preprocessing
        import ai_engine.detector
        import ai_engine.tracker
        import ai_engine.event_memory
        import ai_engine.movement
        import ai_engine.zones
        import ai_engine.rules
        import ai_engine.alerts
        import ai_engine.pipeline

        self.assertEqual(ai_engine.__version__, "0.1.0")

    def test_root_endpoint(self):
        """Verify the root endpoint response structure."""
        from app.main import root

        response = asyncio.run(root())
        self.assertEqual(response.get("status"), "online")
        self.assertEqual(response.get("platform"), "IBVAP")
        self.assertIn("version", response)

    def test_health_endpoint(self):
        """Verify the health check endpoint response structure."""
        from app.main import health_check

        response = asyncio.run(health_check())
        self.assertEqual(response.get("status"), "healthy")
        self.assertIn("service", response)
        self.assertIn("version", response)


if __name__ == "__main__":
    unittest.main()
