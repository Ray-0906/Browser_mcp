from __future__ import annotations

from typing import Any

from app.core.exceptions import MCPError

from .app import mcp
from .context import require_app_context


@mcp.resource(
    "resource://active_sessions",
    description="Lists all currently active browser sessions.",
    mime_type="application/json",
)
async def active_sessions_resource() -> dict[str, Any]:
    app_ctx = require_app_context()
    sessions = await app_ctx.session_manager.get_all_sessions()
    return {"sessions": sessions, "message": "Active sessions listed."}


@mcp.resource(
    "resource://session_info/{session_id}",
    description="Provides information about a specific browser session.",
    mime_type="application/json",
)
async def session_info_resource(
    session_id: str,
) -> dict[str, Any]:
    app_ctx = require_app_context()
    session_info = await app_ctx.session_manager.get_session_info(session_id)
    if not session_info:
        raise MCPError(f"Session not found: {session_id}")
    return {"session_id": session_id, "info": session_info, "message": "Session info retrieved."}
