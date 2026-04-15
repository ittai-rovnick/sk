"""Initial features schema — partitioned features table

Revision ID: 001f
Revises:
Create Date: 2026-04-16

NOTE: Run this against the features database only:
  alembic -x db=features upgrade head
"""
from typing import Sequence, Union
from alembic import op

revision: str = "001f"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("features",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # -------------------------------------------------- partitioned features table
    op.execute("""
    CREATE TABLE features (
        id         BIGSERIAL,
        layer_id   UUID NOT NULL,
        geom       GEOMETRY NOT NULL,
        properties JSONB NOT NULL DEFAULT '{}',
        version    INT NOT NULL DEFAULT 1,
        created_by TEXT,
        updated_by TEXT,
        deleted_at TIMESTAMPTZ,
        deleted_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (id, layer_id),
        CONSTRAINT features_geom_valid CHECK (ST_IsValid(geom))
    ) PARTITION BY HASH (layer_id);
    """)

    # ------------------------------------------- 32 hash partitions
    op.execute("""
    DO $$
    BEGIN
        FOR i IN 0..31 LOOP
            EXECUTE format(
                'CREATE TABLE features_p%s PARTITION OF features
                 FOR VALUES WITH (MODULUS 32, REMAINDER %s)',
                i, i
            );
        END LOOP;
    END $$;
    """)

    # ------------------------------------------- indexes on each partition
    op.execute("""
    DO $$
    BEGIN
        FOR i IN 0..31 LOOP
            EXECUTE format('CREATE INDEX features_p%s_geom_idx       ON features_p%s USING GIST(geom)', i, i);
            EXECUTE format('CREATE INDEX features_p%s_layer_id_idx   ON features_p%s(layer_id)', i, i);
            EXECUTE format('CREATE INDEX features_p%s_props_idx      ON features_p%s USING GIN(properties)', i, i);
            EXECUTE format('CREATE INDEX features_p%s_updated_at_idx ON features_p%s(updated_at DESC)', i, i);
            EXECUTE format(
                'CREATE INDEX features_p%s_deleted_at_idx ON features_p%s(deleted_at) WHERE deleted_at IS NULL',
                i, i
            );
        END LOOP;
    END $$;
    """)

    # ---------------------------------------- auto-repair invalid geometry trigger
    op.execute("""
    CREATE OR REPLACE FUNCTION auto_repair_geometry()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NOT ST_IsValid(NEW.geom) THEN
            NEW.geom := ST_MakeValid(NEW.geom);
            IF NOT ST_IsValid(NEW.geom) THEN
                RAISE EXCEPTION 'Geometry cannot be repaired: %', ST_IsValidReason(NEW.geom);
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_auto_repair_geometry
    BEFORE INSERT ON features
    FOR EACH ROW EXECUTE FUNCTION auto_repair_geometry();
    """)

    # ----------------------------------------- auto-update updated_at trigger
    op.execute("""
    CREATE OR REPLACE FUNCTION update_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_update_features_updated_at
    BEFORE UPDATE ON features
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_update_features_updated_at ON features;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at CASCADE;")
    op.execute("DROP TRIGGER IF EXISTS trg_auto_repair_geometry ON features;")
    op.execute("DROP FUNCTION IF EXISTS auto_repair_geometry CASCADE;")
    op.execute("DROP TABLE IF EXISTS features CASCADE;")
