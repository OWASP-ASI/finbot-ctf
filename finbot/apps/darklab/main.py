"""Dark Lab Portal Main Application"""

from fastapi import FastAPI

from finbot.config import settings
from finbot.core.error_handlers import register_error_handlers

from .routes import api_router, web_router

app = FastAPI(
    title="FinBot Dark Lab",
    description="Dark Lab -- adversary-perspective threat surface for supply chain attacks and exfiltration",
    version="0.1.0",
    debug=settings.DEBUG,
)

register_error_handlers(app)

app.include_router(web_router)
app.include_router(api_router)
