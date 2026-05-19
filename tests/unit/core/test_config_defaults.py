import pytest
from unittest.mock import patch
from finbot.config import Settings

def test_session_cookie_secure_default_when_env_missing(monkeypatch, tmp_path):
    """
    Assert that when SESSION_COOKIE_SECURE is completely absent from the environment,
    the code-level default firmly evaluates to True.
    """
    # Change into an empty temporary directory to ensure no local .env files can be discovered
    monkeypatch.chdir(tmp_path)
    
    # Ensure it's totally removed from the environment
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    
    # Instantiate Settings directly (bypassing any cached singletons).
    # Pass _env_file=None to ensure Pydantic doesn't read a stray .env file in the test dir.
    test_settings = Settings(_env_file=None)
    
    assert test_settings.SESSION_COOKIE_SECURE is True
