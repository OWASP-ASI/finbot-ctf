"""
FinBot Platform Main Application
- Serves all the applications for the FinBot platform.
"""

import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from finbot.apps.vendor.main import app as vendor_app
from finbot.apps.web.routes import router as web_router
from finbot.core.auth.middleware import SessionMiddleware, get_session_context
from finbot.core.auth.session import SessionContext, session_manager

app = FastAPI(
    title="FinBot Platform",
    description="FinBot Application Platform",
    version="0.1.0",
)

app.add_middleware(SessionMiddleware)

# Mount Static Files
app.mount("/static", StaticFiles(directory="finbot/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# Mount all the applications for the platform
app.mount("/vendor", vendor_app)
# Web application is mounted at the root of the platform
app.include_router(web_router)


# web agreement handler
@app.get("/agreement", response_class=HTMLResponse)
async def agreement(_: Request):
    """FinBot Agreement page"""
    try:
        # (TODO) cache this to reduce disk I/O
        with open("finbot/static/pages/agreement.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=200)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Agreement page not found") from e


# Session health check endpoint
@app.get("/api/session/status")
async def session_status(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get current session status and security information"""
    return {
        "session_id": session_context.session_id[:8] + "...",
        "user_id": session_context.user_id,
        "is_temporary": session_context.is_temporary,
        "namespace": session_context.namespace,
        "security_status": session_context.get_security_status(),
        "csrf_token": session_context.csrf_token,
    }


# Helper functions for error handling
def is_api_request(request: Request) -> bool:
    """Determine if the request is for an API endpoint."""
    return request.url.path.startswith("/api/")


def get_json_error_response(status_code: int, detail: str = None) -> dict:
    """Create a standardized JSON error response."""
    error_messages = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        422: "Unprocessable Entity",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    message = detail or error_messages.get(status_code, "An error occurred")

    return {"error": {"code": status_code, "message": message, "type": "api_error"}}


# Error handlers
def get_error_page_path(status_code: int) -> str:
    """Get the path to the error page for a given status code."""
    error_page = f"finbot/static/pages/error/{status_code}.html"
    if os.path.exists(error_page):
        return error_page
    # Fallback to generic error page based on status code range
    if 400 <= status_code < 500:
        return "finbot/static/pages/error/400.html"
    elif 500 <= status_code < 600:
        return "finbot/static/pages/error/500.html"
    else:
        return "finbot/static/pages/error/404.html"


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with custom error pages or JSON responses."""
    # Return JSON response for API requests
    if is_api_request(request):
        error_data = get_json_error_response(exc.status_code, exc.detail)
        return JSONResponse(content=error_data, status_code=exc.status_code)

    # Return HTML response for web requests
    error_page_path = get_error_page_path(exc.status_code)

    try:
        with open(error_page_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=exc.status_code)
    except FileNotFoundError:
        # Fallback to basic error response if error page is missing
        return HTMLResponse(
            content=f"<h1>Error {exc.status_code}</h1><p>{exc.detail}</p>",
            status_code=exc.status_code,
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with 400 error page or JSON response."""
    # Return JSON response for API requests
    if is_api_request(request):
        # Format validation errors for API response
        error_details = []
        for error in exc.errors():
            error_details.append(
                {
                    "field": " -> ".join(str(loc) for loc in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

        error_data = {
            "error": {
                "code": 422,
                "message": "Validation Error",
                "type": "validation_error",
                "details": error_details,
            }
        }
        return JSONResponse(content=error_data, status_code=422)

    # Return HTML response for web requests
    error_page_path = get_error_page_path(400)

    try:
        with open(error_page_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=400)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error 400</h1><p>Bad Request</p>", status_code=400
        )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors with custom error page or JSON response."""
    # Return JSON response for API requests
    if is_api_request(request):
        error_data = get_json_error_response(404, exc.detail)
        return JSONResponse(content=error_data, status_code=404)

    # Return HTML response for web requests
    error_page_path = get_error_page_path(404)

    try:
        with open(error_page_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=404)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error 404</h1><p>Page Not Found</p>", status_code=404
        )


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: HTTPException):
    """Handle 500 errors with custom error page or JSON response."""
    # Return JSON response for API requests
    if is_api_request(request):
        error_data = get_json_error_response(500, exc.detail)
        return JSONResponse(content=error_data, status_code=500)

    # Return HTML response for web requests
    error_page_path = get_error_page_path(500)

    try:
        with open(error_page_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=500)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error 500</h1><p>Internal Server Error</p>", status_code=500
        )


# (TODO): add to lifecycle management
@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    # Clean up expired sessions on startup
    cleaned_count = session_manager.cleanup_expired_sessions()
    if cleaned_count > 0:
        print(f"🧹 Cleaned up {cleaned_count} expired sessions on startup")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
