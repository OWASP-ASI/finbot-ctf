"""Analytics data models"""

from datetime import UTC, datetime

from sqlalchemy import Column, Date, Index, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy import DateTime as _DateTime

from finbot.core.data.database import Base

DateTime = _DateTime(timezone=True)


class PageView(Base):
    """Records each non-static HTTP request for analytics"""

    __tablename__ = "page_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    path = Column(String(500), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(SmallInteger, nullable=False)
    response_time_ms = Column(Integer, nullable=True)

    session_id = Column(String(64), nullable=True, index=True)
    session_type = Column(String(10), nullable=True)

    user_agent = Column(String(500), nullable=True)
    browser = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    device_type = Column(String(20), nullable=True)

    referer = Column(String(500), nullable=True)
    referer_domain = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_pageview_timestamp", "timestamp"),
        Index("ix_pageview_path_ts", "path", "timestamp"),
    )


class ProbeLog(Base):
    """Aggregated scan/bot traffic — one row per (date, path, source) combo.

    Keeps probe intelligence without bloating page_views.
    """

    __tablename__ = "probe_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    path = Column(String(500), nullable=False)
    source = Column(String(100), nullable=True)
    hits = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "path", "source", name="uq_probe_date_path_source"),
        Index("ix_probe_date", "date"),
    )
