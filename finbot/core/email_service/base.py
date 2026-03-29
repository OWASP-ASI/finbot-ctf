"""Abstract base class for email services"""

from abc import ABC, abstractmethod


class EmailService(ABC):
    """Abstract email service interface"""

    @abstractmethod
    async def send_magic_link(self, to_email: str, magic_link: str) -> bool:
        """Send a magic link email to the specified address.

        Args:
            to_email: Recipient email address
            magic_link: The full magic link URL

        Returns:
            True if email was sent successfully, False otherwise
        """
        raise NotImplementedError("send_magic_link method not implemented")
