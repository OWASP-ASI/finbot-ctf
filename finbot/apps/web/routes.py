"""
Route handlers for the CineFlow Productions web app
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="finbot/apps/web/templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse(request, "pages/home.html")


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page"""
    return templates.TemplateResponse(request, "pages/about.html")


@router.get("/work", response_class=HTMLResponse)
async def work(request: Request):
    """Our Work page"""
    return templates.TemplateResponse(request, "pages/work.html")


@router.get("/partners", response_class=HTMLResponse)
async def partners(request: Request):
    """Partners page"""
    return templates.TemplateResponse(request, "pages/partners.html")


@router.get("/careers", response_class=HTMLResponse)
async def careers(request: Request):
    """Careers page"""
    return templates.TemplateResponse(request, "pages/careers.html")


@router.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    """Contact page"""
    return templates.TemplateResponse(request, "pages/contact.html")


# Test routes for error pages (for development/testing)
@router.get("/test/404")
async def test_404():
    """Test 404 error page"""
    raise HTTPException(status_code=404, detail="Test 404 error")


# API test routes to demonstrate JSON error responses
@router.get("/api/test/404")
async def api_test_404():
    """Test 404 API error response"""
    raise HTTPException(status_code=404, detail="API endpoint not found")


@router.get("/api/test/500")
async def api_test_500():
    """Test 500 API error response"""
    raise HTTPException(status_code=500, detail="Internal API error")


@router.get("/test/403")
async def test_403():
    """Test 403 error page"""
    raise HTTPException(status_code=403, detail="Test 403 error")


@router.get("/test/400")
async def test_400():
    """Test 400 error page"""
    raise HTTPException(status_code=400, detail="Test 400 error")


@router.get("/test/500")
async def test_500():
    """Test 500 error page"""
    raise HTTPException(status_code=500, detail="Test 500 error")


@router.get("/test/503")
async def test_503():
    """Test 503 error page"""
    raise HTTPException(status_code=503, detail="Test 503 error")
