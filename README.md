# Browser Automation MCP Server

Browser automation tools and resources exposed over the Model Context Protocol (MCP), plus an optional FastAPI REST API. Playwright powers the browser automation.

## Features
- ✅ **Universal browser control** – Navigate, click, type, capture content, extract links, take screenshots, and even drive your own Chrome/Edge via CDP.
- 🧠 **Smart session creation** – `create_session` auto-detects a local debugging browser, falling back to a managed Playwright instance when none exists.
- 📡 **Resource exports** – Stream page content, screenshots, and session metadata through MCP resources for downstream tools.
- 🔍 **Text-first page insight** – Use `inspect_elements` and `get_accessibility_tree` to understand the live DOM structure without resorting to screenshots.
- 🎯 **Heuristic action helpers** – `find_click_targets` ranks likely buttons/links (e.g., play controls) and `click_by_text` activates visible matches while honoring ARIA roles.
- 🖥️ **Bring-your-own browser** – Attach to an existing Chrome/Edge profile with remote debugging for full-fidelity automation on your own tabs.
- ⚙️ **FastAPI companion app** – Optional REST interface for integrating browser automation into traditional workflows.

## Project structure
- `mcp_server.py` – MCP server wiring using `mcp.server` (stdio transport).
- `browser_mcp/` – FastMCP app with tool/resource registrations and shared context.
- `app/` – FastAPI app, core config/logging/security, and services (Playwright + sessions).
- `logs/` – Rotating application logs when running the FastAPI server.
- `scripts/` – Utility scripts (seed/test helpers, etc.).

## Setup instructions

### Prerequisites
- **Python 3.9+** from [python.org](https://www.python.org/downloads/).
- **uv** package manager (optional but recommended):

```bash
pip install uv
```

### 1. Clone (or extract) the repository
```bash
# If working from an archive, extract and change into the directory
# tar -xzf browser_automation_mcp_server_uv.tar.gz
cd C:\Users\astra\Desktop\browser_automation_mcp_server_uv
```

### 2. Install dependencies with `uv`
```bash
uv pip install -r requirements.txt
```
This automatically creates an isolated environment (e.g., `.venv`) and installs the Python dependencies.

### 3. Install Playwright browsers
```bash
uv run playwright install
```
Downloads Chromium, Firefox, and WebKit so Playwright can launch them.

## Running the servers

### Start the MCP server
```bash
cd C:\Users\astra\Desktop\browser_automation_mcp_server_uv
uv run python mcp_server.py
```
The server listens over stdio for an MCP client (e.g., Claude Desktop). No HTTP port is exposed.

### Start the FastAPI application (optional)
```bash
cd C:\Users\astra\Desktop\browser_automation_mcp_server_uv
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Then open http://localhost:8000/docs for interactive API exploration.

## Configure a user-controlled browser for automation
You can control an already-open (visible) browser using Chrome DevTools Protocol (CDP). This keeps your cookies, extensions, and sign-ins intact.

### 1. Launch Chrome/Edge with remote debugging enabled
Pick a dedicated user data directory so you don’t disturb existing sessions.

**Windows (PowerShell)**
```powershell
# Google Chrome
"C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\temp\chrome-debug"

# Microsoft Edge
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\temp\edge-debug"
```

**macOS (Terminal)**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-debug"

/Applications/Microsoft\ Edge.app/Contents/MacOS/Microsoft\ Edge \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.edge-debug"
```

**Linux (Shell)**
```bash
/usr/bin/google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.chrome-debug"
/usr/bin/microsoft-edge --remote-debugging-port=9222 --user-data-dir="$HOME/.edge-debug"
```

Tips:
- Use a path you can write to; Playwright will create the directory if needed.
- `9222` is the default port; change it if already in use (remember to update the `cdp_url`).
- Keep the debug-launched browser running while you need automation; closing it ends the CDP connection.

### 2. Verify the debugging endpoint
Visit http://localhost:9222/json/version in any browser. Seeing JSON with a `webSocketDebuggerUrl` confirms the debugging port is active. If it fails, check the port, firewall, or VPN restrictions.

### 3. Attach from MCP tools
- Call `connect_cdp` with `{ "cdp_url": "http://localhost:9222", "create_new_page": true }`, **or**
- Call `create_session` with `{}` (auto-detect). It will try CDP first and only launch a managed browser if the port is unavailable.

Once attached, the response includes a `session_id`. Use the standard tools (`navigate`, `find_click_targets`, `click_by_text`, etc.) to drive the page. When finished, call `close_session`; the user’s browser stays open with its state intact.

### Troubleshooting CDP
- **Port already in use** – Pick a different port (e.g., 9223) and update the launch command and `cdp_url`.
- **Connection refused / firewall** – Allow loopback connections to `localhost:<port>`; some VPNs block them.
- **MCP still launches headless Chromium** – Ensure the debugging browser is running and the `/json/version` endpoint responds before calling `create_session`.
- **Noisy extensions** – Use a fresh `--user-data-dir` to avoid popups; you can still sign into sites as needed.

## Windows PowerShell quickstart (alternate to `uv`)
```powershell
# From project root
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install
```
Update `%APPDATA%\Claude\claude_desktop_config.json` to point at `mcp_server.py`, then restart Claude Desktop.

## MCP quick tests (prompt ideas)
- `create_session` with `{}` – attaches to CDP if available, otherwise launches Chromium headless.
- `connect_cdp` with `{ "cdp_url": "http://localhost:9222", "create_new_page": true }` – explicitly attach to your visible browser.
- `navigate` with `{ "session_id": "<SESSION_ID>", "url": "https://example.com" }`.
- `find_click_targets` with `{ "session_id": "<SESSION_ID>", "text": "Play", "preferred_roles": ["button"] }`.
- `click_by_text` with `{ "session_id": "<SESSION_ID>", "text": "Play", "preferred_roles": ["button"], "exact": false }`.
- `inspect_elements`, `get_accessibility_tree`, `get_page_content`, `take_screenshot`, and finally `close_session`.

## Understand pages without screenshots
- `inspect_elements` returns structured data (text, attributes, bounding boxes) for up to N matches.
- `get_accessibility_tree` streams a truncated accessibility snapshot so you can reason about the UI hierarchy.
- `find_click_targets` ranks likely interactive controls by matching text, ARIA labels, titles, and custom attributes; pair it with `click_by_text` for a selector-free click.
- Prefer these text-only diagnostics before falling back to `take_screenshot` to stay token-friendly.

## Token-safe screenshots
- `take_screenshot` returns a `resource_uri` by default instead of inline base64.
- Read the URI via your MCP client (e.g., `screenshot/<SESSION_ID>?full_page=false&format=png`).
- Set `return_image: true` only when you must embed the image data inline.

Inputs: `full_page`, `image_format`, optional `quality`, and `return_image`.
Outputs: `resource_uri` + `mime_type`, or `image_data` when inline.

## Troubleshooting
- **`ModuleNotFoundError`** – Activate the environment or run commands via `uv run`.
- **`TypeError: 'Settings' object is not subscriptable`** – Ensure `app/core/config.py` exposes attributes (use `settings.APP_VERSION`).
- **`AttributeError: 'Server' object has no attribute 'register_tool'`** – Update `mcp_server.py` to the decorator-based implementation.
- **`ValidationError` for tool/resource schemas** – Confirm your schema dicts start with `{ "type": "object", ... }`.
- **Playwright launch issues** – `uv run playwright install --with-deps` (or `python -m playwright install`) to fetch missing browsers/deps.
- Logs are written to `logs/app.log` when using the FastAPI server.

## License
MIT (or your preferred license)


