"""FinBot Labs — FastAPI sub-application for experimental features.

First labs product: Guardrail webhook playground.
"""

from fastapi import FastAPI

from finbot.config import settings
from finbot.core.error_handlers import register_error_handlers

from .routes import guardrails, web

app = FastAPI(
    title="FinBot Labs",
    description="FinBot Labs — experimental features",
    version="0.1.0",
    debug=settings.DEBUG,
)

register_error_handlers(app)

app.include_router(web.router)
app.include_router(guardrails.router)
