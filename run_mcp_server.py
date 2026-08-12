"""Entry point for the FinBot MCP server.

Runs FinBot as an MCP server on its own port, separate from the main
FastAPI app (run.py). Exposes core platform actions (submit_tool_call,
get_scoring_results) to MCP-compatible clients like Claude Desktop and
Codex Desktop.

Usage:
    python run_mcp_server.py
"""

from finbot.mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8100)
