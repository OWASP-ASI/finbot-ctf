"""add labs_guardrail_configs table

Revision ID: a3f7c2d91e04
Revises: 061be7010c24
Create Date: 2026-04-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f7c2d91e04"
down_revision: Union[str, Sequence[str], None] = "061be7010c24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "labs_guardrail_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("webhook_url", sa.String(length=2048), nullable=False),
        sa.Column("signing_secret", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("hooks_json", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "namespace", "user_id", name="uq_labs_guardrail_namespace_user"
        ),
    )
    op.create_index(
        "idx_labs_guardrail_namespace",
        "labs_guardrail_configs",
        ["namespace"],
    )
    op.create_index(
        "idx_labs_guardrail_user",
        "labs_guardrail_configs",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_labs_guardrail_user", table_name="labs_guardrail_configs")
    op.drop_index("idx_labs_guardrail_namespace", table_name="labs_guardrail_configs")
    op.drop_table("labs_guardrail_configs")
