"""Resend email service implementation"""

import logging

from finbot.config import settings
from finbot.core.email.base import EmailService

logger = logging.getLogger(__name__)

resend = None  # pylint: disable=invalid-name

# avoiding import errors when not using resend
if settings.EMAIL_PROVIDER == "resend":
    # pylint: disable=import-outside-toplevel
    import resend

    resend.api_key = settings.RESEND_API_KEY


class ResendEmailService(EmailService):
    """Email service using Resend API"""

    def __init__(self):
        self._resend = resend

    async def send_magic_link(self, to_email: str, magic_link: str) -> bool:
        """Send magic link email via Resend"""
        try:
            self._resend.Emails.send(
                {
                    "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
                    "to": [to_email],
                    "subject": "Sign in to OWASP FinBot CTF",
                    "html": f"""
                    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #07070d; padding: 40px 32px; border-radius: 16px;">
                        <div style="text-align: center; margin-bottom: 32px;">
                            <a href="{settings.PLATFORM_URL}" style="text-decoration: none;">
                                <span style="color: #f1f5f9; font-weight: 800; font-size: 20px; letter-spacing: -0.5px;">OWASP FINBOT</span>
                                <span style="color: #00d4ff; font-size: 11px; font-family: monospace; margin-left: 6px;">CTF</span>
                            </a>
                        </div>
                        <div style="background: linear-gradient(135deg, rgba(18,18,32,0.9), rgba(14,14,26,0.95)); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; padding: 32px;">
                            <h2 style="color: #f1f5f9; font-size: 22px; font-weight: 700; margin: 0 0 12px 0;">Sign in to your account</h2>
                            <p style="color: #94a3b8; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">Click the button below to sign in. This link expires in {settings.MAGIC_LINK_EXPIRY_MINUTES} minutes.</p>
                            <p style="margin: 0 0 24px 0;">
                                <a href="{magic_link}" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #00d4ff, #7c3aed); color: #07070d; text-decoration: none; border-radius: 10px; font-weight: 700; font-size: 15px;">
                                    Sign In
                                </a>
                            </p>
                            <p style="color: #64748b; font-size: 12px; margin: 0;">
                                If you didn't request this email, you can safely ignore it.
                            </p>
                        </div>
                        <div style="text-align: center; margin-top: 24px;">
                            <p style="color: #64748b; font-size: 11px; margin: 0;">
                                Part of the <a href="https://genai.owasp.org/" style="color: #00d4ff; text-decoration: none;">OWASP GenAI Security Project</a>
                            </p>
                        </div>
                    </div>
                """,
                }
            )
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to send email via Resend: %s", e)
            return False
