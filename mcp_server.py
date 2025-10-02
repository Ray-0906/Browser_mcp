from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the project root is importable (needed when launched via stdio runtime).
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enable verbose logging unless already configured
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from browser_mcp import configure_app  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    fastmcp = configure_app()
    logger.info("Starting FastMCP server over stdio")
    fastmcp.run("stdio")


if __name__ == "__main__":
    main()


