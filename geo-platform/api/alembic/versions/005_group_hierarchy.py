"""Add parent_group_id to ms_groups for group hierarchy

Revision ID: 005
Revises: 004
Create Date: 2026-04-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Self-referencing FK — null means root group.
    # ON DELETE SET NULL: removing a parent promotes its children to roots (safe default).
    op.execute("""
    ALTER TABLE ms_groups
        ADD COLUMN parent_group_id UUID
        REFERENCES ms_groups(id) ON DELETE SET NULL;
    """)
    op.execute("""
    ALTER TABLE ms_groups
        ADD CONSTRAINT chk_ms_groups_no_self_parent
        CHECK (parent_group_id IS NULL OR parent_group_id <> id);
    """)
    op.execute("CREATE INDEX idx_ms_groups_parent ON ms_groups(parent_group_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ms_groups_parent;")
    op.execute("ALTER TABLE ms_groups DROP CONSTRAINT IF EXISTS chk_ms_groups_no_self_parent;")
    op.execute("ALTER TABLE ms_groups DROP COLUMN IF EXISTS parent_group_id;")
