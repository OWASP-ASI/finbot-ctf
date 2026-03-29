"""Email service module for magic link authentication"""

from finbot.core.email_service.base import EmailService
from finbot.core.email_service.console import ConsoleEmailService
from finbot.core.email_service.factory import get_email_service
from finbot.core.email_service.resend_client import ResendEmailService

__all__ = [
    "EmailService",
    "ConsoleEmailService",
    "ResendEmailService",
    "get_email_service",
]
