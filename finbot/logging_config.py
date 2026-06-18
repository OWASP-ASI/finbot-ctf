"""
Logging Configuration for FinBot CTF Platform

This module sets up centralized logging configuration for the entire application.
It should be imported and initialized early in the application lifecycle, before
any other modules that create loggers.
"""

import logging
import sys
from typing import Literal

from finbot.config import settings

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def setup_logging(log_level: str | None = None) -> None:
    """
    Configure logging for the entire application.

    Args:
        log_level: Optional override for log level. If not provided, uses settings.LOG_LEVEL

    """
    level = log_level or settings.LOG_LEVEL
    level_upper = level.upper()
    numeric_level = getattr(logging, level_upper, logging.INFO)

    root_logger = logging.getLogger()

    # Clear any existing handlers to avoid duplicates
    # This is important if setup_logging() is called multiple times
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    class ExtraFormatter(logging.Formatter):
        def format(self, record):
            # Format the base message
            s = super().format(record)
            
            # Extract standard record attributes so we know what is "extra"
            standard_attrs = {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename', 
                'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName', 
                'created', 'msecs', 'relativeCreated', 'thread', 'threadName', 
                'processName', 'process', 'message', 'asctime', 'taskName'
            }
            
            # Find any extra attributes added via logger.info(..., extra={"key": "val"})
            extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}
            
            if extras:
                # Append them in a structured way
                extra_str = " ".join(f"{k}={v}" for k, v in extras.items())
                s += f" | {extra_str}"
                
            return s

    formatter = ExtraFormatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    root_logger.info(
        "Logging configured: level=%s, handler=console",
        level_upper,
    )

    # Configure third-party library logging levels
    # Many libraries are too verbose at DEBUG level
    _configure_third_party_loggers(numeric_level)


def _configure_third_party_loggers(app_level: int) -> None:
    """
    Configure logging levels for third-party libraries.

    Many third-party libraries (like uvicorn, sqlalchemy, redis) can be very
    verbose at DEBUG level. This function sets appropriate levels for them
    to reduce noise while keeping your application logs detailed.

    Args:
        app_level: The application's log level (used as reference)

    """

    # Uvicorn logging (web server)
    # Keep at INFO even if app is at DEBUG to avoid request spam
    logging.getLogger("uvicorn").setLevel(max(app_level, logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    # SQLAlchemy logging (database)
    # SQLAlchemy's DEBUG shows every SQL query - usually too verbose
    # Note: engine echo is enabled by DB_ECHO or DEBUG mode (see config.py)
    if settings.DB_ECHO:
        # If DB_ECHO is explicitly enabled, show SQL queries at INFO level
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    else:
        # Otherwise, suppress SQL query logging (even in DEBUG mode)
        # This reduces noise significantly while keeping app-level DEBUG logs
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

    logging.getLogger("sqlalchemy.pool").setLevel(
        logging.INFO if app_level == logging.DEBUG else logging.WARNING
    )
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)

    # Redis logging (if used for event bus)
    logging.getLogger("redis").setLevel(
        logging.INFO if app_level == logging.DEBUG else logging.WARNING
    )
    logging.getLogger("redis.asyncio").setLevel(logging.WARNING)

    # FastAPI/Starlette logging
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("starlette").setLevel(logging.WARNING)

    # HTTP client libraries (if used)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # OpenAI SDK internals
    logging.getLogger("openai").setLevel(logging.WARNING)


def update_log_level(log_level: str) -> None:
    """
    Dynamically update the logging level at runtime.

    This is useful for debugging - we can temporarily increase verbosity
    without restarting the application.

    Args:
        log_level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    level_upper = log_level.upper()
    numeric_level = getattr(logging, level_upper, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Update all handlers
    for handler in root_logger.handlers:
        handler.setLevel(numeric_level)

    root_logger.info("Log level updated to: %s", level_upper)
