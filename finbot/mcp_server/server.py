"""FinBot MCP Server -- exposes core FinBot platform actions as MCP tools,
so external MCP-compatible clients (Claude Desktop, Codex Desktop) can
interact with FinBot without going through the browser.

Design notes (from Week 7-8 investigation):
- Runs as its own process on its own port (separate from the main
  uvicorn app), sharing the same DB.
- Auth: MCP clients pass an existing FinBot `session_id` (same one used
  as the browser cookie). We resolve it via the existing, HTTP-agnostic
  SessionManager.get_session_with_vendor_context(), exactly like the
  SessionMiddleware does internally for the web app.
- "start_challenge_session" from the original proposal wording does not
  map to anything in the codebase -- there is no explicit session-start
  concept. Sessions already exist via login; challenges progress
  implicitly as the player interacts with the agent. This tool was
  dropped in favor of the two that map to real functionality.
- submit_tool_call wraps VendorChatAssistant.stream_response(), which is
  the real tool-call entry point (chat -> agent -> tools like FinMail,
  FinDrive, invoices).
- get_scoring_results wraps UserChallengeProgressRepository, the same
  repository the CTF portal's /challenges endpoints use.

LIMITATION: VendorChatAssistant.stream_response() accepts an optional
background_tasks object used only by the start_workflow tool (invoice
reprocessing, vendor re-review). We pass a lightweight asyncio-based
shim instead of FastAPI's BackgroundTasks, since we are not inside a
FastAPI request here. This lets those actions still fire, just without
FastAPI's request-scoped lifecycle.
"""

import json
import logging

from fastmcp import FastMCP

from finbot.core.auth.session import session_manager
from finbot.core.data.database import db_session
from finbot.core.data.repositories import (
    ChallengeRepository,
    UserChallengeProgressRepository,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("FinBot")


class _AsyncTaskShim:
    """Minimal stand-in for FastAPI's BackgroundTasks.

    VendorChatAssistant only calls .add_task(func, **kwargs) -- it does
    not depend on any other BackgroundTasks behavior, so a simple
    asyncio.create_task wrapper is sufficient here.
    """

    def add_task(self, func, *args, **kwargs):
        import asyncio

        asyncio.create_task(func(*args, **kwargs))


def _resolve_session(session_id: str):
    """Resolve a raw session_id into a full SessionContext, or raise."""
    session_context, status = session_manager.get_session_with_vendor_context(
        session_id
    )
    if not session_context:
        raise ValueError(f"Invalid or expired session ({status})")
    return session_context


@mcp.tool()
async def submit_tool_call(session_id: str, message: str) -> dict:
    """Send a message to the FinBot vendor AI assistant, exactly as the
    Vendor Portal chat does. The assistant may call tools (FinMail,
    FinDrive, invoices, etc.) while responding.

    Args:
        session_id: An existing FinBot session ID (same value used as
            the browser session cookie).
        message: The message to send to the assistant.
    """
    from finbot.agents.chat import VendorChatAssistant

    session_context = _resolve_session(session_id)

    assistant = VendorChatAssistant(
        session_context=session_context,
        background_tasks=_AsyncTaskShim(),
    )

    full_text = ""
    tool_calls_made: list[str] = []

    async for chunk in assistant.stream_response(message):
        if not chunk.startswith("data: "):
            continue
        payload = chunk[len("data: "):].strip()
        if not payload:
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "token":
            full_text += event.get("content", "")
        elif event.get("type") == "status":
            tool_calls_made.append(event.get("content", ""))

    return {
        "response": full_text,
        "activity": tool_calls_made,
        "vendor_id": session_context.current_vendor_id,
    }


@mcp.tool()
async def get_scoring_results(session_id: str) -> dict:
    """Retrieve CTF challenge progress and score for the given session.

    Args:
        session_id: An existing FinBot session ID.
    """
    session_context = _resolve_session(session_id)

    with db_session() as db:
        progress_repo = UserChallengeProgressRepository(db, session_context)
        challenge_repo = ChallengeRepository(db)

        all_progress = progress_repo.get_all_progress()
        completed = [p for p in all_progress if p.status == "completed"]

        total_points = 0
        completed_list = []
        for p in completed:
            challenge = challenge_repo.get_challenge(p.challenge_id)
            if not challenge:
                continue
            modifier = p.points_modifier if p.points_modifier is not None else 1.0
            points = int(challenge.points * modifier)
            total_points += points
            completed_list.append(
                {
                    "challenge_id": p.challenge_id,
                    "title": challenge.title,
                    "category": challenge.category,
                    "points": points,
                }
            )

        return {
            "total_points": total_points,
            "completed_count": len(completed_list),
            "attempted_count": len(all_progress),
            "completed_challenges": completed_list,
        }
