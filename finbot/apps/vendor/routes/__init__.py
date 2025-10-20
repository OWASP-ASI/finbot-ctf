"""Vendor Portal Routes"""

from .api import router as api_router
from .web import router as web_router

__all__ = ["api_router", "web_router"]
