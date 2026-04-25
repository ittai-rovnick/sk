"""Per-partition stats indexes on features table for efficient aggregate queries

Revision ID: 002f
Revises: 001f
Create Date: 2026-04-25

NOTE: Run this against the features database only:
  alembic -x db=features upgrade features@head
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002f"
down_revision: Union[str, None] = "001f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        FOR i IN 0..31 LOOP
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS features_p%s_layer_del_idx
                 ON features_p%s (layer_id, deleted_at) WHERE deleted_at IS NULL', i, i);
        END LOOP;
    END $$;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        FOR i IN 0..31 LOOP
            EXECUTE format(
                'DROP INDEX IF EXISTS features_p%s_layer_del_idx', i);
        END LOOP;
    END $$;
    """)
