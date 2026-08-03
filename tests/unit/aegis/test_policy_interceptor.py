# ============================================================
# File: tests/unit/aegis/test_policy_interceptor.py
# Package: tests.unit.aegis
# Purpose: Policy gate tests for MCPPolicyInterceptor
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 7
# OWASP Category: ASI02 Tool Misuse, ASI03 Excessive Agency, ASI07 Prompt Injection
# ============================================================
"""Unit tests for the MCP Policy Interceptor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from finbot.aegis.policy.agent_profiles import AGENT_PROFILES, DataAnalystProfile
from finbot.aegis.policy.interceptor import MCPPolicyInterceptor
from finbot.aegis.policy.memory import MemoryNamespaceManager


@pytest.fixture
def data_analyst_profile():
    """Fixture providing a data analyst agent profile."""
    return AGENT_PROFILES["data_analyst"]


@pytest.fixture
def memory_manager():
    """Fixture providing a memory namespace manager."""
    return MemoryNamespaceManager()


@pytest.fixture
def policy_interceptor(data_analyst_profile, memory_manager):
    """Fixture providing an MCP policy interceptor for testing."""
    return MCPPolicyInterceptor(
        agent_profile=data_analyst_profile,
        memory_manager=memory_manager,
    )


@pytest.mark.asyncio
async def test_interceptor_allows_permitted_tool(policy_interceptor):
    """Test that the interceptor allows permitted tools."""
    # Arrange
    mock_next_handler = AsyncMock(return_value={"result": "success"})
    
    # Act
    result = await policy_interceptor.intercept_tool_call(
        tool_name="database:query",
        tool_args={"query": "SELECT * FROM users"},
        tool_source="finbot",
        next_handler=mock_next_handler,
    )
    
    # Assert
    assert result == {"result": "success"}
    mock_next_handler.assert_called_once_with(
        "database:query",
        {"query": "SELECT * FROM users"},
        "finbot",
    )


@pytest.mark.asyncio
async def test_interceptor_blocks_non_permitted_tool(policy_interceptor):
    """Test that the interceptor blocks non-permitted tools."""
    # Arrange
    mock_next_handler = AsyncMock()
    
    # Act & Assert
    with pytest.raises(PermissionError, match="not authorized to use tool"):
        await policy_interceptor.intercept_tool_call(
            tool_name="system:shell",
            tool_args={"command": "ls -la"},
            tool_source="finbot",
            next_handler=mock_next_handler,
        )
    
    # Verify the handler was not called
    mock_next_handler.assert_not_called()


@pytest.mark.asyncio
async def test_interceptor_blocks_due_to_resource_limits(policy_interceptor):
    """Test that the interceptor blocks when resource limits are exceeded."""
    # Arrange
    # Set up the interceptor to have exceeded limits
    policy_interceptor._execution_count = 100  # Exceeds the 60/min limit for filesystem:read
    mock_next_handler = AsyncMock(return_value={"data": []})
    
    # Act & Assert
    with pytest.raises(PermissionError, match="Resource limits exceeded"):
        await policy_interceptor.intercept_tool_call(
            tool_name="filesystem:read",
            tool_args={"path": "/tmp/data.txt"},
            tool_source="finbot",
            next_handler=mock_next_handler,
        )
    
    # Verify the handler was not called
    mock_next_handler.assert_not_called()


def test_agent_profile_allows_tool(data_analyst_profile):
    """Test that agent profile correctly identifies allowed tools."""
    # Assert
    assert data_analyst_profile.allows_tool("database:query") is True
    assert data_analyst_profile.allows_tool("data:visualize") is True
    assert data_analyst_profile.allows_tool("filesystem:read") is True
    assert data_analyst_profile.allows_tool("system:shell") is False


def test_agent_profile_tool_limits(data_analyst_profile):
    """Test that agent profile correctly returns tool limits."""
    # Act & Assert
    assert data_analyst_profile.get_tool_limit("database:query") == 30
    assert data_analyst_profile.get_tool_limit("data:visualize") == 10
    assert data_analyst_profile.get_tool_limit("filesystem:read") == 60
    assert data_analyst_profile.get_tool_limit("nonexistent:tool") == 0


def test_policy_interceptor_metrics(policy_interceptor):
    """Test that the interceptor reports correct metrics."""
    # Act
    metrics = policy_interceptor.get_metrics()
    
    # Assert
    assert metrics["agent"] == "data_analyst"
    assert metrics["total_executions"] == 0
    assert metrics["total_violations"] == 0
    assert metrics["violation_rate"] == 0.0
    assert metrics["policy_gradient_weight"] == 0.1


if __name__ == "__main__":
    pytest.main([__file__])
