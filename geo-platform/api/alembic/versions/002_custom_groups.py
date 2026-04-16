"""Add custom groups and members

Revision ID: 002
Revises: 001
Create Date: 2026-04-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_custom flag to ms_groups
    op.add_column(
        "ms_groups",
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Custom group members — only populated for is_custom=true groups
    op.execute("""
    CREATE TABLE custom_group_members (
        group_id   UUID NOT NULL REFERENCES ms_groups(id) ON DELETE CASCADE,
        user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        added_by   UUID REFERENCES users(id),
        added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (group_id, user_id)
    );
    """)

    op.execute("CREATE INDEX idx_custom_group_members_user ON custom_group_members(user_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS custom_group_members;")
    op.drop_column("ms_groups", "is_custom")
