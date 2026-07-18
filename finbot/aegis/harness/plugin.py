# ============================================================
# File: finbot/aegis/harness/plugin.py
# Purpose: pytest-aegis plugin + attack fixtures
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 8
# OWASP Category: -
# ============================================================
"""Pytest plugin for AEGIS red-team testing framework."""

import pytest
from typing import Generator, Any
from unittest.mock import MagicMock

from finbot.aegis.schemas import PolicyAction, ToolInvocationContext
from finbot.aegis.service import AegisEnforcementService


@pytest.fixture
def mock_enforcement_service() -> Generator[AegisEnforcementService, None, None]:
    """Provide a mocked AegisEnforcementService for testing."""
    from unittest.mock import AsyncMock
    
    session = MagicMock(namespace="test_ns", user_id="test_user")
    with pytest.mock.patch("finbot.aegis.service.settings") as mock_settings:
        mock_settings.AEGIS_ENFORCEMENT_MODE = "enforce"
        mock_settings.AEGIS_CASCADE_WINDOW_SECONDS = 30
        mock_settings.AEGIS_CASCADE_MAX_CALLS = 100
        svc = AegisEnforcementService(session_context=session, workflow_id="test_workflow")
        svc._sentinel.record = AsyncMock(return_value=MagicMock())  # pylint: disable=protected-access
        yield svc


@pytest.fixture
def sample_tool_context() -> ToolInvocationContext:
    """Provide a sample tool invocation context for testing."""
    return ToolInvocationContext(
        agent_name="TestAgent",
        tool_name="test_tool",
        tool_source="custom",
        namespace="test_ns",
        user_id="test_user",
        workflow_id="test_workflow",
        arguments={"param": "value"},
    )


@pytest.fixture
def attack_fixtures():
    """Provide common attack payloads for testing."""
    return {
        "rce_attempt": {"script": "rm -rf /"},
        "sql_injection": {"query": "SELECT * FROM users WHERE id = 1 OR 1=1"},
        "path_traversal": {"path": "../../../etc/passwd"},
        "command_injection": {"cmd": "ls; cat /etc/passwd"},
    }


def pytest_configure(config):
    """Register AEGIS-specific markers."""
    config.addinivalue_line("markers", "asi: mark test as related to specific ASI category")
    config.addinivalue_line("markers", "attack: mark test as simulating an attack scenario")
    config.addinivalue_line("markers", "defense: mark test as verifying defensive measures")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location or content."""
    for item in items:
        # Mark tests in asi directories
        if "asi" in str(item.fspath).lower():
            item.add_marker(pytest.mark.asi)
        # Mark tests that mention attack/defense in their name
        if "attack" in item.name.lower():
            item.add_marker(pytest.mark.attack)
        if "defense" in item.name.lower() or "defend" in item.name.lower():
            item.add_marker(pytest.mark.defense)
