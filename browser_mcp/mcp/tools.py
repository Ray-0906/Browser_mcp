from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.resources import FunctionResource
from mcp.server.session import ServerSession

from app.core.exceptions import (
    BrowserAutomationError,
    ElementError,
    ElementNotFoundError,
    ElementNotInteractableError,
    InvalidSelectorError,
    InvalidURLError,
    MCPError,
    NavigationError,
    SessionNotFoundError,
)

from .app import logger, mcp
from .context import AppContext, require_app_context


@mcp.tool(description="Creates a new browser automation session.")
async def create_session(
    session_id: Optional[str] = None,
    browser_type: Optional[str] = "chromium",
    headless: Optional[bool] = None,
    viewport_width: Optional[int] = None,
    viewport_height: Optional[int] = None,
    use_cdp: Optional[bool] = None,
    cdp_url: Optional[str] = None,
    create_new_page: Optional[bool] = True,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        requested_cdp = bool(use_cdp)
        auto_detect_cdp = use_cdp is None
        resolved_cdp_url = cdp_url or "http://localhost:9222"
        session_info: Dict[str, Any]
        used_cdp = False

        if requested_cdp or auto_detect_cdp:
            try:
                session_info = await app_ctx.browser_service.connect_cdp_session(
                    session_id=session_id,
                    cdp_url=resolved_cdp_url,
                    create_new_page=True if create_new_page is None else create_new_page,
                )
                used_cdp = True
                message = "Connected to existing browser via CDP."
            except BrowserAutomationError as e:
                if requested_cdp:
                    logger.error("Failed to connect via CDP at %s: %s", resolved_cdp_url, e.message, exc_info=True)
                    raise MCPError(f"Failed to connect via CDP: {e.message}", details=e.to_dict())
                logger.debug("CDP auto-detection failed at %s: %s. Falling back to launching a browser.", resolved_cdp_url, e.message)
            except Exception as e:  # noqa: BLE001
                if requested_cdp:
                    logger.error("Unexpected error during CDP connection attempt: %s", e, exc_info=True)
                    raise MCPError(f"Unexpected error during CDP connection: {e}")
                logger.debug("CDP auto-detection raised %r; falling back to new session.", e)

        if not used_cdp:
            session_info = await app_ctx.browser_service.create_session(
                session_id=session_id,
                browser_type=browser_type or "chromium",
                headless=headless,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
            )
            message = "Session created successfully."
        await app_ctx.session_manager.register_session(session_info["session_id"], session_info)
        logger.info(
            "Session %s ready via %s.",
            session_info["session_id"],
            "CDP" if used_cdp else session_info.get("browser_type", browser_type),
        )
        result: Dict[str, Any] = {"session_id": session_info["session_id"], "message": message}
        if used_cdp:
            result["cdp_url"] = session_info.get("cdp_url", resolved_cdp_url)
        return result
    except BrowserAutomationError as e:
        logger.error("Failed to create session: %s", e.message, exc_info=True)
        raise MCPError(f"Failed to create session: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during session creation: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(
    description="Attach to a user-launched Chrome/Chromium in visible mode via CDP (remote debugging)."
)
async def connect_cdp(
    session_id: Optional[str] = None,
    cdp_url: Optional[str] = "http://localhost:9222",
    create_new_page: Optional[bool] = True,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        session_info = await app_ctx.browser_service.connect_cdp_session(
            session_id=session_id,
            cdp_url=cdp_url or "http://localhost:9222",
            create_new_page=True if create_new_page is None else create_new_page,
        )
        await app_ctx.session_manager.register_session(session_info["session_id"], session_info)
        logger.info("CDP session %s connected to %s.", session_info["session_id"], session_info["cdp_url"])
        return {
            "session_id": session_info["session_id"],
            "cdp_url": session_info["cdp_url"],
            "message": "Connected to visible Chrome via CDP.",
        }
    except BrowserAutomationError as e:
        logger.error("Failed to connect via CDP: %s", e.message, exc_info=True)
        raise MCPError(f"Failed to connect via CDP: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during CDP connection: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(
    description="Launch a visible Chrome/Edge with remote debugging enabled and optionally auto-connect as a session."
)
async def launch_visible_chrome(
    cdp_port: Optional[int] = 9222,
    user_data_dir: Optional[str] = None,
    exe_path: Optional[str] = None,
    additional_args: Optional[List[str]] = None,
    auto_connect: Optional[bool] = False,
    create_new_page: Optional[bool] = True,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        launch_info = await app_ctx.browser_service.launch_chrome_with_cdp(
            cdp_port=cdp_port or 9222,
            user_data_dir=user_data_dir,
            exe_path=exe_path,
            additional_args=additional_args,
        )
        result: Dict[str, Any] = {
            "cdp_url": launch_info["cdp_url"],
            "pid": launch_info["pid"],
            "user_data_dir": launch_info["user_data_dir"],
            "exe_path": launch_info["exe_path"],
        }
        if auto_connect:
            session_info = await app_ctx.browser_service.connect_cdp_session(
                session_id=None,
                cdp_url=launch_info["cdp_url"],
                create_new_page=True if create_new_page is None else create_new_page,
            )
            await app_ctx.session_manager.register_session(session_info["session_id"], session_info)
            result["session_id"] = session_info["session_id"]
        return result
    except BrowserAutomationError as e:
        logger.error("Failed to launch visible Chrome: %s", e.message, exc_info=True)
        raise MCPError(f"Failed to launch visible Chrome: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during visible Chrome launch: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Closes an existing browser automation session.")
async def close_session(
    session_id: str,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        await app_ctx.browser_service.close_session(session_id)
        await app_ctx.session_manager.unregister_session(session_id)
        logger.info("Session %s closed successfully.", session_id)
        return {"session_id": session_id, "message": "Session closed successfully."}
    except SessionNotFoundError as e:
        logger.warning("Attempted to close non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        logger.error("Failed to close session %s: %s", session_id, e.message, exc_info=True)
        raise MCPError(f"Failed to close session: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during session close: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Navigates the browser in a session to a specified URL.")
async def navigate(
    session_id: str,
    url: str,
    wait_until: Optional[str] = "load",
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        await app_ctx.browser_service.navigate(session_id, url, wait_until)
        await app_ctx.session_manager.update_session_activity(session_id, "navigate", {"url": url})
        logger.info("Session %s navigated to %s.", session_id, url)
        return {"session_id": session_id, "url": url, "message": "Navigation successful."}
    except (NavigationError, InvalidURLError) as e:
        logger.error("Navigation failed for session %s to %s: %s", session_id, url, e.message, exc_info=True)
        raise MCPError(f"Navigation failed: {e.message}", details=e.to_dict())
    except SessionNotFoundError as e:
        logger.warning("Navigation attempt on non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during navigation: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Clicks an element identified by a CSS selector or XPath.")
async def click_element(
    session_id: str,
    selector: str,
    timeout: Optional[int] = None,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        await app_ctx.browser_service.click_element(session_id, selector, timeout)
        await app_ctx.session_manager.update_session_activity(session_id, "click", {"selector": selector})
        logger.info("Session %s clicked element %s.", session_id, selector)
        return {"session_id": session_id, "selector": selector, "message": "Element clicked successfully."}
    except (ElementError, ElementNotFoundError, ElementNotInteractableError, InvalidSelectorError) as e:
        logger.error("Click failed for session %s on %s: %s", session_id, selector, e.message, exc_info=True)
        raise MCPError(f"Click failed: {e.message}", details=e.to_dict())
    except SessionNotFoundError as e:
        logger.warning("Click attempt on non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during click: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Types text into an element identified by a CSS selector or XPath.")
async def type_text(
    session_id: str,
    selector: str,
    text: str,
    timeout: Optional[int] = None,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        await app_ctx.browser_service.type_text(session_id, selector, text, timeout)
        await app_ctx.session_manager.update_session_activity(
            session_id,
            "type",
            {"selector": selector, "text_length": len(text)},
        )
        logger.info("Session %s typed into element %s.", session_id, selector)
        return {"session_id": session_id, "selector": selector, "message": "Text typed successfully."}
    except (ElementError, ElementNotFoundError, ElementNotInteractableError, InvalidSelectorError) as e:
        logger.error("Type failed for session %s on %s: %s", session_id, selector, e.message, exc_info=True)
        raise MCPError(f"Type failed: {e.message}", details=e.to_dict())
    except SessionNotFoundError as e:
        logger.warning("Type attempt on non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during type: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Press a keyboard key within the active page of a session.")
async def press_key(
    session_id: str,
    key: str,
    delay: Optional[int] = None,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        await app_ctx.browser_service.press_key(session_id, key, delay)
        await app_ctx.session_manager.update_session_activity(
            session_id,
            "press_key",
            {"key": key, "delay": delay},
        )
        logger.info("Session %s pressed key %s.", session_id, key)
        return {"session_id": session_id, "key": key, "message": "Key pressed."}
    except SessionNotFoundError as e:
        logger.warning("Key press attempt on non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        logger.error("Failed to press key %s in session %s: %s", key, session_id, e.message, exc_info=True)
        raise MCPError(f"Failed to press key: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during key press: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(
    description="Retrieve page content as HTML or plain text, optionally scoped to a selector and truncated to avoid token limits."
)
async def get_page_content(
    session_id: str,
    selector: Optional[str] = None,
    content_format: Optional[str] = "html",
    max_chars: Optional[int] = None,
    return_content: Optional[bool] = True,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        content = await app_ctx.browser_service.get_page_content(
            session_id,
            selector=selector,
            content_format=content_format or "html",
        )
        if isinstance(max_chars, int) and max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]
        metrics: Dict[str, Any] = {
            "content_length": len(content),
            "format": content_format or "html",
        }
        if selector is not None:
            metrics["selector"] = selector
        await app_ctx.session_manager.update_session_activity(session_id, "get_content", metrics)
        logger.info("Session %s retrieved page content.", session_id)

        result: Dict[str, Any] = {
            "session_id": session_id,
            "message": "Page content retrieved successfully.",
            **metrics,
        }
        if return_content or return_content is None:
            result["content"] = content
        else:
            resource_uuid = uuid4().hex
            resource_uri = f"resource://page_content/{session_id}/{resource_uuid}"
            payload = {
                "session_id": session_id,
                "format": metrics["format"],
                "selector": selector,
                "content": content,
            }
            resource = FunctionResource.from_function(
                fn=lambda data=payload: data,
                uri=resource_uri,
                name=f"page_content_{session_id}_{resource_uuid}",
                description="Captured page content",
                mime_type="application/json",
            )
            ctx.fastmcp.add_resource(resource)
            result["resource_uri"] = resource_uri
        return result
    except SessionNotFoundError as e:
        logger.warning("Get content attempt on non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        logger.error("Failed to get page content for session %s: %s", session_id, e.message, exc_info=True)
        raise MCPError(f"Failed to get page content: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during get_page_content: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(
    description="Takes a screenshot of the current page in a session. Defaults to returning a resource URI instead of inline image data to avoid token limits."
)
async def take_screenshot(
    session_id: str,
    full_page: Optional[bool] = False,
    encoding: Optional[str] = "base64",
    return_image: Optional[bool] = False,
    image_format: Optional[str] = "png",
    quality: Optional[int] = None,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        await app_ctx.session_manager.update_session_activity(
            session_id,
            "screenshot",
            {
                "full_page": full_page,
                "encoding": encoding,
                "image_format": image_format,
            },
        )
        logger.info("Session %s requested screenshot (return_image=%s).", session_id, return_image)

        result: Dict[str, Any] = {"session_id": session_id, "message": "Screenshot ready."}
        mime_type = "image/png" if (image_format or "png") == "png" else "image/jpeg"
        if return_image:
            image_data = await app_ctx.browser_service.take_screenshot(
                session_id,
                full_page,
                encoding or "base64",
            )
            result["image_data"] = image_data
            result["mime_type"] = mime_type
        else:
            screenshot_bytes = await app_ctx.browser_service.take_screenshot_bytes(
                session_id,
                full_page=bool(full_page),
                image_format=image_format or "png",
                quality=quality,
            )
            resource_uuid = uuid4().hex
            resource_uri = f"resource://screenshot/{session_id}/{resource_uuid}"
            resource = FunctionResource.from_function(
                fn=lambda data=screenshot_bytes: data,
                uri=resource_uri,
                name=f"screenshot_{session_id}_{resource_uuid}",
                description="Screenshot captured via take_screenshot tool",
                mime_type=mime_type,
            )
            ctx.fastmcp.add_resource(resource)
            result["resource_uri"] = resource_uri
            result["mime_type"] = mime_type
        return result
    except SessionNotFoundError as e:
        logger.warning("Screenshot attempt on non-existent session %s.", session_id)
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        logger.error("Failed to take screenshot for session %s: %s", session_id, e.message, exc_info=True)
        raise MCPError(f"Failed to take screenshot: {e.message}", details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        logger.error("Unexpected error during screenshot: %s", e, exc_info=True)
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(
    description="Retrieve a truncated plain-text excerpt of the page or a selector to fit token limits."
)
async def get_text_excerpt(
    session_id: str,
    selector: Optional[str] = None,
    max_chars: Optional[int] = 5000,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        text = await app_ctx.browser_service.get_page_content(
            session_id,
            selector=selector,
            content_format="text",
        )
        truncated_to: Optional[int] = None
        if isinstance(max_chars, int) and max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars]
            truncated_to = max_chars
        metrics: Dict[str, Any] = {"content_length": len(text)}
        if truncated_to is not None:
            metrics["truncated_to"] = truncated_to
        if selector is not None:
            metrics["selector"] = selector
        await app_ctx.session_manager.update_session_activity(session_id, "get_text_excerpt", metrics)
        return {"session_id": session_id, "excerpt": text, "message": "Excerpt retrieved.", **metrics}
    except SessionNotFoundError as e:
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        raise MCPError(e.message, details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Extract up to N links (text + href) from the page or a selector to minimize tokens.")
async def get_links(
    session_id: str,
    selector: Optional[str] = None,
    max_links: Optional[int] = 20,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        if session_id not in app_ctx.browser_service.pages:
            raise SessionNotFoundError(session_id)
        page = app_ctx.browser_service.pages[session_id]
        scope = selector or "a"
        all_links = await page.eval_on_selector_all(
            scope,
            "els => els.map(e => ({ text: (e.innerText||'').trim(), href: e.getAttribute('href') || '' }))",
        )
        filtered = [link for link in all_links if link.get("href")]
        if isinstance(max_links, int) and max_links > 0:
            filtered = filtered[:max_links]
        await app_ctx.session_manager.update_session_activity(
            session_id,
            "get_links",
            {"count": len(filtered), "selector": scope},
        )
        return {
            "session_id": session_id,
            "links": filtered,
            "count": len(filtered),
            "selector": scope,
            "message": "Links extracted.",
        }
    except SessionNotFoundError as e:
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        raise MCPError(e.message, details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Inspect elements matching a selector, returning visible text, attributes, and bounding boxes for better action planning.")
async def inspect_elements(
    session_id: str,
    selector: str,
    max_elements: Optional[int] = 10,
    include_html_preview: Optional[bool] = False,
    extra_attributes: Optional[List[str]] = None,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        summary = await app_ctx.browser_service.describe_elements(
            session_id,
            selector,
            max_elements=max_elements if max_elements is not None else 10,
            include_html_preview=bool(include_html_preview),
            extra_attributes=extra_attributes,
        )
        await app_ctx.session_manager.update_session_activity(
            session_id,
            "inspect_elements",
            {
                "selector": selector,
                "total_matches": summary.get("total_matches"),
                "returned": summary.get("returned"),
            },
        )
        return {
            "session_id": session_id,
            "message": "Element inspection complete.",
            **summary,
        }
    except SessionNotFoundError as e:
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        raise MCPError(e.message, details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        raise MCPError(f"Unexpected error: {e}")


@mcp.tool(description="Capture an accessibility tree snapshot (roles, names, states) to understand screen-reader-visible structure without screenshots.")
async def get_accessibility_tree(
    session_id: str,
    max_depth: Optional[int] = 3,
    max_nodes: Optional[int] = 120,
    role_filter: Optional[List[str]] = None,
    name_filter: Optional[str] = None,
    interesting_only: Optional[bool] = True,
    *,
    ctx: Context[ServerSession, AppContext],
) -> Dict[str, Any]:
    app_ctx = require_app_context(ctx)
    try:
        tree = await app_ctx.browser_service.get_accessibility_tree(
            session_id,
            max_depth=max_depth if max_depth is not None else 3,
            max_nodes=max_nodes if max_nodes is not None else 120,
            role_filter=role_filter,
            name_filter=name_filter,
            interesting_only=interesting_only if interesting_only is not None else True,
        )
        await app_ctx.session_manager.update_session_activity(
            session_id,
            "get_accessibility_tree",
            {
                "node_count": tree.get("node_count"),
                "max_depth": tree.get("max_depth"),
                "roles": tree.get("roles"),
                "name_filter": tree.get("name_filter"),
            },
        )
        return {
            "session_id": session_id,
            "message": "Accessibility tree captured.",
            **tree,
        }
    except SessionNotFoundError as e:
        raise MCPError(f"Session not found: {session_id}", details=e.to_dict())
    except BrowserAutomationError as e:
        raise MCPError(e.message, details=e.to_dict())
    except Exception as e:  # noqa: BLE001
        raise MCPError(f"Unexpected error: {e}")
