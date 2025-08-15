from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from typing import Dict, Any, Optional
import asyncio
from uuid import uuid4
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

logger = get_logger(__name__)

class BrowserService:
    def __init__(self, max_browsers: int = 1, max_contexts_per_browser: int = 5, headless: bool = True, timeout: int = 30000):
        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self.headless = headless
        self.timeout = timeout
        self.browsers: Dict[str, Browser] = {}
        self.contexts: Dict[str, BrowserContext] = {}
        self.pages: Dict[str, Page] = {}
        self.playwright_instance = None
        self._browser_counter = 0

    async def _launch_browser(self, browser_type: str = "chromium", headless: Optional[bool] = None) -> Browser:
        if not self.playwright_instance:
            self.playwright_instance = await async_playwright().start()

        effective_headless = self.headless if headless is None else headless
        if browser_type == "chromium":
            browser = await self.playwright_instance.chromium.launch(headless=effective_headless)
        elif browser_type == "firefox":
            browser = await self.playwright_instance.firefox.launch(headless=effective_headless)
        elif browser_type == "webkit":
            browser = await self.playwright_instance.webkit.launch(headless=effective_headless)
        else:
            raise BrowserAutomationError(f"Unsupported browser type: {browser_type}")
        self._browser_counter += 1
        logger.info(f"Launched new {browser_type} browser. Total browsers: {self._browser_counter}")
        return browser

    async def create_session(self, session_id: Optional[str] = None, browser_type: str = "chromium", headless: Optional[bool] = None, viewport_width: Optional[int] = None, viewport_height: Optional[int] = None) -> Dict[str, Any]:
        try:
            if not session_id:
                session_id = str(uuid4())
            if session_id in self.pages:
                raise BrowserAutomationError(f"Session ID {session_id} already exists.")

            # Find an existing browser or launch a new one
            browser_instance = None
            # If a per-session headless override is provided, prefer launching a new browser
            prefer_new_browser = headless is not None and headless != self.headless
            if not prefer_new_browser:
                for _b_id, b in self.browsers.items():
                    if len(b.contexts) < self.max_contexts_per_browser:
                        browser_instance = b
                        break
            
            if not browser_instance:
                if self._browser_counter >= self.max_browsers:
                    raise BrowserAutomationError("Maximum number of browser instances reached.")
                browser_instance = await self._launch_browser(browser_type, headless=headless)
                browser_key = str(id(browser_instance))
                self.browsers[browser_key] = browser_instance

            context = await browser_instance.new_context(
                viewport={"width": viewport_width, "height": viewport_height} if viewport_width and viewport_height else None
            )
            page = await context.new_page()

            self.contexts[session_id] = context
            self.pages[session_id] = page
            logger.info(f"Created new session: {session_id} with browser type {browser_type}")
            return {"session_id": session_id, "browser_type": browser_type, "headless": headless if headless is not None else self.headless}
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to create session: {e}")

    async def close_session(self, session_id: str):
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages.pop(session_id)
            context = self.contexts.pop(session_id)
            await page.close()
            await context.close()
            logger.info(f"Closed session: {session_id}")

            # If the browser has no more contexts, close it
            browser_key_to_close = None
            for b_id, b in list(self.browsers.items()):
                if not b.contexts:
                    await b.close()
                    browser_key_to_close = b_id
                    break
            if browser_key_to_close:
                self.browsers.pop(browser_key_to_close, None)
                self._browser_counter -= 1
                logger.info(f"Closed browser instance. Total browsers: {self._browser_counter}")

        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to close session: {e}")

    async def navigate(self, session_id: str, url: str, wait_until: str = "load"):
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            await page.goto(url, wait_until=wait_until, timeout=self.timeout)
            logger.info(f"Session {session_id} navigated to {url}")
        except Exception as e:
            logger.error(f"Error navigating session {session_id} to {url}: {e}", exc_info=True)
            if "ERR_INVALID_URL" in str(e):
                raise InvalidURLError(url)
            raise NavigationError(url, message=str(e))

    async def click_element(self, session_id: str, selector: str, timeout: Optional[int] = None):
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            await page.click(selector, timeout=timeout if timeout is not None else self.timeout)
            logger.info(f"Session {session_id} clicked element {selector}")
        except Exception as e:
            logger.error(f"Error clicking element {selector} in session {session_id}: {e}", exc_info=True)
            if "not found" in str(e).lower():
                raise ElementNotFoundError(selector)
            if "not interactable" in str(e).lower():
                raise ElementNotInteractableError(selector)
            if "selector" in str(e).lower() and "failed" in str(e).lower():
                raise InvalidSelectorError(selector)
            raise ElementError(selector, message=str(e))

    async def type_text(self, session_id: str, selector: str, text: str, timeout: Optional[int] = None):
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            await page.fill(selector, text, timeout=timeout if timeout is not None else self.timeout)
            logger.info(f"Session {session_id} typed text into element {selector}")
        except Exception as e:
            logger.error(f"Error typing text into element {selector} in session {session_id}: {e}", exc_info=True)
            if "not found" in str(e).lower():
                raise ElementNotFoundError(selector)
            if "not interactable" in str(e).lower():
                raise ElementNotInteractableError(selector)
            if "selector" in str(e).lower() and "failed" in str(e).lower():
                raise InvalidSelectorError(selector)
            raise ElementError(selector, message=str(e))

    async def get_page_content(self, session_id: str) -> str:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            content = await page.content()
            logger.info(f"Session {session_id} retrieved page content")
            return content
        except Exception as e:
            logger.error(f"Error getting page content for session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to get page content: {e}")

    async def take_screenshot(self, session_id: str, full_page: bool = False, encoding: str = "base64") -> str:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            screenshot_bytes = await page.screenshot(full_page=full_page)
            if encoding == "base64":
                import base64
                return base64.b64encode(screenshot_bytes).decode("utf-8")
            return screenshot_bytes.decode("latin-1") # Return as string for binary
        except Exception as e:
            logger.error(f"Error taking screenshot for session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to take screenshot: {e}")

    async def close_all_browsers(self):
        for session_id in list(self.pages.keys()):
            await self.close_session(session_id)
        if self.playwright_instance:
            await self.playwright_instance.stop()
            self.playwright_instance = None
        logger.info("All browsers and Playwright instance closed.")


