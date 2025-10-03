from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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
from app.services.browser_service import BrowserService
from app.services.session_service import SessionManager
from app.api.endpoints import browser

# Setup logging
setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Browser Automation MCP Server with FastAPI",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (can be done via dependency injection in a larger app)
# For simplicity, we'll initialize them globally here for now
# These should ideally be managed as singletons or dependencies
app.browser_service = BrowserService(
    max_browsers=settings.MAX_BROWSER_INSTANCES,
    max_contexts_per_browser=settings.MAX_CONTEXTS_PER_BROWSER,
    headless=settings.BROWSER_HEADLESS,
    timeout=settings.BROWSER_TIMEOUT
)
app.session_manager = SessionManager()
app.browser_service.attach_session_manager(app.session_manager)

# Include API routers
app.include_router(browser.router, prefix="/browser", tags=["Browser Automation"])

@app.get("/", summary="Root endpoint", response_description="Root endpoint of the API")
async def read_root():
    logger.info("Root endpoint accessed.")
    return {"message": "Browser Automation MCP Server is running!", "status": "ok", "version": settings.APP_VERSION}

@app.get("/health", summary="Health check", response_description="Health status of the API")
async def health_check():
    logger.info("Health check endpoint accessed.")
    return {"status": "healthy", "message": "API is operational"}

# Global Exception Handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}", exc_info=True)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "message": exc.detail,
            "status": "error",
            "code": exc.status_code
        }
    )

@app.exception_handler(BrowserAutomationError)
async def browser_automation_exception_handler(request: Request, exc: BrowserAutomationError):
    logger.error(f"Browser Automation Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": exc.message,
            "status": "error",
            "code": "BROWSER_AUTOMATION_ERROR",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(SessionNotFoundError)
async def session_not_found_exception_handler(request: Request, exc: SessionNotFoundError):
    logger.warning(f"Session Not Found Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "message": exc.message,
            "status": "error",
            "code": "SESSION_NOT_FOUND",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(NavigationError)
async def navigation_error_handler(request: Request, exc: NavigationError):
    logger.error(f"Navigation Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": exc.message,
            "status": "error",
            "code": "NAVIGATION_ERROR",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(ElementError)
async def element_error_handler(request: Request, exc: ElementError):
    logger.error(f"Element Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": exc.message,
            "status": "error",
            "code": "ELEMENT_ERROR",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(InvalidURLError)
async def invalid_url_error_handler(request: Request, exc: InvalidURLError):
    logger.error(f"Invalid URL Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "message": exc.message,
            "status": "error",
            "code": "INVALID_URL_ERROR",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(ElementNotFoundError)
async def element_not_found_error_handler(request: Request, exc: ElementNotFoundError):
    logger.warning(f"Element Not Found Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "message": exc.message,
            "status": "error",
            "code": "ELEMENT_NOT_FOUND",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(ElementNotInteractableError)
async def element_not_interactable_error_handler(request: Request, exc: ElementNotInteractableError):
    logger.warning(f"Element Not Interactable Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "message": exc.message,
            "status": "error",
            "code": "ELEMENT_NOT_INTERACTABLE",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(InvalidSelectorError)
async def invalid_selector_error_handler(request: Request, exc: InvalidSelectorError):
    logger.warning(f"Invalid Selector Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "message": exc.message,
            "status": "error",
            "code": "INVALID_SELECTOR",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(MCPError)
async def mcp_error_handler(request: Request, exc: MCPError):
    logger.error(f"MCP Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": exc.message,
            "status": "error",
            "code": "MCP_ERROR",
            "details": exc.details
        }
    )

@app.exception_handler(ToolNotFoundError)
async def tool_not_found_error_handler(request: Request, exc: ToolNotFoundError):
    logger.warning(f"Tool Not Found Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "message": exc.message,
            "status": "error",
            "code": "TOOL_NOT_FOUND",
            "details": exc.to_dict()
        }
    )

@app.exception_handler(InvalidToolArgumentsError)
async def invalid_tool_arguments_error_handler(request: Request, exc: InvalidToolArgumentsError):
    logger.warning(f"Invalid Tool Arguments Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "message": exc.message,
            "status": "error",
            "code": "INVALID_TOOL_ARGUMENTS",
            "details": exc.to_dict()
        }
    )

@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI application startup event.")
    # Perform any startup tasks here, e.g., initializing browser service pools

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FastAPI application shutdown event.")
    # Perform any shutdown tasks here, e.g., closing browser instances
    await app.browser_service.close_all_browsers()

