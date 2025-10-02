from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.core.logging import get_logger, setup_logging

from .context import AppContext
from .lifespan import app_lifespan

# Ensure the project root is available for subpackage imports when executed via stdio
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging once at import time so every module shares the same setup
setup_logging()
logger = get_logger(__name__)

# Instantiate the FastMCP server. Tool/resource registration occurs in configure_app().
mcp: FastMCP[AppContext] = FastMCP(
    name="browser_automation_mcp_server",
    lifespan=app_lifespan,
    instructions="Browser automation tools and resources backed by Playwright",
)


def configure_app() -> FastMCP[AppContext]:
    """Return a fully configured FastMCP application with tools and resources registered."""

    # Import side-effect modules that register tools/resources via decorators.
    from . import resources, tools  # noqa: F401

    logger.debug("FastMCP application configured with tools and resources.")
    return mcp
