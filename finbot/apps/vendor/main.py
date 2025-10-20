"""Vendor Portal Main Application"""

from fastapi import FastAPI

from finbot.config import settings

from .routes import api_router, web_router

# Create Vendor Portal App
app = FastAPI(
    title="FinBot Vendor Portal",
    description="FinBot Vendor Portal",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Include routers
app.include_router(web_router)
app.include_router(api_router)
