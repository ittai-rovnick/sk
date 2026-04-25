"""Saved filter expressions per layer

Revision ID: 010
Revises: 009
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE saved_expressions (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        layer_id    UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
        name        TEXT NOT NULL,
        description TEXT,
        expression  JSONB NOT NULL,
        created_by  UUID REFERENCES users(id),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (layer_id, name)
    );
    CREATE INDEX saved_expressions_layer_id_idx ON saved_expressions(layer_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS saved_expressions;")
