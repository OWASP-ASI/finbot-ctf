"""
FinBot Platform Main Application Entry Point
- Runs bootstrap (migrations, seeding, etc.) then launches uvicorn.
"""

import importlib.util
from pathlib import Path

import uvicorn

from finbot.config import settings


def _load_bootstrap():
    """Load run_bootstrap from scripts/bootstrap.py without requiring __init__.py."""
    spec = importlib.util.spec_from_file_location(
        "bootstrap", Path(__file__).parent / "scripts" / "bootstrap.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_bootstrap


if __name__ == "__main__":
    print("🚀 Starting FinBot CTF Platform")
    print(f"📍 Server will run at http://{settings.HOST}:{settings.PORT}")
    print(f"📋 Application log level: {settings.LOG_LEVEL.upper()}")

    # One-time bootstrap: migrations, seeding, cleanup, CTF definitions.
    # Runs once in the main process before uvicorn forks reload workers.
    run_bootstrap = _load_bootstrap()
    run_bootstrap()

    # Note: Application logging is configured in finbot.main when the module loads
    # The log_level parameter here only controls uvicorn's own logging
    uvicorn.run(
        "finbot.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning",
    )
