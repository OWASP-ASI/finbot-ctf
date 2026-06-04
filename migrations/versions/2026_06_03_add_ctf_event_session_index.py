"""add composite index on ctf_events for SequenceDetector session-window queries

Revision ID: b1e4f9a2c83d
Revises: a3f7c2d91e04
Create Date: 2026-06-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1e4f9a2c83d"
down_revision: Union[str, Sequence[str], None] = "a3f7c2d91e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for SequenceDetector session-window queries:
    # WHERE namespace = ? AND session_id = ? ORDER BY timestamp ASC
    # namespace leads so rows are partitioned by tenant first, then by
    # session within that tenant — matches the actual filter shape and
    # keeps selectivity high in multi-tenant deployments.
    op.create_index(
        "idx_ctf_event_session_ts_type",
        "ctf_events",
        ["namespace", "session_id", "timestamp", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_ctf_event_session_ts_type", table_name="ctf_events")
