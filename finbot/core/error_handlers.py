"""
Error handling utilities and exception handlers for the FinBot platform.
"""

import os
from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def is_api_request(request: Request) -> bool:
    """Determine if the request is for an API endpoint."""
    return request.url.path.startswith("/api/")


def get_json_error_response(status_code: int, detail: str = None) -> Dict[str, Any]:
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


async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions"""
    # Convert FastAPI HTTPException to StarletteHTTPException and reuse handler
    starlette_exc = StarletteHTTPException(
        status_code=exc.status_code, detail=exc.detail
    )
    return await http_exception_handler(request, starlette_exc)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with custom error pages or JSON responses."""

    # Special handling for CSRF errors
    if exc.status_code == 403 and "CSRF" in str(exc.detail):
        if is_api_request(request):
            return JSONResponse(
                content={
                    "error": {
                        "code": 403,
                        "message": "CSRF token validation failed",
                        "type": "csrf_error",
                        "details": exc.detail,
                    }
                },
                status_code=403,
            )
        else:
            # For web requests, show a dedicated CSRF error page
            try:
                with open(
                    "finbot/static/pages/error/403_csrf.html", "r", encoding="utf-8"
                ) as f:
                    content = f.read()
                return HTMLResponse(content=content, status_code=403)
            except FileNotFoundError:
                # Fallback if CSRF error page is missing
                return HTMLResponse(
                    content="<h1>403 Forbidden</h1><p>Security validation failed. Please refresh the page and try again.</p>",
                    status_code=403,
                )

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


def register_error_handlers(app):
    """Register all error handlers with the FastAPI app."""
    app.add_exception_handler(HTTPException, fastapi_http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(404, not_found_handler)
    app.add_exception_handler(500, internal_server_error_handler)
