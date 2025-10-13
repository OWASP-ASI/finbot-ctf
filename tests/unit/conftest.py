"""
Unit test configuration.
"""

import pytest


@pytest.fixture
def fast_client(client):
    """Alias for client fixture for unit tests."""
    return client
