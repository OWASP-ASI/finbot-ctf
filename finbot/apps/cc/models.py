"""Command Center data models"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy import DateTime as _DateTime

from finbot.core.data.database import Base

DateTime = _DateTime(timezone=True)


class PlatformAdmin(Base):
    """Maintainers authorized to access the Command Center"""

    __tablename__ = "platform_admins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    added_by = Column(String(255), nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<PlatformAdmin email={self.email} active={self.is_active}>"
