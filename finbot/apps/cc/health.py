"""Platform health checks for Command Center"""

import os
import time

import httpx
from sqlalchemy import text

from finbot.config import settings
from finbot.core.data.database import SessionLocal


def check_database() -> dict:
    """Check database connectivity and measure latency"""
    db = SessionLocal()
    try:
        start = time.monotonic()
        db.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": "error", "latency_ms": None, "error": str(e)[:100]}
    finally:
        db.close()


def check_redis() -> dict:
    """Check Redis connectivity and measure latency"""
    try:
        import redis as redis_lib  # pylint: disable=import-outside-toplevel

        start = time.monotonic()
        r = redis_lib.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        r.close()
        return {"status": "ok", "latency_ms": latency_ms}
    except ImportError:
        return {"status": "unavailable", "latency_ms": None, "error": "redis package not installed"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": "error", "latency_ms": None, "error": str(e)[:100]}


def check_llm() -> dict:
    """Check LLM provider availability"""
    if not settings.OPENAI_API_KEY:
        return {"status": "unavailable", "detail": "No API key configured"}

    try:
        from openai import OpenAI  # pylint: disable=import-outside-toplevel

        start = time.monotonic()
        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=5)
        client.models.list()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency_ms, "provider": settings.LLM_PROVIDER}
    except ImportError:
        return {"status": "unavailable", "detail": "openai package not installed"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": "error", "latency_ms": None, "error": str(e)[:100]}


def check_ctf_engine() -> dict:
    """Check if the CTF event processor is running"""
    try:
        from finbot.ctf.processor import get_processor  # pylint: disable=import-outside-toplevel

        processor = get_processor()
        if processor and getattr(processor, "_running", False):
            return {"status": "ok", "detail": "Event processor running"}
        if processor:
            return {"status": "error", "detail": "Event processor initialized but not running"}
        return {"status": "error", "detail": "Event processor not initialized"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": "error", "detail": str(e)[:100]}


def check_db_size() -> dict:
    """Check database size"""
    db = SessionLocal()
    try:
        if settings.DATABASE_TYPE == "sqlite":
            db_path = settings.SQLITE_DB_PATH
            if os.path.exists(db_path):
                size_bytes = os.path.getsize(db_path)
                return {"status": "ok", "size_mb": round(size_bytes / (1024 * 1024), 1)}
            return {"status": "error", "detail": "DB file not found"}
        else:
            result = db.execute(
                text("SELECT pg_database_size(current_database())")
            ).scalar()
            size_mb = round(result / (1024 * 1024), 1) if result else 0
            return {"status": "ok", "size_mb": size_mb}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": "error", "detail": str(e)[:100]}
    finally:
        db.close()


def _check_endpoint(path: str) -> dict:
    """HTTP GET a local endpoint and measure response time"""
    base_url = settings.MAGIC_LINK_BASE_URL.rstrip("/")
    url = f"{base_url}{path}"
    try:
        start = time.monotonic()
        resp = httpx.get(url, timeout=5, follow_redirects=True)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        status = "ok" if resp.status_code < 500 else "error"
        return {"status": status, "latency_ms": latency_ms, "status_code": resp.status_code}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"status": "error", "latency_ms": None, "error": str(e)[:100]}


def check_ctf_apps() -> dict:
    """Check each CTF app portal endpoint independently"""
    endpoints = {
        "Home": "/",
        "Vendor Portal": "/vendor",
        "Admin Portal": "/admin",
        "CTF Portal": "/ctf",
    }
    return {name: _check_endpoint(path) for name, path in endpoints.items()}


def get_all_health() -> dict:
    """Run all health checks and return results"""
    return {
        "ctf_apps": check_ctf_apps(),
        "database": check_database(),
        "redis": check_redis(),
        "llm": check_llm(),
        "ctf_engine": check_ctf_engine(),
        "db_size": check_db_size(),
    }
