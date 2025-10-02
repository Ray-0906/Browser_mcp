from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, cast

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from app.core.exceptions import MCPError
from app.services.browser_service import BrowserService
from app.services.session_service import SessionManager


@dataclass(slots=True)
class AppContext:
    """Container for dependencies shared across MCP tool handlers."""

    browser_service: BrowserService
    session_manager: SessionManager

logger = logging.getLogger(__name__)

_current_app_context: Optional[AppContext] = None


def require_app_context(ctx: Optional[Context[ServerSession, AppContext]] = None) -> AppContext:
    """Extract the application context from FastMCP request context or global state."""

    if ctx is not None:
        try:
            request_context = ctx.request_context
        except ValueError:
            logger.debug("Context request_context unavailable; falling back to global AppContext")
        else:
            if request_context is not None and request_context.lifespan_context is not None:
                logger.debug("Using request-scoped AppContext from lifespan context")
                return cast(AppContext, request_context.lifespan_context)

    if _current_app_context is None:
        logger.error("AppContext requested but not set globally")
        raise MCPError("Application context not available.")

    logger.debug("Using globally stored AppContext")
    return _current_app_context


def set_current_app_context(app_ctx: AppContext) -> None:
    global _current_app_context
    logger.debug("Setting global AppContext")
    _current_app_context = app_ctx


def clear_current_app_context() -> None:
    global _current_app_context
    logger.debug("Clearing global AppContext")
    _current_app_context = None
