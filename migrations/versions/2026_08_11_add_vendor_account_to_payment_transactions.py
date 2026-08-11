"""add vendor_account to payment_transactions

Revision ID: f1a4b9c73d2e
Revises: a3f7c2d91e04
Create Date: 2026-08-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a4b9c73d2e"
down_revision: Union[str, Sequence[str], None] = "a3f7c2d91e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_transactions",
        sa.Column("vendor_account", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_transactions", "vendor_account")
