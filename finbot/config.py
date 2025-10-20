"""Configuration management for FinBot CTF Platform
- Handles environment variables and application settings.
"""

import hashlib
import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import ConfigDict, model_validator
from pydantic_settings import BaseSettings

DatabaseType = Literal["sqlite", "postgresql"]

DEFAULT_SECRET_KEY = "super_long_default_key_change_this_in_production"


class Settings(BaseSettings):
    """Application settings with env variable support"""

    # Database Config
    DATABASE_URL: str = "sqlite://finbot.db"
    DATABASE_TYPE: DatabaseType = "sqlite"

    # Postgres Config
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "finbot"

    # SQLite Config
    SQLITE_DB_PATH: str = "finbot.db"

    # Database Connection settings
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_PRE_PING: bool = True

    # Application Config
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security Config
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    SESSION_SIGNING_KEY: str | None = None  # Derived from SECRET_KEY

    # Session Config
    TEMP_SESSION_TIMEOUT: int = 86400 * 7  # 7 days
    PERM_SESSION_TIMEOUT: int = 86400 * 14  # 14 days
    TEMP_SESSION_ROTATION_INTERVAL: int = 3600 * 3  # Every 3 hours
    PERM_SESSION_ROTATION_INTERVAL: int = 3600  # Every hour - more secure
    # to force reauth based on session age
    MAX_TEMP_SESSION_AGE: int = 86400 * 7  # 7 days
    MAX_PERM_SESSION_AGE: int = 86400 * 30  # 30 days

    # Session Security
    ENABLE_SESSION_ROTATION: bool = True
    ENABLE_FINGERPRINT_VALIDATION: bool = True
    ENABLE_AUTOMATIC_COOKIE_REFRESH: bool = True
    ENABLE_HIJACK_DETECTION: bool = True
    SUSPICIOUS_ROTATION_THRESHOLD: int = 5

    # CSRF Protection
    ENABLE_CSRF_PROTECTION: bool = True
    CSRF_TOKEN_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # Cookie Config
    SESSION_COOKIE_NAME: str = "finbot_session"
    SESSION_COOKIE_SECURE: bool = False  # Set to True in production with https
    SESSION_COOKIE_HTTP_ONLY: bool = True  # Always HTTP-only for security
    SESSION_COOKIE_SAMESITE: str = "Lax"

    # Namespace Config
    NAMESPACE_PREFIX: str = "user_"
    ENABLE_NAMESPACE_ISOLATION: bool = True

    # Development Config
    RELOAD: bool = True
    LOG_LEVEL: str = "info"

    model_config = ConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    @model_validator(mode="after")
    def validate_model(self):
        """Post initialization hook using Pydantic v2 model validator"""
        if not self.DATABASE_TYPE:
            self.DATABASE_TYPE = self._detect_database_type()  # pylint: disable=C0103
        if not self.SESSION_SIGNING_KEY:
            self.SESSION_SIGNING_KEY = self._derive_session_signing_key()  # pylint: disable=C0103
        return self

    def _derive_session_signing_key(self) -> str:
        """Derive the session signing key from the SECRET_KEY"""
        return hashlib.sha256(f"{self.SECRET_KEY}:session_signing".encode()).hexdigest()

    def _detect_database_type(self) -> DatabaseType:
        """Detect the database type from the DATABASE_URL"""
        parsed = urlparse(self.DATABASE_URL)
        scheme = parsed.scheme.lower()

        if scheme.startswith("sqlite"):
            return "sqlite"
        if scheme.startswith(("postgresql", "postgres")):
            return "postgresql"
        return "sqlite"

    def get_database_url(self) -> str:
        """Get the formatted database URL"""

        if self.DATABASE_TYPE == "sqlite":
            return self._get_sqlite_url()
        elif self.DATABASE_TYPE == "postgresql":
            return self._get_postgresql_url()
        else:
            return self.DATABASE_URL

    def _get_sqlite_url(self) -> str:
        """Get the SQLite database URL"""
        if self.DATABASE_URL.startswith("sqlite"):
            if ":///" in self.DATABASE_URL:
                return self.DATABASE_URL
            db_path = self.DATABASE_URL.replace("sqlite://", "")
            return f"sqlite:///{os.path.abspath(db_path)}"
        return f"sqlite:///{os.path.abspath(self.SQLITE_DB_PATH)}"

    def _get_postgresql_url(self) -> str:
        """Get the PostgreSQL database URL"""
        if (
            self.DATABASE_URL.startswith(("postgresql", "postgres"))
            and "localhost" not in self.DATABASE_URL
        ):
            return self.DATABASE_URL
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_database_config(self) -> dict:
        """Get the database specific configuration"""
        base_config = {"echo": self.DB_ECHO or self.DEBUG}
        if self.DATABASE_TYPE == "sqlite":
            base_config.update({"connect_args": {"check_same_thread": False}})
        elif self.DATABASE_TYPE == "postgresql":
            base_config.update(
                {
                    "pool_size": self.DB_POOL_SIZE,
                    "max_overflow": self.DB_MAX_OVERFLOW,
                    "pool_timeout": self.DB_POOL_TIMEOUT,
                    "pool_pre_ping": self.DB_POOL_PRE_PING,
                }
            )
        return base_config


# Global settings instance
settings = Settings()

# ensure secret key is taken care of in production
if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
    if not settings.DEBUG:
        raise ValueError("🚨 SECRET_KEY is not set in production")
    print("⚠️ Warning: using default SECRET_KEY in development mode")

if settings.DATABASE_TYPE not in ["sqlite", "postgresql"]:
    raise ValueError(f"🚨 Unsupported database type: {settings.DATABASE_TYPE}")
