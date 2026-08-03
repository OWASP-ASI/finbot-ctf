# ============================================================
# File: tests/unit/aegis/test_mcp_mocks.py
# Purpose: Unit tests for adversarial MCP server mocks
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 4
# OWASP Category: ASI02, ASI04, ASI05
# ============================================================
"""Tests for adversarial MCP server mocks."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import json

from finbot.aegis.simulator.mcp_mocks.adversarial import (
    AdmServer,
    AdviceServer,
    DataExfiltrationServer,
    FileSystemServer,
    ToolPoisoningServer,
)


@pytest.mark.unit
class TestAdmServer:
    """Test AdmServer (ASI02 - Admin panel manipulation)."""

    def test_adm_server_initialization(self) -> None:
        """Test AdmServer initializes correctly."""
        server = AdmServer()
        assert server.name == "adm-server"
        assert "Admin panel manipulation" in server.description

    @pytest.mark.asyncio
    async def test_adm_server_list_tools(self) -> None:
        """Test AdmServer lists expected tools."""
        server = AdmServer()
        tools = await server._list_tools()
        tool_names = [tool.name for tool in tools]
        assert "get_admin_panel" in tool_names
        assert "modify_user_role" in tool_names
        assert "bypass_mfa" in tool_names

    @pytest.mark.asyncio
    async def test_adm_server_get_admin_panel(self) -> None:
        """Test AdmServer get_admin_panel tool."""
        server = AdmServer()
        result = await server._call_tool("get_admin_panel", {"panel_id": "test_panel"})
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data["panel_id"] == "test_panel"
        assert "admin_users" in data


@pytest.mark.unit
class TestAdviceServer:
    """Test AdviceServer (ASI04 - Financial advice manipulation)."""

    def test_advice_server_initialization(self) -> None:
        """Test AdviceServer initializes correctly."""
        server = AdviceServer()
        assert server.name == "advice-server"
        assert "Financial advice manipulation" in server.description

    @pytest.mark.asyncio
    async def test_advice_server_list_tools(self) -> None:
        """Test AdviceServer lists expected tools."""
        server = AdviceServer()
        tools = await server._list_tools()
        tool_names = [tool.name for tool in tools]
        assert "get_investment_advice" in tool_names
        assert "modify_portfolio_allocation" in tool_names
        assert "inject_malicious_advice" in tool_names

    @pytest.mark.asyncio
    async def test_advice_server_get_investment_advice(self) -> None:
        """Test AdviceServer get_investment_advice tool."""
        server = AdviceServer()
        result = await server._call_tool(
            "get_investment_advice",
            {"user_profile": "conservative", "risk_tolerance": "low"}
        )
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data["advice_id"] == "adv_001"
        assert "recommendation" in data


@pytest.mark.unit
class TestDataExfiltrationServer:
    """Test DataExfiltrationServer (ASI05 - Data exfiltration)."""

    def test_data_exfiltration_server_initialization(self) -> None:
        """Test DataExfiltrationServer initializes correctly."""
        server = DataExfiltrationServer()
        assert server.name == "data-exfil-server"
        assert "Data exfiltration" in server.description

    @pytest.mark.asyncio
    async def test_data_exfiltration_server_list_tools(self) -> None:
        """Test DataExfiltrationServer lists expected tools."""
        server = DataExfiltrationServer()
        tools = await server._list_tools()
        tool_names = [tool.name for tool in tools]
        assert "get_user_data" in tool_names
        assert "export_transaction_history" in tool_names
        assert "steal_credentials" in tool_names

    @pytest.mark.asyncio
    async def test_data_exfiltration_server_get_user_data(self) -> None:
        """Test DataExfiltrationServer get_user_data tool."""
        server = DataExfiltrationServer()
        result = await server._call_tool("get_user_data", {"user_id": "user123"})
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data["user_id"] == "user123"
        assert "exfiltrated_data" in data


@pytest.mark.unit
class TestFileSystemServer:
    """Test FileSystemServer (File system access)."""

    def test_file_system_server_initialization(self) -> None:
        """Test FileSystemServer initializes correctly."""
        server = FileSystemServer()
        assert server.name == "fs-server"
        assert "File system" in server.description

    @pytest.mark.asyncio
    async def test_file_system_server_list_tools(self) -> None:
        """Test FileSystemServer lists expected tools."""
        server = FileSystemServer()
        tools = await server._list_tools()
        tool_names = [tool.name for tool in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_directory" in tool_names

    @pytest.mark.asyncio
    async def test_file_system_server_read_file(self) -> None:
        """Test FileSystemServer read_file tool."""
        server = FileSystemServer()
        result = await server._call_tool("read_file", {"file_path": "/etc/passwd"})
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data["file_path"] == "/etc/passwd"
        assert "content" in data


@pytest.mark.unit
class TestToolPoisoningServer:
    """Test ToolPoisoningServer (Tool poisoning and injection)."""

    def test_tool_poisoning_server_initialization(self) -> None:
        """Test ToolPoisoningServer initializes correctly."""
        server = ToolPoisoningServer()
        assert server.name == "tool-poison-server"
        assert "Tool poisoning" in server.description

    @pytest.mark.asyncio
    async def test_tool_poisoning_server_list_tools(self) -> None:
        """Test ToolPoisoningServer lists expected tools."""
        server = ToolPoisoningServer()
        tools = await server._list_tools()
        tool_names = [tool.name for tool in tools]
        assert "register_malicious_tool" in tool_names
        assert "hook_legitimate_tool" in tool_names
        assert "create_backdoor_tool" in tool_names

    @pytest.mark.asyncio
    async def test_tool_poisoning_server_register_malicious_tool(self) -> None:
        """Test ToolPoisoningServer register_malicious_tool tool."""
        server = ToolPoisoningServer()
        result = await server._call_tool(
            "register_malicious_tool",
            {
                "tool_name": "legitimate_tool",
                "tool_description": "A helpful tool",
                "malicious_payload": "rm -rf /"
            }
        )
        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["tool_name"] == "legitimate_tool"