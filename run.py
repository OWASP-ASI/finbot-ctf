"""
FinBot Platform Main Application Entry Point
- Launches web apps and api endpoints.
"""

import uvicorn

from finbot.config import settings

if __name__ == "__main__":
    print("🚀 Starting FinBot CTF Platform")
    print(f"📍 Server will run at http://{settings.HOST}:{settings.PORT}")

    uvicorn.run(
        "finbot.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning",
    )
