"""
Global test configuration for FinBot CTF.
"""

import concurrent.futures
import sys

import pytest
from fastapi.testclient import TestClient

from finbot.main import app

# Load the Google Sheets pytest plugin
pytest_plugins = ["tests.plugins.google_sheets_reporter.pytest_google_sheets"]


@pytest.fixture
def client():
    """Test client for the Main FinBot app.

    The try/except around __exit__ suppresses a spurious CancelledError raised
    during lifespan teardown on Python 3.13 + anyio 4.x.  Python 3.13 changed
    how concurrent.futures.Future.result() propagates cancellation, which
    breaks starlette's TestClient shutdown path (encode/starlette#2606).
    The tests themselves are unaffected — only the fixture cleanup is patched.
    """
    test_client = TestClient(app)
    test_client.__enter__()
    yield test_client
    try:
        test_client.__exit__(None, None, None)
    except (concurrent.futures.CancelledError, Exception):  # noqa: BLE001
        # On Python 3.13 anyio's BlockingPortal raises CancelledError during
        # shutdown. Swallow it here — lifespan cleanup has already completed.
        if sys.version_info < (3, 13):
            raise


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "smoke: Critical functionality tests")
    config.addinivalue_line("markers", "web: Web application tests")


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on location."""
    _ = config

    for item in items:
        test_path = str(item.fspath)

        if "/unit/" in test_path or "\\unit\\" in test_path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in test_path or "\\integration\\" in test_path:
            item.add_marker(pytest.mark.integration)

        if "/web/" in test_path or "\\web\\" in test_path:
            item.add_marker(pytest.mark.web)

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables before running tests"""
    from finbot.core.data.database import create_tables
    create_tables()
    yield