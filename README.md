# Browser Automation MCP Server

Browser automation tools and resources exposed over the Model Context Protocol (MCP), plus an optional FastAPI REST API. Playwright powers the browser automation.

## Features

- ✅ **Universal browser control** − Navigate, click, type, capture content, extract links, take screenshots, and even drive your own Chrome/Edge via CDP.
- 🧠 **Smart session creation** − `create_session` auto-detects a local debugging browser, falling back to a managed Playwright instance when none exists.
- 📡 **Resource exports** − Stream page content, screenshots, and session metadata through MCP resources for downstream tools.
- 🔍 **Text-first page insight** − Use `inspect_elements` and `get_accessibility_tree` to understand the live DOM structure without resorting to screenshots.
- ⚙️ **FastAPI companion app** − Optional REST interface for integrating browser automation into traditional workflows.

## Setup Instructions

Follow these steps to set up and run the Browser Automation MCP Server on your local machine.

## Architecture at a glance

- **`browser_mcp/`** – FastMCP app built with decorator-registered tools/resources and a lifespan-managed `AppContext`.
- **`app/services/`** – Playwright-backed browser/session services plus CDP helpers for visible Chrome/Edge.
- **`mcp_server.py`** – CL-friendly entrypoint that wires logging, configures the FastMCP instance, and serves over stdio.
- **`app/main.py`** – Optional FastAPI app mirroring the MCP capabilities for REST integrations.

### Prerequisites

Before you begin, ensure you have the following installed:

 *   **Python 3.9+**: Download from [python.org](https://www.python.org/downloads/).
 *   **uv**: A fast Python package installer and resolver. If you don't have it, install it using pip:
     ```bash
     pip install uv
     ```

### 1. Clone the Repository

First, clone this repository to your local machine:

```bash
# Assuming you have received the project archive, extract it.
# For example, if it's a .tar.gz file:
# tar -xzf browser_automation_mcp_server_uv.tar.gz
# cd browser_automation_mcp_server_uv
```

### 2. Install Dependencies using `uv`

Navigate to the project root directory (where `requirements.txt` is located) and install the dependencies. `uv` will automatically create a virtual environment if one doesn't exist.

```bash
cd C:\Users\astra\Desktop\browser_automation_mcp_server_uv
uv pip install -r requirements.txt
```

This command will:
 *   Create a virtual environment (e.g., `.venv` or `env`) if it doesn't exist.
 *   Install all required Python packages listed in `requirements.txt` into this environment.

### 3. Install Playwright Browsers

After installing the Python dependencies, you need to install the actual browser binaries that Playwright will use. This is done via the `playwright` command-line tool, which is installed as part of the `playwright` Python package.

```bash
uv run playwright install
```

This command will download and install Chromium, Firefox, and WebKit browsers.

## Running the Servers

The Browser Automation MCP Server consists of two main components that need to run concurrently:

1.  **The MCP Server**: Handles the Model Context Protocol communication and registers the browser automation tools and resources.
2.  **The FastAPI Application**: Provides a RESTful API for interacting with the browser automation functionalities.

### 1. Start the MCP Server

Open your first terminal window, navigate to the project root directory, and run the MCP server:

```bash
cd C:\Users\astra\Desktop\browser_automation_mcp_server_uv
uv run python mcp_server.py
```

The MCP server runs over stdio and waits for an MCP client (e.g., Claude Desktop). No HTTP port is opened.

### 2. Start the FastAPI Application

Open a **second terminal window**, navigate to the project root directory, and run the FastAPI application using Uvicorn:

```bash
cd C:\Users\astra\Desktop\browser_automation_mcp_server_uv
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

*   `--host 0.0.0.0`: Makes the server accessible from any IP address.
*   `--port 8000`: Specifies the port for the FastAPI server.
*   `--reload`: Enables auto-reloading of the server when code changes are detected (useful during development).

You should see output indicating that the FastAPI application is running on `http://0.0.0.0:8000`.

### 3. Access the API Documentation

Once both servers are running, you can access the interactive API documentation (Swagger UI) for the FastAPI application by opening your web browser and navigating to:

[http://localhost:8000/docs](http://localhost:8000/docs)

Here, you can explore all available endpoints for browser automation, test them, and understand their request/response schemas.

## Troubleshooting

*   **`ModuleNotFoundError`**: Ensure you are running commands with `uv run` or that your virtual environment is activated (`source .venv/bin/activate` on Linux/macOS, `.\.venv\Scripts\Activate.ps1` on Windows PowerShell, or `.\.venv\Scripts\activate.bat` on Windows Command Prompt).
*   **`TypeError: 'Settings' object is not subscriptable`**: This indicates a version mismatch or incorrect file content. Ensure your `app/main.py` and `app/core/config.py` files are exactly as provided in the latest codebase. This error specifically means `settings["APP_VERSION"]` is being used instead of `settings.APP_VERSION`.
*   **`AttributeError: 'Server' object has no attribute 'register_tool'`**: This means your `mcp_server.py` is not updated to use the decorator-based tool registration. Ensure you have the latest `mcp_server.py` content.
*   **`ValidationError` for Tool/Resource schemas**: Ensure that your `input_schema` and `output_schema` dictionaries within `@Tool` and `@Resource` decorators start with `"type": "object",`.
*   **Playwright Browser Issues**: If browsers fail to launch, try `uv run playwright install --with-deps` to ensure all system dependencies are met.

If you encounter persistent issues, please provide the full error traceback and the exact commands you are running. 

## Windows setup (PowerShell)
From the project root: `C:\Users\astra\Desktop\browser_automation_mcp_server_uv`

1) Create/activate venv and install deps
```powershell
# Create venv (if not already present)
py -3.11 -m venv .venv
# Activate venv
.\.venv\Scripts\Activate.ps1
# Install Python packages
python -m pip install -r requirements.txt
# Install Playwright browsers
python -m playwright install
```

2) Use with Claude Desktop (MCP)
- Edit config file: %APPDATA%\Claude\claude_desktop_config.json
- Add this entry:
```json
{
    "mcpServers": {
        "browser-automation": {
        "command": "C:/Users/astra/Desktop/browser_automation_mcp_server_uv/.venv/Scripts/python.exe",
        "args": ["C:/Users/astra/Desktop/browser_automation_mcp_server_uv/mcp_server.py"],
            "cwd": "C:/Users/astra/Desktop/browser_automation_mcp_server_uv",
            "env": {}
        }
    }
}
```
- Restart Claude Desktop, open a new chat, and ask: “List available tools.”

3) Optional: run FastAPI locally
```powershell
# From an activated venv
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# Open docs
# http://127.0.0.1:8000/docs
```

## MCP quick tests (prompts for Claude)
- Use tool create_session with empty arguments `{}` – it will first try to attach to Chrome at `http://localhost:9222` and fall back to launching Playwright if none is available.
- Force a new automation browser with { "use_cdp": false, "browser_type": "chromium", "headless": true }.
- Explicitly attach to a specific debugging endpoint with { "use_cdp": true, "cdp_url": "http://localhost:9222" } after starting Chrome with remote debugging to drive your own browser profile.
- Use tool navigate with arguments: { "session_id": "<SESSION_ID>", "url": "https://example.com" }
- Use tool click_element with arguments: { "session_id": "<SESSION_ID>", "selector": "a.more-info" }
- Use tool type_text with arguments: { "session_id": "<SESSION_ID>", "selector": "input[name='q']", "text": "playwright mcp" }
- Use tool get_page_content with arguments: { "session_id": "<SESSION_ID>" }
- Use tool take_screenshot with arguments: { "session_id": "<SESSION_ID>", "full_page": true }
- Use tool inspect_elements when a selector fails: { "session_id": "<SESSION_ID>", "selector": "ytmusic-responsive-list-item-renderer", "max_elements": 5 }
- Use tool get_accessibility_tree to list the screen-reader visible items: { "session_id": "<SESSION_ID>", "role_filter": ["link", "button"] }
- Use tool close_session with arguments: { "session_id": "<SESSION_ID>" }

### Understand pages without screenshots

- `inspect_elements` returns up to N matches for a selector (tag, text, attributes, visibility, bounding box, optional HTML preview). Perfect for disambiguating long selector lists or diagnosing “element not visible” errors.
- `get_accessibility_tree` streams a truncated accessibility snapshot (roles, names, state flags) so the LLM can reason about the UI hierarchy using plain text.
- Prefer these text-only diagnostics before falling back to `take_screenshot`; they keep conversations token-friendly and work even when the client cannot display images.

Resources:
- Read resource active_sessions
- Read resource session_info/<SESSION_ID>
 - Read resource page_content/<SESSION_ID>?format=html&selector=
 - Read resource screenshot/<SESSION_ID>?full_page=true&format=png

### Token-safe screenshots
- By default, `take_screenshot` returns a `resource_uri` (not inline base64) to avoid blowing token limits in chat UIs.
- To fetch the binary image, ask your client to read the returned resource URI (e.g., `screenshot/<SESSION_ID>?full_page=false&format=png`).
- If you absolutely need inline data, set `return_image: true` (beware: large payloads).

Inputs:
- `full_page` (bool): capture entire scrollable page.
- `image_format` ("png"|"jpeg") and optional `quality` (for jpeg).
- `return_image` (bool, default false): inline `image_data`.

Outputs:
- `resource_uri` and `mime_type` (default path), or `image_data` when `return_image=true`.

### Connect to your own visible Chrome (CDP)
1) Start Chrome with remote debugging:
     - Windows PowerShell:
         "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome-debug"
2) Use tool `connect_cdp` with arguments: { "cdp_url": "http://localhost:9222", "create_new_page": true } or simply call `create_session` with `{}` (auto-detect) or `{ "use_cdp": true, "cdp_url": "http://localhost:9222", "create_new_page": true }` to attach in a single step.
3) Navigate, click, type as usual. Closing the session will not close your Chrome.

## Troubleshooting
- Playwright browsers: If a first run fails, try installing again in the active venv:
```powershell
python -m playwright install
```
- Claude cannot start server: Recheck paths in claude_desktop_config.json point to your venv Python and mcp_server.py.
- Nothing happens when running mcp_server.py directly: That’s expected; it waits for an MCP client over stdio.
- Logs: see `logs/app.log`.
 - Screenshot responses too large: Don’t request inline `image_data`. Use the default `resource_uri` returned by `take_screenshot` and read that resource.

## Project structure
- `mcp_server.py`: MCP server wiring using mcp.server (stdio transport).
- `app/`: FastAPI app, core config/logging/security, and services (Playwright + sessions).

## License
MIT (or your preferred license)


