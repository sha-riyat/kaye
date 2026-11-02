"""shop language: French, or English for the hackathon judges

Revision ID: 7c3d9e1f2a40
Revises: 5b1e7c2d9a10
Create Date: 2026-11-03 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c3d9e1f2a40"
down_revision: str | Sequence[str] | None = "5b1e7c2d9a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL means « not chosen yet »: a new shop is asked. Shops that exist already speak French.
    op.add_column("shop", sa.Column("language", sa.String(2), nullable=True))
    op.execute("UPDATE shop SET language = 'fr'")


def downgrade() -> None:
    op.drop_column("shop", "language")
