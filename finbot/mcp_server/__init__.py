"""FinBot MCP Server -- exposes core FinBot platform actions (starting
challenge sessions, submitting tool calls, retrieving scoring results)
as an MCP server, so FinBot can be used from MCP-compatible AI clients
like Claude Desktop and Codex Desktop.

This is the inverse of finbot/mcp/, which contains mock external MCP
servers (FinDrive, FinMail, FinStripe, etc.) that FinBot's own agents
call out to as tools. This package instead makes FinBot itself
reachable as an MCP server.
"""
