"""message log: the recent conversation, for context

Revision ID: 5b1e7c2d9a10
Revises: 2ccf0406cc20
Create Date: 2026-10-31 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b1e7c2d9a10"
down_revision: str | Sequence[str] | None = "2ccf0406cc20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shop.id"), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_message_log_user_created", "message_log", ["user_id", "created_at"])
    op.execute("ALTER TABLE message_log ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("message_log")
