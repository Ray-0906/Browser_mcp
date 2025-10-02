from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.services.browser_service import BrowserService
from app.services.session_service import SessionManager

from .context import AppContext, clear_current_app_context, set_current_app_context


@asynccontextmanager
async def app_lifespan(_: FastMCP[AppContext]) -> AsyncIterator[AppContext]:
    """Manage application-wide resources for the MCP server lifecycle."""

    browser_service = BrowserService(
        max_browsers=settings.MAX_BROWSER_INSTANCES,
        max_contexts_per_browser=settings.MAX_CONTEXTS_PER_BROWSER,
        headless=settings.BROWSER_HEADLESS,
        timeout=settings.BROWSER_TIMEOUT,
    )
    session_manager = SessionManager()

    app_context = AppContext(browser_service=browser_service, session_manager=session_manager)
    set_current_app_context(app_context)

    try:
        yield app_context
    finally:
        clear_current_app_context()
        await browser_service.close_all_browsers()
        await session_manager.close_all_sessions()
