"""Analytics data retention — cleanup old pageview records"""

import logging
from datetime import UTC, datetime, timedelta

from finbot.config import settings
from finbot.core.data.database import SessionLocal

from .models import PageView

logger = logging.getLogger(__name__)


def cleanup_old_pageviews() -> int:
    """Delete pageview records older than ANALYTICS_RETENTION_DAYS.
    Returns the number of records deleted.
    """
    retention_days = settings.ANALYTICS_RETENTION_DAYS
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    db = SessionLocal()
    try:
        count = db.query(PageView).filter(PageView.timestamp < cutoff).delete()
        db.commit()
        if count > 0:
            logger.info(
                "Analytics retention: deleted %d pageviews older than %d days",
                count,
                retention_days,
            )
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
