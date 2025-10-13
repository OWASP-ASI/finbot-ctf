"""
Integration test configuration.
"""

import pytest


@pytest.fixture
def integration_client(client):
    """Alias for client fixture for integration tests."""
    return client
