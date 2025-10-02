# MCP Tool Reference & Execution Flow

This guide explains how each Model Context Protocol (MCP) tool exposed by the Browser Automation MCP Server works, how it coordinates session/context state, and how real browser work is delegated to Playwright under the hood.

> **Key components**
>
> - **MCP tools (`browser_mcp/mcp/tools.py`)** – Thin RPC wrappers that validate inputs, surface errors, and call into shared services.
> - **`AppContext` (`browser_mcp/mcp/context.py`)** – Provides every tool handler with the same `BrowserService` and `SessionManager` instance.
> - **`BrowserService` (`app/services/browser_service.py`)** – Owns the Playwright browser instances, contexts, and pages. It executes navigation, DOM queries, clicks, typing, etc.
> - **`SessionManager` (`app/services/session_service.py`)** – Tracks MCP-visible sessions (metadata, last activity, cleanup bookkeeping).

The flow for any tool call is:

1. MCP receives the request and resolves the `AppContext` from the lifespan state.
2. Tool handler calls into `BrowserService` to do the Playwright work.
3. `SessionManager` is updated with activity metadata (or session lifecycle changes).
4. Results are serialized back to the MCP client; large payloads (e.g., HTML, screenshots) can be returned as resource URIs.

---

## Session & context management tools

| Tool | Purpose | Under the hood | Key outputs |
| --- | --- | --- | --- |
| `create_session` | Start automation via Playwright or attach to CDP endpoint (auto-detects when `use_cdp` not specified). | Attempts `BrowserService.connect_cdp_session`; on failure or when `use_cdp=False`, launches a new Playwright browser, creates a context+page, caches them in `BrowserService.pages`. Registers the session with `SessionManager.register_session`. | `session_id`, optional `cdp_url`, message indicating launch vs. CDP attach. |
| `connect_cdp` | Explicitly attach to a user-launched Chrome/Edge with remote debugging. | Calls `BrowserService.connect_cdp_session`, which connects to the remote target via Playwright’s CDP client and records page handles in `BrowserService.pages`. Session metadata stored via `SessionManager`. | `session_id`, `cdp_url`. |
| `launch_visible_chrome` | Start Chrome/Edge with `--remote-debugging-port` and optionally auto-attach. | `BrowserService.launch_chrome_with_cdp` spawns the browser process, returning PID, user data dir, and the CDP URL. When `auto_connect=True`, it immediately reuses `connect_cdp` to register a session. | `cdp_url`, `pid`, `user_data_dir`, optional `session_id`. |
| `close_session` | Tear down automation state. | `BrowserService.close_session` disposes Playwright handles (page/context/browsers or CDP connections) and removes them from internal maps. `SessionManager.unregister_session` drops tracking metadata. | Confirmation message. |

### Session state

- **`BrowserService` dictionaries** map `session_id -> Playwright Page`, plus underlying context/browser references.
- **`SessionManager.sessions`** holds creation timestamps, last activity, and opaque `info` (currently the dict returned by `BrowserService`).
- Activity-update helpers (`update_session_activity`) let downstream tooling understand what each session last did and support idle cleanup.

---

## Navigation & page lifecycle

| Tool | Parameters | What `BrowserService` does | Notes |
| --- | --- | --- | --- |
| `navigate` | `session_id`, `url`, optional `wait_until` | Uses `page.goto`, respecting the Playwright waiting option. On success, updates last-activity metadata. | Raises `NavigationError` or `InvalidURLError` when Playwright surfaces issues. |
| `press_key` | `session_id`, `key`, optional `delay` | Calls `page.keyboard.press`, optionally `await asyncio.sleep` between actions. | Useful for keyboard shortcuts like `Space`, `ArrowRight`, etc. |

When CDP sessions are involved, navigation works on the active tab returned during connection (you can request a new page via `create_new_page=True`).

---

## Element interaction tools

| Tool | Primary inputs | Execution details | Output |
| --- | --- | --- | --- |
| `click_element` | `selector`, optional `timeout` | Delegates to `page.click` (CSS or XPath). The call is wrapped in error translation to return precise MCP errors (`ElementNotFoundError`, `ElementNotInteractableError`, `InvalidSelectorError`). | Confirmation with selector echoed. |
| `type_text` | `selector`, `text`, optional `timeout` | Uses `page.fill` when possible, falling back to `page.type` as needed. Records typed character count for analytics. | Confirmation with selector echoed. |
| `find_click_targets` | `text`, optional `preferred_roles`, `exact`, `case_sensitive`, `scan_limit`, `include_html_preview` | Scans a curated list of “clickable” selectors (buttons, links, inputs, ARIA roles) using `page.locator`. For every candidate Playwright handle, it fetches text, labels, titles, computed attributes, and visibility/enabled state. Each match receives a heuristic score so likely play buttons rise to the top. | Ranked list with confidence score, matched fields, bounding boxes, and optional HTML snippet. |
| `click_by_text` | `text`, optional `exact`, `preferred_roles`, `timeout`, `nth` | First tries Playwright’s `get_by_text`. If role hints are given, filters candidates by `role`. Falls back to `get_by_role` for listed roles. Ensures targets are visible/enabled before clicking. | Confirmation with matched index/role. |

Together, `find_click_targets` → `click_by_text` provide a resilient flow for LLM-driven control without crafting brittle CSS selectors.

---

## Content extraction & diagnostics

| Tool | Purpose | Browser operations | Output |
| --- | --- | --- | --- |
| `get_page_content` | Full HTML or plain text of the page or a scoped selector. | Uses `page.content` (HTML) or `inner_text` for CSS scope. Large responses can be truncated or emitted as MCP resources. | `content_length`, optional inline `content` or resource URI. |
| `get_text_excerpt` | Token-safe snippet of the page/selector. | Calls `get_page_content` in text mode and truncates to `max_chars`. | Direct text + metadata (length, truncation). |
| `get_links` | Extract anchor list quickly. | `page.eval_on_selector_all` to map text/href pairs beneath a selector (default `a`). | Array of `{text, href}` objects. |
| `take_screenshot` | Window or full page capture. | `page.screenshot`, optionally streaming bytes back as an MCP resource instead of inline base64. | Either inline `image_data` (if requested) or `resource_uri` with `mime_type`. |
| `inspect_elements` | Structured view of matching DOM nodes. | Iterates `page.locator(selector).nth(i)` up to `max_elements`, calling `element.evaluate` to extract text, attributes, bounding boxes, visibility, disabled state, etc. | List of element descriptors, optional clipped HTML preview. |
| `get_accessibility_tree` | Screen-reader facing structure. | Uses Playwright accessibility snapshot API with depth/node caps and optional role/name filters. | Roles, names, states, truncated to keep payload manageable. |

---

## Supporting infrastructure

### BrowserService quick facts
- Manages a pool of Playwright browser instances (`self.browsers`) and pages (`self.pages`) keyed by `session_id`.
- Handles both **managed** (Playwright-launched) and **CDP-attached** sessions. For CDP, only metadata differs; downstream calls remain the same because they operate on Playwright page handles.
- Provides utility methods like `describe_elements`, `get_accessibility_tree`, `find_click_targets`, and `click_by_text` to expose richer semantics than raw Playwright.
- Normalizes errors into project-specific exception classes so the MCP layer can surface actionable messages (e.g., `InvalidSelectorError`, `ElementNotFoundError`).

### SessionManager quick facts
- Keeps lightweight metadata for each active session (creation time, last activity, original session info).
- Exposes `get_all_sessions` and `get_session_info` for potential introspection resources.
- Can run an inactivity cleanup coroutine (disabled by default) to close idle sessions automatically.

### Activity tracking
Each tool updates the manager with:

- `navigate` → `{ "url": ... }`
- `click_element` → `{ "selector": ... }`
- `type_text` → `{ "selector": ..., "text_length": ... }`
- Content/screenshot/diagnostic tools → counts, selector info, format, etc.

This data is handy for telemetry, debugging, or presenting session state in a UI.

---

## Typical automation flows

1. **Bring-your-own browser**
   - Launch Chrome with `--remote-debugging-port=9222`.
   - Call `create_session` with `{}`; it auto-attaches via CDP.
   - Run `find_click_targets` → `click_by_text` to trigger controls.
   - Retrieve a snippet with `get_text_excerpt` or `inspect_elements` to confirm state.
   - Call `close_session` when finished (browser remains open).

2. **Managed headless session**
   - `create_session` with `{ "use_cdp": false, "browser_type": "chromium", "headless": true }`.
   - `navigate` to the target URL.
   - Use `click_element` / `type_text` with deterministic selectors.
   - Capture results with `take_screenshot` (resource URI) and `get_page_content`.
   - `close_session` to release the Playwright browser.

3. **Diagnostics-first debugging**
   - Run `inspect_elements` or `get_accessibility_tree` before attempting clicks.
   - Analyze the returned attributes/roles to craft a better selector or leverage `find_click_targets`.
   - Confirm visibility/enabled state before performing the action.

---

## Error handling & best practices

- Tools consistently raise `MCPError` with nested `details` from domain-specific exceptions so clients can react programmatically.
- Prefer `find_click_targets` + `click_by_text` over screenshotting when an LLM is choosing elements – it keeps the conversation text-based and token efficient.
- When dealing with long-running sessions, periodically poll `SessionManager.get_all_sessions` (resource or future tool) to audit stale entries.
- For UI flows with dynamic content, consider combining `navigate` waits (`wait_until="networkidle"`) with Playwright’s `locator.wait_for` via a custom helper if needed.

---

## Additional resources
- **README** – High-level setup, CDP configuration, and quick prompts.
- **`app/services/browser_service.py`** – Reference for the exact Playwright calls and heuristics (e.g., scoring logic in `find_click_targets`).
- **`app/services/session_service.py`** – Session tracking and idle cleanup logic.

This document should provide enough detail to reason about how each tool behaves, how it manages session state, and how real browser work is executed behind the scenes.
