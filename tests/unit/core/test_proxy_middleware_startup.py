import pytest
import logging
import importlib
from unittest.mock import patch

def test_proxy_middleware_startup_warning_when_unset():
    """
    Assert that the startup warning fires when TRUSTED_PROXY_IPS is unset.
    """
    with patch("finbot.main.settings.TRUSTED_PROXY_IPS", None):
        with patch("logging.Logger.warning") as mock_warning:
            import finbot.main
            importlib.reload(finbot.main)
            
            # Check if warning was called with the correct message
            called_with_message = any(
                "TRUSTED_PROXY_IPS is unset" in call_args[0][0]
                for call_args in mock_warning.call_args_list
            )
            assert called_with_message

def test_proxy_middleware_startup_no_warning_when_set():
    """
    Assert that the startup warning does NOT fire when TRUSTED_PROXY_IPS is set.
    """
    with patch("finbot.main.settings.TRUSTED_PROXY_IPS", "10.0.0.1"):
        with patch("logging.Logger.warning") as mock_warning:
            import finbot.main
            importlib.reload(finbot.main)
            
            called_with_message = any(
                "TRUSTED_PROXY_IPS is unset" in call_args[0][0]
                for call_args in mock_warning.call_args_list
            )
            assert not called_with_message
