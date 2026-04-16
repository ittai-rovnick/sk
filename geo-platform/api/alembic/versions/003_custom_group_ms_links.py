"""Add custom_group_ms_links for attaching external group sources

Revision ID: 003
Revises: 002
Create Date: 2026-04-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Links a custom group to one or more external group IDs (e.g. Microsoft Entra).
    # All members of a linked external group are treated as members of the custom group.
    op.execute("""
    CREATE TABLE custom_group_ms_links (
        custom_group_id UUID NOT NULL REFERENCES ms_groups(id) ON DELETE CASCADE,
        ms_group_id     TEXT NOT NULL,
        ms_display_name TEXT,
        linked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (custom_group_id, ms_group_id)
    );
    """)
    op.execute("CREATE INDEX idx_cgms_ms_group ON custom_group_ms_links(ms_group_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS custom_group_ms_links;")
