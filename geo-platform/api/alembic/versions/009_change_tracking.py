"""Change tracking columns on layers — separate feature-edit signal from metadata-edit signal

Revision ID: 009
Revises: 008
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE layers
        ADD COLUMN features_updated_at TIMESTAMPTZ,
        ADD COLUMN features_updated_by UUID REFERENCES users(id),
        ADD COLUMN updated_by          UUID REFERENCES users(id);
    """)
    op.execute("""
    CREATE INDEX layers_features_updated_at_idx
        ON layers(features_updated_at DESC NULLS LAST)
        WHERE deleted_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS layers_features_updated_at_idx;")
    op.execute("""
    ALTER TABLE layers
        DROP COLUMN IF EXISTS features_updated_at,
        DROP COLUMN IF EXISTS features_updated_by,
        DROP COLUMN IF EXISTS updated_by;
    """)
