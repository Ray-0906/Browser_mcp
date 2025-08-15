from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any, Optional
from app.services.browser_service import BrowserService
from app.services.session_service import SessionManager
from app.core.logging import get_logger
from app.core.exceptions import (
    BrowserAutomationError,
    SessionNotFoundError,
    NavigationError,
    ElementError,
    InvalidURLError,
    ElementNotFoundError,
    ElementNotInteractableError,
    InvalidSelectorError
)

router = APIRouter()
logger = get_logger(__name__)

# Dependency to get BrowserService and SessionManager instances
# In a real application, these would be managed by FastAPI's dependency injection
# For simplicity, we'll assume they are attached to the app instance
def get_browser_service(request: Request) -> BrowserService:
    return request.app.browser_service

def get_session_manager(request: Request) -> SessionManager:
    return request.app.session_manager

@router.post("/session", summary="Create a new browser session", response_model=Dict[str, Any])
async def create_session(
    session_id: Optional[str] = None,
    browser_type: Optional[str] = "chromium",
    headless: Optional[bool] = None,
    viewport_width: Optional[int] = None,
    viewport_height: Optional[int] = None,
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        session_info = await browser_service.create_session(
            session_id=session_id,
            browser_type=browser_type,
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )
        await session_manager.register_session(session_info["session_id"], session_info)
        logger.info(f"API: Session {session_info['session_id']} created successfully.")
        return {"session_id": session_info['session_id'], "message": "Session created successfully."}
    except BrowserAutomationError as e:
        logger.error(f"API: Failed to create session: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

@router.delete("/session/{session_id}", summary="Close a browser session", response_model=Dict[str, Any])
async def close_session(
    session_id: str,
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        await browser_service.close_session(session_id)
        await session_manager.unregister_session(session_id)
        logger.info(f"API: Session {session_id} closed successfully.")
        return {"session_id": session_id, "message": "Session closed successfully."}
    except SessionNotFoundError as e:
        logger.warning(f"API: Attempted to close non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except BrowserAutomationError as e:
        logger.error(f"API: Failed to close session {session_id}: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

@router.post("/session/{session_id}/navigate", summary="Navigate to a URL", response_model=Dict[str, Any])
async def navigate(
    session_id: str,
    url: str,
    wait_until: Optional[str] = "load",
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        await browser_service.navigate(session_id, url, wait_until)
        await session_manager.update_session_activity(session_id, "navigate", {"url": url})
        logger.info(f"API: Session {session_id} navigated to {url}.")
        return {"session_id": session_id, "url": url, "message": "Navigation successful."}
    except (NavigationError, InvalidURLError) as e:
        logger.error(f"API: Navigation failed for session {session_id} to {url}: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except SessionNotFoundError as e:
        logger.warning(f"API: Navigation attempt on non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except BrowserAutomationError as e:
        logger.error(f"API: An unexpected error occurred during navigation: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

@router.post("/session/{session_id}/click", summary="Click an element", response_model=Dict[str, Any])
async def click_element(
    session_id: str,
    selector: str,
    timeout: Optional[int] = None,
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        await browser_service.click_element(session_id, selector, timeout)
        await session_manager.update_session_activity(session_id, "click", {"selector": selector})
        logger.info(f"API: Session {session_id} clicked element {selector}.")
        return {"session_id": session_id, "selector": selector, "message": "Element clicked successfully."}
    except (ElementError, ElementNotFoundError, ElementNotInteractableError, InvalidSelectorError) as e:
        logger.error(f"API: Click failed for session {session_id} on {selector}: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except SessionNotFoundError as e:
        logger.warning(f"API: Click attempt on non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except BrowserAutomationError as e:
        logger.error(f"API: An unexpected error occurred during click: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

@router.post("/session/{session_id}/type", summary="Type text into an element", response_model=Dict[str, Any])
async def type_text(
    session_id: str,
    selector: str,
    text: str,
    timeout: Optional[int] = None,
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        await browser_service.type_text(session_id, selector, text, timeout)
        await session_manager.update_session_activity(session_id, "type", {"selector": selector, "text_length": len(text)})
        logger.info(f"API: Session {session_id} typed into element {selector}.")
        return {"session_id": session_id, "selector": selector, "message": "Text typed successfully."}
    except (ElementError, ElementNotFoundError, ElementNotInteractableError, InvalidSelectorError) as e:
        logger.error(f"API: Type failed for session {session_id} on {selector}: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except SessionNotFoundError as e:
        logger.warning(f"API: Type attempt on non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except BrowserAutomationError as e:
        logger.error(f"API: An unexpected error occurred during type: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

@router.get("/session/{session_id}/content", summary="Get page HTML content", response_model=Dict[str, Any])
async def get_page_content(
    session_id: str,
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        content = await browser_service.get_page_content(session_id)
        await session_manager.update_session_activity(session_id, "get_content", {"content_length": len(content)})
        logger.info(f"API: Session {session_id} retrieved page content.")
        return {"session_id": session_id, "content": content, "message": "Page content retrieved successfully."}
    except SessionNotFoundError as e:
        logger.warning(f"API: Get content attempt on non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except BrowserAutomationError as e:
        logger.error(f"API: Failed to get page content for session {session_id}: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

@router.get("/session/{session_id}/screenshot", summary="Take a screenshot", response_model=Dict[str, Any])
async def take_screenshot(
    session_id: str,
    full_page: Optional[bool] = False,
    encoding: Optional[str] = "base64",
    browser_service: BrowserService = Depends(get_browser_service),
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        image_data = await browser_service.take_screenshot(session_id, full_page, encoding)
        await session_manager.update_session_activity(session_id, "screenshot", {"full_page": full_page, "encoding": encoding})
        logger.info(f"API: Session {session_id} took screenshot.")
        return {"session_id": session_id, "image_data": image_data, "message": "Screenshot taken successfully."}
    except SessionNotFoundError as e:
        logger.warning(f"API: Screenshot attempt on non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except BrowserAutomationError as e:
        logger.error(f"API: Failed to take screenshot for session {session_id}: {e.message}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

@router.get("/sessions", summary="List all active sessions", response_model=Dict[str, Any])
async def list_active_sessions(
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        active_sessions = await session_manager.get_all_sessions()
        logger.info("API: Listed all active sessions.")
        return {"sessions": active_sessions, "message": "Active sessions listed."}
    except Exception as e:
        logger.error(f"API: An unexpected error occurred while listing sessions: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/session/{session_id}", summary="Get session information", response_model=Dict[str, Any])
async def get_session_info(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        session_info = await session_manager.get_session_info(session_id)
        if not session_info:
            raise SessionNotFoundError(session_id)
        logger.info(f"API: Retrieved info for session {session_id}.")
        return {"session_id": session_id, "info": session_info, "message": "Session info retrieved."}
    except SessionNotFoundError as e:
        logger.warning(f"API: Info request for non-existent session {session_id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except Exception as e:
        logger.error(f"API: An unexpected error occurred while getting session info: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


