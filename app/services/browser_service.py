from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from typing import Dict, Any, Optional, Set, List
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
import os
import sys
import subprocess

logger = get_logger(__name__)

CLICKABLE_SELECTOR = ",".join(
    [
        "a[href]",
        "button",
        "input[type='button']",
        "input[type='submit']",
        "input[type='reset']",
        "input[type='image']",
        "[role='button']",
        "[role='link']",
        "[role='menuitem']",
        "[role='menuitemcheckbox']",
        "[role='menuitemradio']",
        "[role='option']",
        "[role='tab']",
        "[role='checkbox']",
        "[role='radio']",
        "[role='switch']",
        "[role='listitem']",
        "[role='treeitem']",
        "[role='gridcell']",
        "[role='row']",
        "[role='combobox']",
        "[tabindex]",
        "[onclick]",
        "[contenteditable='true']",
        "ytmusic-responsive-list-item-renderer",
    ]
)

CLICKABLE_ROLE_HINTS: Set[str] = {
    "button",
    "link",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "tab",
    "checkbox",
    "radio",
    "switch",
    "treeitem",
    "gridcell",
    "row",
    "combobox",
    "listitem",
}

class BrowserService:
    def __init__(self, max_browsers: int = 1, max_contexts_per_browser: int = 5, headless: bool = True, timeout: int = 30000):
        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self.headless = headless
        self.timeout = timeout
        self.browsers = {}
        self.contexts = {}
        self.pages = {}
        self.playwright_instance = None
        self._browser_counter = 0
        # Track sessions connected via CDP to a user-managed browser (visible)
        self._cdp_sessions = set()

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

    async def connect_cdp_session(self, session_id: Optional[str] = None, cdp_url: str = "http://localhost:9222", create_new_page: bool = True) -> Dict[str, Any]:
        """Connect to an existing, user-launched Chromium/Chrome via CDP. Leaves the browser visible and user-controllable.

        Steps to prepare Chrome manually (Windows example):
        - "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome-debug"
        Then call this method with cdp_url="http://localhost:9222".
        """
        try:
            if not self.playwright_instance:
                self.playwright_instance = await async_playwright().start()
            if not session_id:
                session_id = str(uuid4())
            if session_id in self.pages:
                raise BrowserAutomationError(f"Session ID {session_id} already exists.")

            browser = await self.playwright_instance.chromium.connect_over_cdp(cdp_url)
            # For persistent Chrome, there is usually a single context
            contexts = browser.contexts
            if not contexts:
                # Fallback: some environments might expose a default context differently
                context = await browser.new_context()
            else:
                context = contexts[0]

            page: Optional[Page] = None
            if create_new_page or not context.pages:
                page = await context.new_page()
            else:
                page = context.pages[0]

            browser_key = str(id(browser))
            self.browsers[browser_key] = browser
            self.contexts[session_id] = context
            self.pages[session_id] = page
            self._cdp_sessions.add(session_id)
            logger.info(f"Connected CDP session: {session_id} via {cdp_url}")
            return {"session_id": session_id, "browser_type": "chromium", "cdp_url": cdp_url, "headless": False}
        except Exception as e:
            logger.error(f"Error connecting CDP session {session_id} to {cdp_url}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to connect via CDP: {e}")

    async def close_session(self, session_id: str):
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages.pop(session_id)
            context = self.contexts.pop(session_id)
            await page.close()
            # For CDP sessions (user-managed), do not close the persistent context/browser
            if session_id in self._cdp_sessions:
                self._cdp_sessions.discard(session_id)
            else:
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

    async def press_key(self, session_id: str, key: str, delay: Optional[int] = None):
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            if delay is not None:
                await page.keyboard.press(key, delay=max(0, int(delay)))
            else:
                await page.keyboard.press(key)
            logger.info(f"Session {session_id} pressed key {key}")
        except Exception as e:
            logger.error(f"Error pressing key {key} in session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to press key {key}: {e}")

    async def get_page_content(self, session_id: str, selector: Optional[str] = None, content_format: str = "html") -> str:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            if selector:
                locator = page.locator(selector).first
                if content_format == "text":
                    content = await locator.inner_text()
                else:
                    content = await locator.inner_html()
            else:
                if content_format == "text":
                    content = await page.inner_text("body")
                else:
                    content = await page.content()
            logger.info(f"Session {session_id} retrieved page content (format={content_format}, selector={selector})")
            return content
        except Exception as e:
            logger.error(f"Error getting page content for session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to get page content: {e}")

    async def describe_elements(
        self,
        session_id: str,
        selector: str,
        max_elements: int = 10,
        include_html_preview: bool = False,
        extra_attributes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            locator = page.locator(selector)
            total_matches = await locator.count()
            limit = total_matches if max_elements is None or max_elements <= 0 else min(max_elements, total_matches)
            results: List[Dict[str, Any]] = []

            for index in range(limit):
                element = locator.nth(index)
                element_info = await element.evaluate(
                    """
                    (el) => ({
                        tag: el.tagName ? el.tagName.toLowerCase() : null,
                        id: el.id || null,
                        className: el.className || null,
                        name: el.getAttribute('name') || null,
                        ariaLabel: el.getAttribute('aria-label') || null,
                        role: el.getAttribute('role') || null,
                        type: el.getAttribute('type') || null,
                        placeholder: el.getAttribute('placeholder') || null,
                        title: el.getAttribute('title') || null,
                        href: el.getAttribute('href') || null,
                        text: (el.innerText || '').trim(),
                        value: typeof el.value === 'string' ? el.value : null,
                        disabled: el.matches(':disabled'),
                        checked: el.matches(':checked'),
                    })
                    """
                )

                classes_raw = element_info.pop("className", None)
                classes: Optional[List[str]] = None
                if classes_raw:
                    classes = [cls for cls in classes_raw.split() if cls]

                extra_attrs: Dict[str, Any] = {}
                if extra_attributes:
                    extra_attrs = await element.evaluate(
                        "(el, names) => Object.fromEntries(names.map(name => [name, el.getAttribute(name)]))",
                        extra_attributes,
                    )

                bounding_box = await element.bounding_box()
                visible = await element.is_visible()

                element_record: Dict[str, Any] = {
                    "index": index,
                    "tag": element_info.get("tag"),
                    "id": element_info.get("id"),
                    "classes": classes,
                    "role": element_info.get("role"),
                    "name": element_info.get("name"),
                    "aria_label": element_info.get("ariaLabel"),
                    "type": element_info.get("type"),
                    "placeholder": element_info.get("placeholder"),
                    "title": element_info.get("title"),
                    "href": element_info.get("href"),
                    "text": element_info.get("text"),
                    "value": element_info.get("value"),
                    "disabled": element_info.get("disabled"),
                    "checked": element_info.get("checked"),
                    "visible": visible,
                    "bounding_box": bounding_box,
                }

                if extra_attrs:
                    element_record["attributes"] = {k: v for k, v in extra_attrs.items() if v is not None}

                if include_html_preview:
                    outer_html = await element.evaluate("el => el.outerHTML || ''")
                    preview = outer_html[:500]
                    element_record["outer_html_preview"] = preview

                if element_record.get("tag") and (element_record.get("id") or classes):
                    parts: List[str] = [element_record["tag"]]
                    if element_record.get("id"):
                        parts.append(f"#{element_record['id']}")
                    if classes:
                        parts.extend([f".{c}" for c in classes[:3]])
                    element_record["suggested_locator"] = "".join(parts)

                results.append(element_record)

            return {
                "selector": selector,
                "total_matches": total_matches,
                "returned": len(results),
                "elements": results,
            }
        except Exception as e:
            logger.error(f"Error describing elements for session {session_id} using {selector}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to describe elements: {e}")

    async def find_click_targets(
        self,
        session_id: str,
        text: str,
        exact: bool = False,
        case_sensitive: bool = False,
        preferred_roles: Optional[List[str]] = None,
        max_results: int = 10,
        include_html_preview: bool = False,
        extra_attributes: Optional[List[str]] = None,
        scan_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        if not text or not text.strip():
            raise BrowserAutomationError("Search text must be provided.")
        try:
            page = self.pages[session_id]
            target_text = text if case_sensitive else text.strip().lower()
            roles_set: Optional[Set[str]] = {r.lower() for r in preferred_roles} if preferred_roles else None
            dedup_attrs = list(dict.fromkeys(extra_attributes or []))

            locator = page.locator(CLICKABLE_SELECTOR)
            total_candidates = await locator.count()
            scan_cap = total_candidates
            if scan_limit is not None and scan_limit > 0:
                scan_cap = min(total_candidates, scan_limit)
            else:
                scan_cap = min(total_candidates, 200)

            matches: List[Dict[str, Any]] = []
            matched_count = 0

            for index in range(scan_cap):
                element = locator.nth(index)
                try:
                    info = await element.evaluate(
                        """
                        (el, attrs) => {
                            const rect = el.getBoundingClientRect();
                            const attrEntries = {};
                            if (Array.isArray(attrs)) {
                                for (const name of attrs) {
                                    attrEntries[name] = el.getAttribute(name);
                                }
                            }
                            return {
                                tag: el.tagName ? el.tagName.toLowerCase() : null,
                                text: (el.innerText || el.textContent || '').trim(),
                                id: el.id || null,
                                className: el.className || null,
                                role: el.getAttribute('role') || null,
                                href: el.getAttribute('href') || null,
                                ariaLabel: el.getAttribute('aria-label') || null,
                                title: el.getAttribute('title') || null,
                                value: typeof el.value === 'string' ? el.value : null,
                                disabled: el.matches(':disabled'),
                                checked: el.matches(':checked'),
                                rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                                attributes: attrEntries,
                            };
                        }
                        """,
                        dedup_attrs,
                    )
                except Exception:
                    continue

                if not info:
                    continue

                role = info.get("role")
                if roles_set and (role is None or role.lower() not in roles_set):
                    continue

                classes_raw = info.get("className") or ""
                classes = [cls for cls in classes_raw.split() if cls]

                attributes = info.get("attributes") or {}

                search_pool: List[tuple[str, str]] = []
                text_value = (info.get("text") or "").strip()
                if text_value:
                    search_pool.append(("text", text_value))
                aria_label = (info.get("ariaLabel") or "").strip()
                if aria_label:
                    search_pool.append(("aria_label", aria_label))
                title_value = (info.get("title") or "").strip()
                if title_value:
                    search_pool.append(("title", title_value))
                value_attr = (info.get("value") or "").strip()
                if value_attr:
                    search_pool.append(("value", value_attr))
                for attr_name, attr_value in attributes.items():
                    if attr_value:
                        search_pool.append((f"attr:{attr_name}", attr_value.strip()))

                matched_field: Optional[str] = None
                matched_value: Optional[str] = None
                exact_match = False

                for field_name, field_value in search_pool:
                    if not field_value:
                        continue
                    compare_value = field_value if case_sensitive else field_value.lower()
                    needle = text if case_sensitive else target_text
                    if not needle:
                        continue
                    match_found = compare_value == needle if exact else needle in compare_value
                    if match_found:
                        matched_field = field_name
                        matched_value = field_value
                        exact_match = compare_value == needle
                        break

                if not matched_field:
                    continue

                matched_count += 1

                bounding_box = info.get("rect") or {}
                visible = await element.is_visible()
                enabled = await element.is_enabled()

                suggested_locator = None
                tag = info.get("tag")
                if tag and (info.get("id") or classes):
                    parts: List[str] = [tag]
                    if info.get("id"):
                        parts.append(f"#{info['id']}")
                    if classes:
                        parts.extend([f".{cls}" for cls in classes[:3]])
                    suggested_locator = "".join(parts)

                score = 0.0
                if exact_match:
                    score += 2.5
                if matched_field == "text":
                    score += 1.5
                elif matched_field and matched_field.startswith("aria"):
                    score += 1.0
                elif matched_field and matched_field.startswith("attr:"):
                    score += 0.8
                if visible:
                    score += 1.5
                if enabled:
                    score += 0.5
                if info.get("disabled"):
                    score -= 1.5
                if role and role.lower() in CLICKABLE_ROLE_HINTS:
                    score += 1.0
                if tag in {"button", "a", "input", "ytmusic-responsive-list-item-renderer"}:
                    score += 0.5
                if classes and any("play" in cls.lower() for cls in classes):
                    score += 0.4
                if matched_value:
                    similarity = 1.0 - min(abs(len(matched_value) - len(text)) / max(len(text), 1), 1.0)
                    score += 0.5 * similarity
                confidence = max(0.0, min(score / 6.0, 1.0))

                record: Dict[str, Any] = {
                    "index": index,
                    "tag": tag,
                    "id": info.get("id"),
                    "classes": classes or None,
                    "role": role,
                    "text": text_value or None,
                    "aria_label": aria_label or None,
                    "title": title_value or None,
                    "href": info.get("href"),
                    "value": info.get("value"),
                    "disabled": info.get("disabled"),
                    "checked": info.get("checked"),
                    "visible": visible,
                    "enabled": enabled,
                    "bounding_box": bounding_box,
                    "match_field": matched_field,
                    "match_text": matched_value,
                    "exact_match": exact_match,
                    "suggested_locator": suggested_locator,
                    "confidence": round(confidence, 2),
                }

                filtered_attributes = {k: v for k, v in attributes.items() if v}
                if filtered_attributes:
                    record["attributes"] = filtered_attributes

                record["text_snippet"] = (text_value or matched_value or "")[:120] if (text_value or matched_value) else None
                record["_element_index"] = index

                matches.append(record)

            matches.sort(key=lambda item: (-item["confidence"], item["index"]))
            limited_matches = matches[: max_results if max_results and max_results > 0 else len(matches)]

            if include_html_preview and limited_matches:
                for entry in limited_matches:
                    idx = entry.get("_element_index")
                    if idx is None:
                        continue
                    element = locator.nth(idx)
                    try:
                        outer_html = await element.evaluate("el => el.outerHTML || ''")
                        entry["outer_html_preview"] = outer_html[:500]
                    except Exception:
                        continue

            for entry in limited_matches:
                entry.pop("_element_index", None)
                if not entry.get("text_snippet"):
                    entry.pop("text_snippet", None)

            return {
                "query": text,
                "case_sensitive": case_sensitive,
                "exact": exact,
                "preferred_roles": preferred_roles,
                "total_candidates": total_candidates,
                "scanned": scan_cap,
                "total_matches": matched_count,
                "returned": len(limited_matches),
                "more_available": matched_count > len(limited_matches),
                "elements": limited_matches,
            }
        except BrowserAutomationError:
            raise
        except Exception as e:
            logger.error(f"Error finding click targets for session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to find click targets: {e}")

    async def click_by_text(
        self,
        session_id: str,
        text: str,
        exact: bool = False,
        preferred_roles: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        nth: Optional[int] = None,
    ) -> Dict[str, Any]:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        if not text or not text.strip():
            raise BrowserAutomationError("Text must be provided for click_by_text.")
        try:
            page = self.pages[session_id]
            search_text = text.strip()
            roles_set: Optional[Set[str]] = {r.lower() for r in preferred_roles} if preferred_roles else None

            locator = page.get_by_text(search_text, exact=exact)
            candidate_count = await locator.count()
            if candidate_count == 0:
                raise ElementNotFoundError(search_text)

            indices: List[int]
            if nth is not None:
                indices = [nth]
            else:
                indices = list(range(candidate_count))

            last_error: Optional[Exception] = None

            for idx in indices:
                if idx < 0 or idx >= candidate_count:
                    continue
                candidate = locator.nth(idx)
                try:
                    if roles_set:
                        role = await candidate.get_attribute("role")
                        if role is None or role.lower() not in roles_set:
                            continue
                    if not await candidate.is_visible():
                        continue
                    await candidate.click(timeout=timeout if timeout is not None else self.timeout)
                    logger.info(f"Session {session_id} clicked text '{search_text}' (index={idx}).")
                    return {
                        "session_id": session_id,
                        "text": search_text,
                        "clicked_index": idx,
                        "total_candidates": candidate_count,
                        "preferred_roles": preferred_roles,
                    }
                except Exception as click_error:
                    last_error = click_error
                    logger.debug(
                        "Failed attempt clicking text '%s' at index %s in session %s: %s",
                        search_text,
                        idx,
                        session_id,
                        click_error,
                        exc_info=True,
                    )
                    continue

            if roles_set:
                for role in roles_set:
                    role_locator = page.get_by_role(role, name=search_text, exact=exact)
                    role_count = await role_locator.count()
                    for idx in range(role_count):
                        candidate = role_locator.nth(idx)
                        try:
                            if not await candidate.is_visible():
                                continue
                            await candidate.click(timeout=timeout if timeout is not None else self.timeout)
                            logger.info(
                                "Session %s clicked text '%s' via role '%s' (index=%s).",
                                session_id,
                                search_text,
                                role,
                                idx,
                            )
                            return {
                                "session_id": session_id,
                                "text": search_text,
                                "clicked_index": idx,
                                "role": role,
                                "total_candidates": candidate_count,
                                "preferred_roles": preferred_roles,
                            }
                        except Exception as click_error:
                            last_error = click_error
                            logger.debug(
                                "Failed role-based click for '%s' role '%s' index %s in session %s: %s",
                                search_text,
                                role,
                                idx,
                                session_id,
                                click_error,
                                exc_info=True,
                            )
                            continue

            if last_error:
                logger.error(
                    "Unable to click text '%s' in session %s after %s attempts: %s",
                    search_text,
                    session_id,
                    len(indices),
                    last_error,
                )
                raise ElementNotInteractableError(search_text)

            raise ElementNotInteractableError(search_text)
        except BrowserAutomationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error clicking text '{text}' in session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to click text '{text}': {e}")

    async def get_accessibility_tree(
        self,
        session_id: str,
        max_depth: int = 3,
        max_nodes: int = 120,
        role_filter: Optional[List[str]] = None,
        name_filter: Optional[str] = None,
        interesting_only: bool = True,
    ) -> Dict[str, Any]:
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            snapshot = await page.accessibility.snapshot(interesting_only=interesting_only)
            results: List[Dict[str, Any]] = []
            role_filter_set: Optional[Set[str]] = {r.lower() for r in role_filter} if role_filter else None
            name_filter_value = name_filter.lower() if name_filter else None

            def walk(node: Optional[Dict[str, Any]], depth: int, path: str) -> None:
                if node is None or depth > max_depth or len(results) >= max_nodes:
                    return

                role = node.get("role")
                name = node.get("name")
                include_node = True
                if role_filter_set and (role or "").lower() not in role_filter_set:
                    include_node = False
                if include_node and name_filter_value and name:
                    include_node = name_filter_value in name.lower()
                elif include_node and name_filter_value and not name:
                    include_node = False

                if include_node:
                    results.append(
                        {
                            "path": path,
                            "depth": depth,
                            "role": role,
                            "name": name,
                            "value": node.get("value"),
                            "description": node.get("description"),
                            "focused": node.get("focused"),
                            "checked": node.get("checked"),
                            "disabled": node.get("disabled"),
                            "actions": node.get("actions"),
                        }
                    )

                children = node.get("children") or []
                for idx, child in enumerate(children):
                    if len(results) >= max_nodes:
                        break
                    next_path = f"{path}.{idx}" if path else str(idx)
                    walk(child, depth + 1, next_path)

            walk(snapshot, 0, "")
            return {
                "node_count": len(results),
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "roles": role_filter,
                "name_filter": name_filter,
                "nodes": results,
            }
        except Exception as e:
            logger.error(f"Error getting accessibility tree for session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to get accessibility tree: {e}")

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

    async def take_screenshot_bytes(self, session_id: str, full_page: bool = False, image_format: str = "png", quality: Optional[int] = None) -> bytes:
        """Return raw screenshot bytes for use in MCP resources to avoid inline base64 in tool responses.

        image_format: "png" or "jpeg". For "jpeg", optional quality (0-100) can be provided.
        """
        if session_id not in self.pages:
            raise SessionNotFoundError(session_id)
        try:
            page = self.pages[session_id]
            kwargs: Dict[str, Any] = {"full_page": full_page}
            # Playwright uses "type" to specify image format
            if image_format in ("png", "jpeg"):
                kwargs["type"] = image_format
                if image_format == "jpeg" and isinstance(quality, int):
                    # Only JPEG supports quality
                    kwargs["quality"] = max(0, min(100, quality))
            screenshot_bytes: bytes = await page.screenshot(**kwargs)
            return screenshot_bytes
        except Exception as e:
            logger.error(f"Error taking screenshot bytes for session {session_id}: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to take screenshot: {e}")

    async def close_all_browsers(self):
        for session_id in list(self.pages.keys()):
            await self.close_session(session_id)
        if self.playwright_instance:
            await self.playwright_instance.stop()
            self.playwright_instance = None
        logger.info("All browsers and Playwright instance closed.")

    async def launch_chrome_with_cdp(
        self,
        cdp_port: int = 9222,
        user_data_dir: Optional[str] = None,
        exe_path: Optional[str] = None,
        additional_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Launch a visible Chrome/Chromium with remote debugging and return the CDP URL and process info.

        If exe_path is not provided, tries common Windows install paths and then falls back to 'chrome.exe' on PATH.
        """
        try:
            # Resolve executable path
            candidates: List[str] = []
            if exe_path:
                candidates.append(exe_path)
            else:
                # Common Windows paths
                candidates += [
                    r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                ]
                # Try Edge if Chrome isn't found
                candidates += [
                    r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                    r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
                ]

            resolved_exe = None
            for p in candidates:
                if os.path.isfile(p):
                    resolved_exe = p
                    break
            if not resolved_exe:
                # Fallback to PATH
                resolved_exe = exe_path or "chrome.exe"

            # Ensure user-data-dir
            udd = user_data_dir or os.path.join(os.getcwd(), "chrome-debug-profile")
            os.makedirs(udd, exist_ok=True)

            args = [
                resolved_exe,
                f"--remote-debugging-port={cdp_port}",
                f"--user-data-dir={udd}",
            ]
            if additional_args:
                args.extend(additional_args)

            creationflags = 0
            popen_kwargs: Dict[str, Any] = {}
            if sys.platform.startswith("win"):
                # Detach so the browser stays open and doesn't block the server
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                popen_kwargs["creationflags"] = creationflags
            else:
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **popen_kwargs)
            cdp_url = f"http://localhost:{cdp_port}"
            logger.info(f"Launched Chrome for CDP at {cdp_url} (pid={proc.pid}) using {resolved_exe}")
            return {
                "cdp_url": cdp_url,
                "pid": proc.pid,
                "exe_path": resolved_exe,
                "user_data_dir": udd,
            }
        except Exception as e:
            logger.error(f"Error launching Chrome with CDP: {e}", exc_info=True)
            raise BrowserAutomationError(f"Failed to launch Chrome with CDP: {e}")


