"""
Error handling utilities and exception handlers for the FinBot platform.
"""

from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.templating import Jinja2Templates

error_templates = Jinja2Templates(directory="finbot/templates/errors")

PORTAL_ROUTES = {
    "/vendor": ("/vendor/dashboard", "Back to Vendor Portal"),
    "/ctf": ("/ctf/dashboard", "Back to CTF Portal"),
    "/admin": ("/admin/dashboard", "Back to Admin Portal"),
}
DEFAULT_BACK = ("/", "Back to Home")


def is_api_request(request: Request) -> bool:
    """Determine if the request is for an API endpoint."""
    return request.url.path.startswith("/api/")


def get_portal_context(request: Request) -> dict:
    """Derive back_url and back_label from the request path.

    In mounted sub-apps, request.url.path is relative to the mount point,
    so we check root_path (the mount prefix) first, then fall back to the
    full URL path for requests handled by the root app.
    """
    root_path = request.scope.get("root_path", "")
    full_path = root_path + request.url.path
    for prefix, (url, label) in PORTAL_ROUTES.items():
        if full_path.startswith(prefix):
            return {"back_url": url, "back_label": label}
    return {"back_url": DEFAULT_BACK[0], "back_label": DEFAULT_BACK[1]}


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


def get_error_template_name(status_code: int) -> str:
    """Get the template name for a given status code."""
    known = {400, 401, 403, 404, 500, 503}
    if status_code in known:
        return f"{status_code}.html"
    if 400 <= status_code < 500:
        return "400.html"
    if 500 <= status_code < 600:
        return "500.html"
    return "404.html"


def render_error_page(request: Request, status_code: int, template_name: str = None):
    """Render an error page template with portal-aware context."""
    name = template_name or get_error_template_name(status_code)
    ctx = get_portal_context(request)
    return error_templates.TemplateResponse(
        request=request, name=name, context=ctx, status_code=status_code
    )


async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions"""
    starlette_exc = StarletteHTTPException(
        status_code=exc.status_code, detail=exc.detail
    )
    return await http_exception_handler(request, starlette_exc)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with custom error pages or JSON responses."""

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
        return render_error_page(request, 403, template_name="403_csrf.html")

    if is_api_request(request):
        error_data = get_json_error_response(exc.status_code, exc.detail)
        return JSONResponse(content=error_data, status_code=exc.status_code)

    return render_error_page(request, exc.status_code)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with 400 error page or JSON response."""
    if is_api_request(request):
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

    return render_error_page(request, 400)


async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors with custom error page or JSON response."""
    if is_api_request(request):
        error_data = get_json_error_response(404, exc.detail)
        return JSONResponse(content=error_data, status_code=404)

    return render_error_page(request, 404)


async def internal_server_error_handler(request: Request, exc: Exception):
    """Handle 500 errors with custom error page or JSON response."""
    if is_api_request(request):
        # exc may be any exception type (not just HTTPException), so use
        # getattr to safely retrieve .detail; fall back to str(exc) otherwise.
        detail = getattr(exc, "detail", None) or str(exc) or "Internal Server Error"
        error_data = get_json_error_response(500, detail)
        return JSONResponse(content=error_data, status_code=500)

    return render_error_page(request, 500)


def register_error_handlers(app):
    """Register all error handlers with the FastAPI app."""
    app.add_exception_handler(HTTPException, fastapi_http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(404, not_found_handler)
    app.add_exception_handler(500, internal_server_error_handler)
