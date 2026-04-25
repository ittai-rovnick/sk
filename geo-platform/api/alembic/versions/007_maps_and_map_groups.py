"""Maps, map groups, and map-layer join table

Revision ID: 007
Revises: 006
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------- maps
    op.execute("""
    CREATE TABLE maps (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name                TEXT NOT NULL,
        description         TEXT,
        database_id         UUID NOT NULL REFERENCES geo_databases(id) ON DELETE CASCADE,
        extent              GEOMETRY(Polygon, 4326),
        created_by          UUID REFERENCES users(id),
        updated_by          UUID REFERENCES users(id),
        deleted_at          TIMESTAMPTZ,
        deleted_by          UUID REFERENCES users(id),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        content_version     INT NOT NULL DEFAULT 0,
        content_updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        content_updated_by  UUID REFERENCES users(id)
    );
    CREATE INDEX maps_database_id_idx ON maps(database_id);
    CREATE INDEX maps_deleted_at_idx  ON maps(deleted_at) WHERE deleted_at IS NULL;
    CREATE INDEX maps_extent_idx      ON maps USING GIST(extent) WHERE extent IS NOT NULL;
    """)

    # -------------------------------------------------------------- map_groups
    op.execute("""
    CREATE TABLE map_groups (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        map_id           UUID NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
        parent_id        UUID REFERENCES map_groups(id) ON DELETE CASCADE,
        embedded_map_id  UUID REFERENCES maps(id) ON DELETE CASCADE,
        name             TEXT NOT NULL,
        sort_order       INT NOT NULL DEFAULT 0,
        is_expanded      BOOLEAN NOT NULL DEFAULT TRUE,
        created_by       UUID REFERENCES users(id),
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_no_self_parent CHECK (parent_id IS NULL OR parent_id <> id),
        CONSTRAINT chk_no_self_embed  CHECK (embedded_map_id IS NULL OR embedded_map_id <> map_id)
    );
    CREATE INDEX map_groups_map_id_idx    ON map_groups(map_id);
    CREATE INDEX map_groups_parent_id_idx ON map_groups(parent_id);
    CREATE UNIQUE INDEX map_groups_unique_name_idx
        ON map_groups(map_id, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), name);
    """)

    # -------------------------------------------------------------- map_layers
    op.execute("""
    CREATE TABLE map_layers (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        map_id            UUID NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
        layer_id          UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
        group_id          UUID REFERENCES map_groups(id) ON DELETE SET NULL,
        sort_order        INT NOT NULL DEFAULT 0,
        is_visible        BOOLEAN NOT NULL DEFAULT TRUE,
        filter_expression JSONB,
        added_by          UUID REFERENCES users(id),
        added_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (map_id, layer_id)
    );
    CREATE INDEX map_layers_map_id_idx   ON map_layers(map_id);
    CREATE INDEX map_layers_layer_id_idx ON map_layers(layer_id);
    CREATE INDEX map_layers_group_id_idx ON map_layers(group_id);
    """)

    # ---------------------------------------- get_map_layer_tree() SQL function
    op.execute("""
    CREATE OR REPLACE FUNCTION get_map_layer_tree(p_map_id UUID)
    RETURNS TABLE (
        row_type       TEXT,
        row_id         UUID,
        parent_id      UUID,
        name           TEXT,
        sort_order     INT,
        is_expanded    BOOLEAN,
        embedded_map_id UUID,
        layer_id       UUID,
        is_visible     BOOLEAN,
        srid           INT,
        geometry_types TEXT[],
        bbox_arr       FLOAT8[]
    ) AS $$
    BEGIN
        -- Groups
        RETURN QUERY
        SELECT 'group'::TEXT, mg.id, mg.parent_id, mg.name, mg.sort_order, mg.is_expanded,
               mg.embedded_map_id,
               NULL::UUID, NULL::BOOLEAN, NULL::INT, NULL::TEXT[], NULL::FLOAT8[]
        FROM map_groups mg WHERE mg.map_id = p_map_id;
        -- Layers
        RETURN QUERY
        SELECT 'layer'::TEXT, ml.id, ml.group_id, l.name, ml.sort_order, NULL::BOOLEAN,
               NULL::UUID,
               l.id, ml.is_visible, l.srid, l.geometry_types,
               CASE WHEN l.bbox IS NOT NULL THEN
                   ARRAY[ST_XMin(l.bbox)::FLOAT8, ST_YMin(l.bbox)::FLOAT8,
                         ST_XMax(l.bbox)::FLOAT8, ST_YMax(l.bbox)::FLOAT8]
               ELSE NULL END
        FROM map_layers ml
        JOIN layers l ON l.id = ml.layer_id
        WHERE ml.map_id = p_map_id AND l.deleted_at IS NULL;
    END;
    $$ LANGUAGE plpgsql STABLE;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_map_layer_tree(UUID);")
    op.execute("DROP TABLE IF EXISTS map_layers;")
    op.execute("DROP TABLE IF EXISTS map_groups;")
    op.execute("DROP TABLE IF EXISTS maps;")
