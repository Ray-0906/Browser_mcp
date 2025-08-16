import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

# Adjust sys.path to allow imports from the project root (so `app` can be imported)
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.services.browser_service import BrowserService
from app.services.session_service import SessionManager
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.exceptions import (
    BrowserAutomationError,
    SessionNotFoundError,
    NavigationError,
    ElementError,
    InvalidURLError,
    ElementNotFoundError,
    ElementNotInteractableError,
    InvalidSelectorError,
    MCPError,
    ToolNotFoundError,
    InvalidToolArgumentsError
)

# Import necessary types from mcp.server or mcp.types if they are exposed
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types as mcp_types

# Setup logging for the MCP server
setup_logging()
logger = get_logger(__name__)

class BrowserAutomationMCPServer:
    def __init__(self):
        self.browser_service = BrowserService(
            max_browsers=settings.MAX_BROWSER_INSTANCES,
            max_contexts_per_browser=settings.MAX_CONTEXTS_PER_BROWSER,
            headless=settings.BROWSER_HEADLESS,
            timeout=settings.BROWSER_TIMEOUT
        )
        self.session_manager = SessionManager()
        # Initialize Server without 'description' argument
        self.mcp_server = Server(name="browser_automation_mcp_server")

        # Register handlers with the MCP server
        self.mcp_server.list_tools()(self._list_tools)
        self.mcp_server.call_tool(validate_input=True)(self._call_tool)
        self.mcp_server.list_resource_templates()(self._list_resource_templates)
        self.mcp_server.read_resource()(self._read_resource)

    # Underlying implementation for tools
    async def create_session(self, **kwargs) -> Dict[str, Any]:
        session_id = kwargs.get("session_id")
        browser_type = kwargs.get("browser_type")
        headless = kwargs.get("headless")
        viewport_width = kwargs.get("viewport_width")
        viewport_height = kwargs.get("viewport_height")

        try:
            session_info = await self.browser_service.create_session(
                session_id=session_id,
                browser_type=browser_type or "chromium",
                headless=headless,
                viewport_width=viewport_width,
                viewport_height=viewport_height
            )
            await self.session_manager.register_session(session_info["session_id"], session_info)
            logger.info(f"Session {session_info['session_id']} created successfully.")
            return {"session_id": session_info['session_id'], "message": "Session created successfully."}
        except BrowserAutomationError as e:
            logger.error(f"Failed to create session: {e.message}", exc_info=True)
            raise MCPError(f"Failed to create session: {e.message}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during session creation: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def connect_cdp(self, **kwargs) -> Dict[str, Any]:
        session_id = kwargs.get("session_id")
        cdp_url = kwargs.get("cdp_url") or "http://localhost:9222"
        create_new_page = kwargs.get("create_new_page")
        try:
            session_info = await self.browser_service.connect_cdp_session(
                session_id=session_id, cdp_url=cdp_url, create_new_page=create_new_page if create_new_page is not None else True
            )
            await self.session_manager.register_session(session_info["session_id"], session_info)
            logger.info(f"CDP session {session_info['session_id']} connected to {cdp_url}.")
            return {"session_id": session_info['session_id'], "cdp_url": cdp_url, "message": "Connected to visible Chrome via CDP."}
        except BrowserAutomationError as e:
            raise MCPError(f"Failed to connect via CDP: {e.message}", details=e.to_dict())
        except Exception as e:
            raise MCPError(f"Unexpected error: {e}")

    async def launch_visible_chrome(self, **kwargs) -> Dict[str, Any]:
        """Launch a visible Chrome/Edge with remote debugging and optionally auto-connect a session."""
        cdp_port = kwargs.get("cdp_port") or 9222
        user_data_dir = kwargs.get("user_data_dir")
        exe_path = kwargs.get("exe_path")
        additional_args = kwargs.get("additional_args") or []
        auto_connect = kwargs.get("auto_connect") or False
        create_new_page = kwargs.get("create_new_page")
        try:
            launch_info = await self.browser_service.launch_chrome_with_cdp(
                cdp_port=cdp_port,
                user_data_dir=user_data_dir,
                exe_path=exe_path,
                additional_args=additional_args,
            )
            result: Dict[str, Any] = {"cdp_url": launch_info["cdp_url"], "pid": launch_info["pid"], "user_data_dir": launch_info["user_data_dir"], "exe_path": launch_info["exe_path"]}
            if auto_connect:
                # Connect a new MCP session to the launched browser
                session_info = await self.browser_service.connect_cdp_session(
                    session_id=None, cdp_url=launch_info["cdp_url"], create_new_page=create_new_page if create_new_page is not None else True
                )
                await self.session_manager.register_session(session_info["session_id"], session_info)
                result["session_id"] = session_info["session_id"]
            return result
        except BrowserAutomationError as e:
            raise MCPError(f"Failed to launch visible Chrome: {e.message}", details=e.to_dict())
        except Exception as e:
            raise MCPError(f"Unexpected error: {e}")

    async def close_session(self, session_id: str) -> Dict[str, Any]:
        try:
            await self.browser_service.close_session(session_id)
            await self.session_manager.unregister_session(session_id)
            logger.info(f"Session {session_id} closed successfully.")
            return {"session_id": session_id, "message": "Session closed successfully."}
        except SessionNotFoundError as e:
            logger.warning(f"Attempted to close non-existent session {session_id}.")
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except BrowserAutomationError as e:
            logger.error(f"Failed to close session {session_id}: {e.message}", exc_info=True)
            raise MCPError(f"Failed to close session: {e.message}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during session closing: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def navigate(self, session_id: str, url: str, wait_until: Optional[str] = "load") -> Dict[str, Any]:
        try:
            await self.browser_service.navigate(session_id, url, wait_until)
            await self.session_manager.update_session_activity(session_id, "navigate", {"url": url})
            logger.info(f"Session {session_id} navigated to {url}.")
            return {"session_id": session_id, "url": url, "message": "Navigation successful."}
        except (NavigationError, InvalidURLError) as e:
            logger.error(f"Navigation failed for session {session_id} to {url}: {e.message}", exc_info=True)
            raise MCPError(f"Navigation failed: {e.message}", details=e.to_dict())
        except SessionNotFoundError as e:
            logger.warning(f"Navigation attempt on non-existent session {session_id}.")
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during navigation: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def click_element(self, session_id: str, selector: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        try:
            await self.browser_service.click_element(session_id, selector, timeout)
            await self.session_manager.update_session_activity(session_id, "click", {"selector": selector})
            logger.info(f"Session {session_id} clicked element {selector}.")
            return {"session_id": session_id, "selector": selector, "message": "Element clicked successfully."}
        except (ElementError, ElementNotFoundError, ElementNotInteractableError, InvalidSelectorError) as e:
            logger.error(f"Click failed for session {session_id} on {selector}: {e.message}", exc_info=True)
            raise MCPError(f"Click failed: {e.message}", details=e.to_dict())
        except SessionNotFoundError as e:
            logger.warning(f"Click attempt on non-existent session {session_id}.")
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during click: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def type_text(self, session_id: str, selector: str, text: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        try:
            await self.browser_service.type_text(session_id, selector, text, timeout)
            await self.session_manager.update_session_activity(session_id, "type", {"selector": selector, "text_length": len(text)})
            logger.info(f"Session {session_id} typed into element {selector}.")
            return {"session_id": session_id, "selector": selector, "message": "Text typed successfully."}
        except (ElementError, ElementNotFoundError, ElementNotInteractableError, InvalidSelectorError) as e:
            logger.error(f"Type failed for session {session_id} on {selector}: {e.message}", exc_info=True)
            raise MCPError(f"Type failed: {e.message}", details=e.to_dict())
        except SessionNotFoundError as e:
            logger.warning(f"Type attempt on non-existent session {session_id}.")
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during type: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def get_page_content(
        self,
        session_id: str,
        selector: Optional[str] = None,
        content_format: Optional[str] = "html",
        max_chars: Optional[int] = None,
        return_content: Optional[bool] = True,
    ) -> Dict[str, Any]:
        try:
            content = await self.browser_service.get_page_content(session_id, selector=selector, content_format=content_format or "html")
            if isinstance(max_chars, int) and max_chars > 0 and len(content) > max_chars:
                content = content[:max_chars]
            metrics: Dict[str, Any] = {"content_length": len(content), "format": content_format or "html"}
            if selector is not None:
                metrics["selector"] = selector
            await self.session_manager.update_session_activity(session_id, "get_content", metrics)
            logger.info(f"Session {session_id} retrieved page content.")
            result: Dict[str, Any] = {"session_id": session_id, "message": "Page content retrieved successfully.", **metrics}
            if return_content:
                result["content"] = content
            else:
                # Provide a resource URI to read the full or truncated content separately
                fmt = (content_format or "html")
                sel = selector if selector is not None else ""
                result["resource_uri"] = f"page_content/{session_id}?format={fmt}&selector={sel}"
            return result
        except SessionNotFoundError as e:
            logger.warning(f"Get content attempt on non-existent session {session_id}.")
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except BrowserAutomationError as e:
            logger.error(f"Failed to get page content for session {session_id}: {e.message}", exc_info=True)
            raise MCPError(f"Failed to get page content: {e.message}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during get_page_content: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def take_screenshot(
        self,
        session_id: str,
        full_page: Optional[bool] = False,
        encoding: Optional[str] = "base64",
        return_image: Optional[bool] = False,
        image_format: Optional[str] = "png",
        quality: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            # Record activity regardless of return strategy
            await self.session_manager.update_session_activity(
                session_id, "screenshot", {"full_page": full_page, "encoding": encoding, "image_format": image_format}
            )
            logger.info(f"Session {session_id} requested screenshot (return_image={return_image}).")

            result: Dict[str, Any] = {"session_id": session_id, "message": "Screenshot ready."}
            if return_image:
                # Inline image is explicitly requested (beware token usage)
                image_data = await self.browser_service.take_screenshot(session_id, full_page, encoding or "base64")
                result["image_data"] = image_data
                result["mime_type"] = "image/png" if (image_format or "png") == "png" else "image/jpeg"
            else:
                # Provide a resource URI to fetch image separately; avoids dumping base64 into chat
                fp = "true" if full_page else "false"
                fmt = (image_format or "png")
                q = str(quality) if isinstance(quality, int) else ""
                result["resource_uri"] = f"screenshot/{session_id}?full_page={fp}&format={fmt}&quality={q}"
                result["mime_type"] = "image/png" if fmt == "png" else "image/jpeg"
            return result
        except SessionNotFoundError as e:
            logger.warning(f"Screenshot attempt on non-existent session {session_id}.")
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except BrowserAutomationError as e:
            logger.error(f"Failed to take screenshot for session {session_id}: {e.message}", exc_info=True)
            raise MCPError(f"Failed to take screenshot: {e.message}", details=e.to_dict())
        except Exception as e:
            logger.error(f"An unexpected error occurred during screenshot: {e}", exc_info=True)
            raise MCPError(f"Unexpected error: {e}")

    async def get_text_excerpt(self, session_id: str, selector: Optional[str] = None, max_chars: Optional[int] = 5000) -> Dict[str, Any]:
        try:
            text = await self.browser_service.get_page_content(session_id, selector=selector, content_format="text")
            truncated_to: Optional[int] = None
            if isinstance(max_chars, int) and max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars]
                truncated_to = max_chars
            metrics: Dict[str, Any] = {"content_length": len(text)}
            if truncated_to is not None:
                metrics["truncated_to"] = truncated_to
            if selector is not None:
                metrics["selector"] = selector
            await self.session_manager.update_session_activity(session_id, "get_text_excerpt", metrics)
            return {"session_id": session_id, "excerpt": text, "message": "Excerpt retrieved.", **metrics}
        except SessionNotFoundError as e:
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except BrowserAutomationError as e:
            raise MCPError(e.message, details=e.to_dict())
        except Exception as e:
            raise MCPError(f"Unexpected error: {e}")

    async def get_links(self, session_id: str, selector: Optional[str] = None, max_links: Optional[int] = 20) -> Dict[str, Any]:
        try:
            # Use page-level extraction to minimize data
            # Accessing service internals for the page
            if session_id not in self.browser_service.pages:
                raise SessionNotFoundError(session_id)
            page = self.browser_service.pages[session_id]
            scope = selector or "a"
            all_links = await page.eval_on_selector_all(
                scope,
                "els => els.map(e => ({ text: (e.innerText||'').trim(), href: e.getAttribute('href') || '' }))"
            )
            # Filter and limit
            filtered = [l for l in all_links if l.get("href")]
            if isinstance(max_links, int) and max_links > 0:
                filtered = filtered[:max_links]
            await self.session_manager.update_session_activity(session_id, "get_links", {"count": len(filtered), "selector": scope})
            return {"session_id": session_id, "links": filtered, "count": len(filtered), "selector": scope, "message": "Links extracted."}
        except SessionNotFoundError as e:
            raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
        except BrowserAutomationError as e:
            raise MCPError(e.message, details=e.to_dict())
        except Exception as e:
            raise MCPError(f"Unexpected error: {e}")

    # MCP server registration handlers
    async def _list_tools(self) -> List[mcp_types.Tool]:
        """Return the list of tools supported by this server."""
        return [
            mcp_types.Tool(
                name="create_session",
                description="Creates a new browser automation session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Optional: A unique ID for the session. If not provided, one will be generated.", "nullable": True},
                        "browser_type": {"type": "string", "enum": ["chromium", "firefox", "webkit"], "description": "Optional: The type of browser to launch (chromium, firefox, or webkit). Defaults to chromium.", "nullable": True},
                        "headless": {"type": "boolean", "description": "Optional: Whether to run the browser in headless mode. Defaults to server configuration.", "nullable": True},
                        "viewport_width": {"type": "integer", "description": "Optional: The width of the browser viewport.", "nullable": True},
                        "viewport_height": {"type": "integer", "description": "Optional: The height of the browser viewport.", "nullable": True}
                    }
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="launch_visible_chrome",
                description="Launch a visible Chrome/Edge with remote debugging enabled and optionally auto-connect as a session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cdp_port": {"type": "integer", "description": "Remote debugging port (default 9222)", "nullable": True},
                        "user_data_dir": {"type": ["string", "null"], "description": "Profile dir used by the launched browser."},
                        "exe_path": {"type": ["string", "null"], "description": "Path to chrome.exe/msedge.exe. If not provided, common Windows paths and PATH are tried."},
                        "additional_args": {"type": "array", "items": {"type": "string"}, "description": "Extra flags to pass to the browser.", "nullable": True},
                        "auto_connect": {"type": "boolean", "description": "If true, automatically create and return a session attached via CDP.", "nullable": True},
                        "create_new_page": {"type": "boolean", "description": "Open a new tab on connect when auto_connect.", "nullable": True}
                    }
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "cdp_url": {"type": "string"},
                        "pid": {"type": "integer"},
                        "user_data_dir": {"type": "string"},
                        "exe_path": {"type": "string"},
                        "session_id": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="connect_cdp",
                description="Attach to a user-launched Chrome/Chromium in visible mode via CDP (remote debugging).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": ["string", "null"], "description": "Optional: Provide to set a custom session id."},
                        "cdp_url": {"type": "string", "description": "CDP endpoint, e.g., http://localhost:9222", "nullable": True},
                        "create_new_page": {"type": "boolean", "description": "Open a new tab on connect (default true).", "nullable": True}
                    }
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "cdp_url": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="close_session",
                description="Closes an existing browser automation session.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session to close."}
                    },
                    "required": ["session_id"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="navigate",
                description="Navigates the browser in a session to a specified URL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session."},
                        "url": {"type": "string", "description": "The URL to navigate to."},
                        "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"], "description": "Optional: When to consider navigation successful. Defaults to 'load'.", "nullable": True}
                    },
                    "required": ["session_id", "url"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "url": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="click_element",
                description="Clicks an element identified by a CSS selector or XPath.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session."},
                        "selector": {"type": "string", "description": "CSS selector or XPath of the element to click."},
                        "timeout": {"type": "integer", "description": "Optional: Maximum time in milliseconds to wait for the element. Defaults to 30000.", "nullable": True}
                    },
                    "required": ["session_id", "selector"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "selector": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="type_text",
                description="Types text into an element identified by a CSS selector or XPath.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session."},
                        "selector": {"type": "string", "description": "CSS selector or XPath of the element to type into."},
                        "text": {"type": "string", "description": "The text to type."},
                        "timeout": {"type": "integer", "description": "Optional: Maximum time in milliseconds to wait for the element. Defaults to 30000.", "nullable": True}
                    },
                    "required": ["session_id", "selector", "text"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "selector": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="get_page_content",
                description="Retrieve page content as HTML or plain text, optionally scoped to a selector and truncated to avoid token limits.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session."},
                        "selector": {"type": ["string", "null"], "description": "Optional CSS/XPath selector to scope extraction."},
                        "content_format": {"type": "string", "enum": ["html", "text"], "description": "Return HTML or plain text.", "nullable": True},
                        "max_chars": {"type": "integer", "description": "Optional: truncate content to this many characters to avoid token limits.", "nullable": True},
                        "return_content": {"type": "boolean", "description": "Return content inline (true) or provide only metadata and a resource URI (false).", "nullable": True}
                    },
                    "required": ["session_id"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "content": {"type": "string"},
                        "resource_uri": {"type": "string"},
                        "content_length": {"type": "integer"},
                        "format": {"type": "string"},
                        "selector": {"type": ["string", "null"]},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="take_screenshot",
        description="Takes a screenshot of the current page in a session. Defaults to returning a resource URI instead of inline image data to avoid token limits.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "The ID of the session."},
                        "full_page": {"type": "boolean", "description": "Optional: Whether to take a screenshot of the full scrollable page. Defaults to false.", "nullable": True},
            "encoding": {"type": "string", "enum": ["base64", "binary"], "description": "Optional: Encoding when returning inline image_data.", "nullable": True},
            "return_image": {"type": "boolean", "description": "If true, return inline image_data (may be very large). If false, return a resource_uri.", "nullable": True},
            "image_format": {"type": "string", "enum": ["png", "jpeg"], "description": "Image format when generating the screenshot.", "nullable": True},
            "quality": {"type": "integer", "description": "JPEG quality 0-100 (only used when format=jpeg).", "nullable": True}
                    },
                    "required": ["session_id"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
            "image_data": {"type": "string"},
            "resource_uri": {"type": "string"},
            "mime_type": {"type": "string"},
                        "message": {"type": "string"}
                    }
                },
            ),
            mcp_types.Tool(
                name="get_text_excerpt",
                description="Retrieve a truncated plain-text excerpt of the page or a selector to fit token limits.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "selector": {"type": ["string", "null"]},
                        "max_chars": {"type": "integer", "nullable": True}
                    },
                    "required": ["session_id"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "excerpt": {"type": "string"},
                        "content_length": {"type": "integer"},
                        "truncated_to": {"type": "integer"},
                        "selector": {"type": ["string", "null"]},
                        "message": {"type": "string"}
                    }
                }
            ),
            mcp_types.Tool(
                name="get_links",
                description="Extract up to N links (text + href) from the page or a selector to minimize tokens.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "selector": {"type": ["string", "null"], "description": "Optional scope; defaults to 'a'"},
                        "max_links": {"type": "integer", "description": "Limit number of links", "nullable": True}
                    },
                    "required": ["session_id"]
                },
                outputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "links": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "href": {"type": "string"}
                                }
                            }
                        },
                        "count": {"type": "integer"},
                        "selector": {"type": ["string", "null"]},
                        "message": {"type": "string"}
                    }
                }
            ),
        ]

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]):
        """Dispatch tool calls based on name and arguments."""
        try:
            if tool_name == "create_session":
                return await self.create_session(**arguments)
            elif tool_name == "close_session":
                return await self.close_session(**arguments)
            elif tool_name == "navigate":
                return await self.navigate(**arguments)
            elif tool_name == "click_element":
                return await self.click_element(**arguments)
            elif tool_name == "type_text":
                return await self.type_text(**arguments)
            elif tool_name == "get_page_content":
                return await self.get_page_content(**arguments)
            elif tool_name == "take_screenshot":
                return await self.take_screenshot(**arguments)
            elif tool_name == "connect_cdp":
                return await self.connect_cdp(**arguments)
            elif tool_name == "launch_visible_chrome":
                return await self.launch_visible_chrome(**arguments)
            elif tool_name == "get_text_excerpt":
                return await self.get_text_excerpt(**arguments)
            elif tool_name == "get_links":
                return await self.get_links(**arguments)
            else:
                raise ToolNotFoundError(tool_name)
        except BrowserAutomationError as e:
            raise MCPError(e.message, details=e.to_dict())
        except SessionNotFoundError as e:
            raise MCPError(f"Session not found: {arguments.get('session_id','')}", details=e.to_dict())
        except Exception as e:
            raise MCPError(f"Unexpected error: {e}")

    async def _list_resource_templates(self) -> List[mcp_types.ResourceTemplate]:
        return [
            mcp_types.ResourceTemplate(
                name="session_info",
                uriTemplate="session_info/{session_id}",
                description="Provides information about a specific browser session.",
                mimeType="application/json",
            ),
            mcp_types.ResourceTemplate(
                name="active_sessions",
                uriTemplate="active_sessions",
                description="Lists all currently active browser sessions.",
                mimeType="application/json",
            ),
            mcp_types.ResourceTemplate(
                name="page_content",
                uriTemplate="page_content/{session_id}?format={format}&selector={selector}",
                description="Retrieve page content for a session with optional format and selector.",
                mimeType="application/json",
            ),
            mcp_types.ResourceTemplate(
                name="screenshot",
                uriTemplate="screenshot/{session_id}?full_page={full_page}&format={format}&quality={quality}",
                description="Retrieve a screenshot for a session as binary image content.",
                mimeType="application/octet-stream",
            ),
        ]

    async def _read_resource(self, uri: str):
        try:
            if uri.startswith("session_info/"):
                session_id = uri.split("/", 1)[1]
                session_info = await self.session_manager.get_session_info(session_id)
                if not session_info:
                    raise SessionNotFoundError(session_id)
                payload = json.dumps({"session_id": session_id, "info": session_info, "message": "Session info retrieved."})
                return [mcp_types.TextResourceContents(uri=uri, text=payload, mimeType="application/json")]
            elif uri == "active_sessions":
                active_sessions = await self.session_manager.get_all_sessions()
                payload = json.dumps({"sessions": active_sessions, "message": "Active sessions listed."})
                return [mcp_types.TextResourceContents(uri=uri, text=payload, mimeType="application/json")]
            elif uri.startswith("page_content/"):
                # rudimentary query parsing: page_content/{session_id}?format=html&selector=...
                body = uri[len("page_content/"):]
                if "?" in body:
                    sid, qs = body.split("?", 1)
                else:
                    sid, qs = body, ""
                params = {}
                for pair in qs.split("&"):
                    if not pair:
                        continue
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        params[k] = v
                content_format = params.get("format", "html")
                selector = params.get("selector")
                content = await self.browser_service.get_page_content(sid, selector=selector, content_format=content_format)
                payload = json.dumps({"session_id": sid, "format": content_format, "selector": selector, "content": content})
                return [mcp_types.TextResourceContents(uri=uri, text=payload, mimeType="application/json")]
            elif uri.startswith("screenshot/"):
                # screenshot/{session_id}?full_page=true&format=png&quality=80
                body = uri[len("screenshot/"):]
                if "?" in body:
                    sid, qs = body.split("?", 1)
                else:
                    sid, qs = body, ""
                params = {}
                for pair in qs.split("&"):
                    if not pair:
                        continue
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        params[k] = v
                full_page = params.get("full_page", "false").lower() == "true"
                image_format = params.get("format", "png")
                quality = params.get("quality")
                q_int = int(quality) if (quality and quality.isdigit()) else None
                data = await self.browser_service.take_screenshot_bytes(sid, full_page=full_page, image_format=image_format, quality=q_int)
                mime = "image/png" if image_format == "png" else "image/jpeg"
                return [mcp_types.BinaryResourceContents(uri=uri, blob=data, mimeType=mime)]
            else:
                raise ToolNotFoundError(uri)
        except SessionNotFoundError as e:
            raise MCPError(f"Session not found: {uri}", details=e.to_dict())
        except Exception as e:
            raise MCPError(f"Unexpected error: {e}")

    async def run(self):
        logger.info("Starting MCP Server over stdio")
        async with stdio_server() as (read_stream, write_stream):
            init_opts = self.mcp_server.create_initialization_options()
            await self.mcp_server.run(read_stream, write_stream, init_opts)

async def main():
    mcp_server_instance = BrowserAutomationMCPServer()
    await mcp_server_instance.run()

if __name__ == "__main__":
    asyncio.run(main())


