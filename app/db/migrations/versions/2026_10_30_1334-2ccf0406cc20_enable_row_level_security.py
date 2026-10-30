"""enable row level security

Supabase exposes the public schema through its REST API with the public anon key. RLS with no
policies denies every row to the anon and authenticated roles; the app connects as the table
owner, which bypasses RLS.

Revision ID: 2ccf0406cc20
Revises: e42115efa470
Create Date: 2026-10-30 13:34:42.244172

"""

from collections.abc import Sequence

from alembic import op

revision: str = "2ccf0406cc20"
down_revision: str | Sequence[str] | None = "e42115efa470"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "shop",
    "app_user",
    "contact",
    "product",
    "unit_price",
    "media",
    "entry",
    "pending_action",
    "processed_message",
    "receipt",
    "model_call",
    "alembic_version",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
