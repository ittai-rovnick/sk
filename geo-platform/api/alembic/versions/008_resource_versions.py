"""Resource version history — full snapshots, race-condition-free counter

Revision ID: 008
Revises: 007
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE resource_type AS ENUM ('layer', 'map');")

    op.execute("""
    CREATE TABLE resource_versions (
        id             BIGSERIAL PRIMARY KEY,
        resource_type  resource_type NOT NULL,
        resource_id    UUID NOT NULL,
        version        INT NOT NULL,
        snapshot       JSONB NOT NULL,
        changed_fields TEXT[] NOT NULL DEFAULT '{}',
        message        TEXT,
        changed_by     UUID REFERENCES users(id),
        changed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (resource_type, resource_id, version)
    );
    CREATE INDEX resource_versions_resource_idx
        ON resource_versions(resource_type, resource_id, version DESC);
    CREATE INDEX resource_versions_changed_at_idx
        ON resource_versions(changed_at DESC);
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION next_resource_version(
        p_resource_type resource_type,
        p_resource_id   UUID
    ) RETURNS INT AS $$
    DECLARE v_next INT;
    BEGIN
        SELECT COALESCE(MAX(version), 0) + 1 INTO v_next
        FROM resource_versions
        WHERE resource_type = p_resource_type AND resource_id = p_resource_id
        FOR UPDATE;
        RETURN v_next;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS next_resource_version(resource_type, UUID);")
    op.execute("DROP TABLE IF EXISTS resource_versions;")
    op.execute("DROP TYPE IF EXISTS resource_type;")
