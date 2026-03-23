"""
Route handlers for the CineFlow Productions demo tenant website.
Mounted at /demo/cineflow/ -- a fictional company preserved for future IPI scenarios.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from finbot.core.templates import TemplateResponse

template_response = TemplateResponse("finbot/apps/web/templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return template_response(request, "pages/home.html")


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """About page"""
    return template_response(request, "pages/about.html")


@router.get("/work", response_class=HTMLResponse)
async def work(request: Request):
    """Our Work page"""
    return template_response(request, "pages/work.html")


@router.get("/partners", response_class=HTMLResponse)
async def partners(request: Request):
    """Partners page"""
    return template_response(request, "pages/partners.html")


@router.get("/careers", response_class=HTMLResponse)
async def careers(request: Request):
    """Careers page"""
    return template_response(request, "pages/careers.html")


@router.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    """Contact page"""
    return template_response(request, "pages/contact.html")
