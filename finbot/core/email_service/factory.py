"""Factory function for email service"""

from finbot.config import settings
from finbot.core.email_service.base import EmailService


def get_email_service() -> EmailService:
    """Get the configured email service instance"""
    if settings.EMAIL_PROVIDER == "resend":
        # pylint: disable=import-outside-toplevel
        from finbot.core.email_service.resend_client import ResendEmailService

        return ResendEmailService()
    # pylint: disable=import-outside-toplevel
    from finbot.core.email_service.console import ConsoleEmailService

    return ConsoleEmailService()
