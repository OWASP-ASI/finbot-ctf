"""
Global test configuration for FinBot CTF.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finbot.main import app


@pytest.fixture
def client():
    """Test client for the Main FinBot app."""
    with TestClient(app) as test_client:
        yield test_client


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
        test_path = Path(item.fspath)

        # Mark by directory
        if "unit" in test_path.parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in test_path.parts:
            item.add_marker(pytest.mark.integration)

        if "web" in test_path.parts:
            item.add_marker(pytest.mark.web)
