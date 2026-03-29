"""Console email service for development - prints magic links to console"""

from finbot.core.email_service.base import EmailService


class ConsoleEmailService(EmailService):
    """Development email service that logs to console"""

    async def send_magic_link(self, to_email: str, magic_link: str) -> bool:
        """Print magic link to console instead of sending email"""
        print("\n" + "=" * 60)
        print("📧 MAGIC LINK EMAIL (Console Mode)")
        print("=" * 60)
        print(f"To: {to_email}")
        print("Subject: Sign in to OWASP ASI FinBot CTF")
        print("-" * 60)
        print("Click the link below to sign in:\n")
        print(f"  {magic_link}")
        print("\n" + "=" * 60 + "\n")
        return True
