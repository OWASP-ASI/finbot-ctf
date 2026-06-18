import pytest
import logging
from unittest.mock import patch
from finbot.core.auth.session import SessionManager

@pytest.fixture
def session_manager():
    return SessionManager()

@pytest.mark.parametrize("trusted_proxy_ips, expected_trusted_source", [
    (None, False),
    ("10.0.0.1,127.0.0.1", True)
])
def test_session_ip_change_logging(
    session_manager, 
    trusted_proxy_ips, 
    expected_trusted_source, 
    caplog, 
    db
):
    """
    Assert that IP-change heuristics correctly add structured `trusted_source` flags
    based on the TRUSTED_PROXY_IPS configuration.
    """
    with patch("finbot.core.auth.session.settings.TRUSTED_PROXY_IPS", trusted_proxy_ips):
        with caplog.at_level(logging.INFO):
            # Create a session with an initial IP
            session_context = session_manager.create_session(
                ip_address="192.168.1.1"
            )
            
            # Retrieve session with a different IP to trigger the heuristic
            session_manager.get_session(
                session_id=session_context.session_id,
                current_ip="192.168.1.2",
                _db=db
            )
            
            # Check log records
            log_records = [r for r in caplog.records if "IP change" in r.getMessage()]
            assert len(log_records) == 1
            assert getattr(log_records[0], "app.trusted_source") == expected_trusted_source
