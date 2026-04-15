"""Initial metadata schema

Revision ID: 001
Revises:
Create Date: 2026-04-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("meta",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # ------------------------------------------------------------------ users
    op.execute("""
    CREATE TABLE users (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ms_object_id     TEXT NOT NULL UNIQUE,
        email            TEXT NOT NULL,
        display_name     TEXT,
        is_superadmin    BOOLEAN NOT NULL DEFAULT FALSE,
        is_active        BOOLEAN NOT NULL DEFAULT TRUE,
        last_seen_at     TIMESTAMPTZ,
        deactivated_at   TIMESTAMPTZ,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX users_ms_object_id_idx ON users(ms_object_id);
    CREATE INDEX users_is_active_idx ON users(is_active);
    """)

    # --------------------------------------------------------------- ms_groups
    op.execute("""
    CREATE TABLE ms_groups (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ms_group_id      TEXT NOT NULL UNIQUE,
        display_name     TEXT,
        description      TEXT,
        synced_at        TIMESTAMPTZ,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX ms_groups_ms_group_id_idx ON ms_groups(ms_group_id);
    """)

    # ------------------------------------------------------------------- roles
    op.execute("""
    CREATE TABLE roles (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name             TEXT NOT NULL UNIQUE,
        description      TEXT,
        can_read         BOOLEAN NOT NULL DEFAULT FALSE,
        can_write        BOOLEAN NOT NULL DEFAULT FALSE,
        can_delete       BOOLEAN NOT NULL DEFAULT FALSE,
        can_export       BOOLEAN NOT NULL DEFAULT FALSE,
        can_manage_style BOOLEAN NOT NULL DEFAULT FALSE,
        can_manage_perms BOOLEAN NOT NULL DEFAULT FALSE,
        can_publish      BOOLEAN NOT NULL DEFAULT FALSE,
        is_system_role   BOOLEAN NOT NULL DEFAULT FALSE
    );

    INSERT INTO roles (name, description, is_system_role,
        can_read, can_write, can_delete, can_export,
        can_manage_style, can_manage_perms, can_publish)
    VALUES
        ('viewer',  'Read only',                             TRUE, TRUE,  FALSE, FALSE, FALSE, FALSE, FALSE, FALSE),
        ('editor',  'Read, write and export',                TRUE, TRUE,  TRUE,  FALSE, TRUE,  FALSE, FALSE, FALSE),
        ('manager', 'Full layer control except permissions', TRUE, TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  FALSE, TRUE),
        ('admin',   'Full control including permissions',    TRUE, TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  TRUE);
    """)

    # ----------------------------------------------------------- geo_databases
    op.execute("""
    CREATE TABLE geo_databases (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name         TEXT NOT NULL UNIQUE,
        description  TEXT,
        default_srid INT NOT NULL DEFAULT 4326,
        tags         TEXT[] NOT NULL DEFAULT '{}',
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX geo_databases_tags_idx ON geo_databases USING GIN(tags);
    """)

    # ----------------------------------------------------------- group_layers
    op.execute("""
    CREATE TABLE group_layers (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        database_id  UUID NOT NULL REFERENCES geo_databases(id) ON DELETE CASCADE,
        parent_id    UUID REFERENCES group_layers(id) ON DELETE CASCADE,
        name         TEXT NOT NULL,
        description  TEXT,
        tags         TEXT[] NOT NULL DEFAULT '{}',
        sort_order   INT NOT NULL DEFAULT 0,
        deleted_at   TIMESTAMPTZ,
        deleted_by   UUID REFERENCES users(id),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX group_layers_database_id_idx ON group_layers(database_id);
    CREATE INDEX group_layers_parent_id_idx ON group_layers(parent_id);
    CREATE INDEX group_layers_tags_idx ON group_layers USING GIN(tags);
    CREATE UNIQUE INDEX group_layers_unique_name_idx
        ON group_layers(database_id, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), name)
        WHERE deleted_at IS NULL;
    """)

    # --------------------------------------------------------------- layers
    op.execute("""
    CREATE TABLE layers (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        database_id    UUID NOT NULL REFERENCES geo_databases(id) ON DELETE CASCADE,
        group_layer_id UUID REFERENCES group_layers(id) ON DELETE SET NULL,
        name           TEXT NOT NULL,
        description    TEXT,
        geometry_type  TEXT NOT NULL,
        srid           INT NOT NULL DEFAULT 4326,
        tags           TEXT[] NOT NULL DEFAULT '{}',
        status         TEXT NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft','review','published')),
        health         TEXT NOT NULL DEFAULT 'ok'
                       CHECK (health IN ('ok','stale','error','syncing')),
        shard_id       INT NOT NULL DEFAULT 0,
        is_locked      BOOLEAN NOT NULL DEFAULT FALSE,
        locked_by      UUID REFERENCES users(id),
        locked_at      TIMESTAMPTZ,
        lock_reason    TEXT,
        bbox           GEOMETRY(Polygon, 4326),
        lyrx_s3_key    TEXT,
        sort_order     INT NOT NULL DEFAULT 0,
        deleted_at     TIMESTAMPTZ,
        deleted_by     UUID REFERENCES users(id),
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX layers_database_id_idx  ON layers(database_id);
    CREATE INDEX layers_group_layer_id_idx ON layers(group_layer_id);
    CREATE INDEX layers_shard_id_idx     ON layers(shard_id);
    CREATE INDEX layers_is_locked_idx    ON layers(is_locked) WHERE is_locked = TRUE;
    CREATE INDEX layers_status_idx       ON layers(status);
    CREATE INDEX layers_tags_idx         ON layers USING GIN(tags);
    CREATE INDEX layers_bbox_idx         ON layers USING GIST(bbox) WHERE bbox IS NOT NULL;
    CREATE INDEX layers_deleted_at_idx   ON layers(deleted_at) WHERE deleted_at IS NULL;
    """)

    # ---------------------------------------------------------- layer_owners
    op.execute("""
    CREATE TABLE layer_owners (
        layer_id     UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
        user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
        assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        assigned_by  UUID REFERENCES users(id),
        PRIMARY KEY (layer_id, user_id)
    );
    CREATE UNIQUE INDEX layer_owners_primary_idx
        ON layer_owners(layer_id)
        WHERE is_primary = TRUE;
    """)

    # ------------------------------------------------ ownership transfer trigger
    op.execute("""
    CREATE OR REPLACE FUNCTION transfer_ownership_on_deactivate()
    RETURNS TRIGGER AS $$
    BEGIN
        UPDATE layer_owners lo
        SET user_id = (
            SELECT gl.id FROM users gl
            WHERE gl.id IN (
                SELECT p.ms_group_id::uuid FROM permissions p
                WHERE p.layer_id = lo.layer_id
                LIMIT 1
            )
            LIMIT 1
        ),
        assigned_at = now()
        WHERE lo.user_id = NEW.id
          AND lo.is_primary = TRUE
          AND NEW.is_active = FALSE;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_transfer_ownership
    AFTER UPDATE OF is_active ON users
    FOR EACH ROW
    WHEN (OLD.is_active = TRUE AND NEW.is_active = FALSE)
    EXECUTE FUNCTION transfer_ownership_on_deactivate();
    """)

    # ---------------------------------------------------------- layer_schema
    op.execute("""
    CREATE TABLE layer_schema (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        layer_id       UUID NOT NULL UNIQUE REFERENCES layers(id) ON DELETE CASCADE,
        json_schema    JSONB NOT NULL DEFAULT '{}',
        schema_version INT NOT NULL DEFAULT 1,
        updated_by     UUID REFERENCES users(id),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # ---------------------------------------------------------- layer_styles
    op.execute("""
    CREATE TABLE layer_styles (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        layer_id     UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
        name         TEXT NOT NULL DEFAULT 'default',
        renderer     JSONB NOT NULL DEFAULT '{}',
        label_config JSONB,
        popup_config JSONB,
        is_default   BOOLEAN NOT NULL DEFAULT FALSE,
        lyrx_s3_key  TEXT,
        created_by   UUID REFERENCES users(id),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (layer_id, name)
    );
    CREATE INDEX layer_styles_layer_id_idx ON layer_styles(layer_id);
    """)

    # ---------------------------------------------------------- permissions
    op.execute("""
    CREATE TABLE permissions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ms_user_id      TEXT,
        ms_group_id     TEXT,
        database_id     UUID REFERENCES geo_databases(id) ON DELETE CASCADE,
        group_layer_id  UUID REFERENCES group_layers(id) ON DELETE CASCADE,
        layer_id        UUID REFERENCES layers(id) ON DELETE CASCADE,
        role_id         UUID NOT NULL REFERENCES roles(id),
        allow           BOOLEAN NOT NULL DEFAULT TRUE,
        granted_by      UUID REFERENCES users(id),
        granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT one_principal CHECK (
            (ms_user_id IS NOT NULL)::INT +
            (ms_group_id IS NOT NULL)::INT = 1
        ),
        CONSTRAINT one_resource CHECK (
            (database_id IS NOT NULL)::INT +
            (group_layer_id IS NOT NULL)::INT +
            (layer_id IS NOT NULL)::INT = 1
        )
    );
    CREATE INDEX perms_ms_user_id_idx       ON permissions(ms_user_id);
    CREATE INDEX perms_ms_group_id_idx      ON permissions(ms_group_id);
    CREATE INDEX perms_database_id_idx      ON permissions(database_id);
    CREATE INDEX perms_group_layer_id_idx   ON permissions(group_layer_id);
    CREATE INDEX perms_layer_id_idx         ON permissions(layer_id);
    """)

    # ------------------------------------------------- can_user_do() function
    op.execute("""
    CREATE OR REPLACE FUNCTION can_user_do(
        p_ms_object_id TEXT,
        p_ms_group_ids TEXT[],
        p_layer_id     UUID,
        p_operation    TEXT
    ) RETURNS BOOLEAN AS $$
    DECLARE
        v_has_explicit_deny BOOLEAN;
        v_has_permission    BOOLEAN;
        v_layer             RECORD;
    BEGIN
        SELECT database_id, group_layer_id INTO v_layer FROM layers WHERE id = p_layer_id;

        SELECT EXISTS (
            SELECT 1 FROM permissions p
            JOIN roles r ON p.role_id = r.id
            WHERE p.allow = FALSE
              AND (
                (p.ms_user_id = p_ms_object_id) OR
                (p.ms_group_id = ANY(p_ms_group_ids))
              )
              AND (
                p.layer_id = p_layer_id OR
                p.group_layer_id = v_layer.group_layer_id OR
                p.database_id = v_layer.database_id
              )
        ) INTO v_has_explicit_deny;

        IF v_has_explicit_deny THEN RETURN FALSE; END IF;

        SELECT EXISTS (
            SELECT 1 FROM permissions p
            JOIN roles r ON p.role_id = r.id
            WHERE p.allow = TRUE
              AND (
                (p.ms_user_id = p_ms_object_id) OR
                (p.ms_group_id = ANY(p_ms_group_ids))
              )
              AND (
                p.layer_id = p_layer_id OR
                p.group_layer_id = v_layer.group_layer_id OR
                p.database_id = v_layer.database_id
              )
              AND CASE p_operation
                WHEN 'read'          THEN r.can_read
                WHEN 'write'         THEN r.can_write
                WHEN 'delete'        THEN r.can_delete
                WHEN 'export'        THEN r.can_export
                WHEN 'manage_style'  THEN r.can_manage_style
                WHEN 'manage_perms'  THEN r.can_manage_perms
                WHEN 'publish'       THEN r.can_publish
                ELSE FALSE
              END = TRUE
        ) INTO v_has_permission;

        RETURN v_has_permission;
    END;
    $$ LANGUAGE plpgsql STABLE;
    """)

    # --------------------------------------------------------- group_quotas
    op.execute("""
    CREATE TABLE group_quotas (
        ms_group_id            TEXT PRIMARY KEY,
        max_layers             INT NOT NULL DEFAULT 100,
        max_features_per_layer BIGINT NOT NULL DEFAULT 1000000,
        max_export_mb          INT NOT NULL DEFAULT 500,
        updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # ------------------------------------------------------ raster_catalog
    op.execute("""
    CREATE TABLE raster_catalog (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        database_id    UUID REFERENCES geo_databases(id) ON DELETE CASCADE,
        group_layer_id UUID REFERENCES group_layers(id) ON DELETE SET NULL,
        name           TEXT NOT NULL,
        s3_key         TEXT NOT NULL,
        format         TEXT NOT NULL DEFAULT 'COG',
        srid           INT NOT NULL DEFAULT 4326,
        resolution_m   FLOAT,
        band_count     INT,
        bbox           GEOMETRY(Polygon, 4326),
        tags           TEXT[] NOT NULL DEFAULT '{}',
        status         TEXT NOT NULL DEFAULT 'ready',
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX raster_catalog_bbox_idx ON raster_catalog USING GIST(bbox);
    CREATE INDEX raster_catalog_tags_idx ON raster_catalog USING GIN(tags);
    """)

    # ---------------------------------------------------------- audit_log
    op.execute("""
    CREATE TABLE audit_log (
        id            BIGSERIAL PRIMARY KEY,
        user_id       UUID REFERENCES users(id),
        ms_object_id  TEXT,
        action        TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        resource_id   TEXT NOT NULL,
        old_value     JSONB,
        new_value     JSONB,
        ip_address    INET,
        error_message TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX audit_log_user_id_idx    ON audit_log(user_id);
    CREATE INDEX audit_log_resource_idx   ON audit_log(resource_type, resource_id);
    CREATE INDEX audit_log_created_at_idx ON audit_log(created_at DESC);
    CREATE INDEX audit_log_action_idx     ON audit_log(action);
    """)

    # -------------------------------------------------------- layer_events
    op.execute("""
    CREATE TABLE layer_events (
        id         BIGSERIAL PRIMARY KEY,
        layer_id   UUID REFERENCES layers(id) ON DELETE CASCADE,
        user_id    UUID REFERENCES users(id),
        event_type TEXT NOT NULL,
        payload    JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX layer_events_layer_id_idx   ON layer_events(layer_id);
    CREATE INDEX layer_events_event_type_idx ON layer_events(event_type);
    CREATE INDEX layer_events_created_at_idx ON layer_events(created_at DESC);
    """)

    # ------------------------------------------------------ sync_snapshots
    op.execute("""
    CREATE TABLE sync_snapshots (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        layer_id        UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
        user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        device_id       TEXT NOT NULL,
        snapshotted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at      TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days'),
        feature_count   INT NOT NULL DEFAULT 0
    );
    CREATE INDEX sync_snapshots_layer_user_idx ON sync_snapshots(layer_id, user_id);
    CREATE INDEX sync_snapshots_expires_at_idx ON sync_snapshots(expires_at);
    """)

    # ------------------------------------------------------- sync_conflicts
    op.execute("""
    CREATE TABLE sync_conflicts (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        layer_id       UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
        feature_id     BIGINT NOT NULL,
        user_id        UUID NOT NULL REFERENCES users(id),
        device_id      TEXT NOT NULL,
        client_payload JSONB NOT NULL,
        server_version INT NOT NULL,
        client_version INT NOT NULL,
        resolution     TEXT CHECK (resolution IN ('server_wins','client_wins','manual','pending'))
                       DEFAULT 'pending',
        resolved_by    UUID REFERENCES users(id),
        resolved_at    TIMESTAMPTZ,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX sync_conflicts_layer_id_idx   ON sync_conflicts(layer_id);
    CREATE INDEX sync_conflicts_user_id_idx    ON sync_conflicts(user_id);
    CREATE INDEX sync_conflicts_resolution_idx ON sync_conflicts(resolution) WHERE resolution = 'pending';
    """)

    # ------------------------------------------------------- failed_syncs
    op.execute("""
    CREATE TABLE failed_syncs (
        id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id       UUID REFERENCES users(id),
        layer_id      UUID REFERENCES layers(id),
        device_id     TEXT,
        payload       JSONB NOT NULL,
        error_code    TEXT NOT NULL,
        error_message TEXT NOT NULL,
        retried_at    TIMESTAMPTZ,
        resolved      BOOLEAN NOT NULL DEFAULT FALSE,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX failed_syncs_user_id_idx  ON failed_syncs(user_id);
    CREATE INDEX failed_syncs_resolved_idx ON failed_syncs(resolved) WHERE resolved = FALSE;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS failed_syncs CASCADE;")
    op.execute("DROP TABLE IF EXISTS sync_conflicts CASCADE;")
    op.execute("DROP TABLE IF EXISTS sync_snapshots CASCADE;")
    op.execute("DROP TABLE IF EXISTS layer_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS raster_catalog CASCADE;")
    op.execute("DROP TABLE IF EXISTS group_quotas CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS can_user_do CASCADE;")
    op.execute("DROP TABLE IF EXISTS permissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS layer_styles CASCADE;")
    op.execute("DROP TABLE IF EXISTS layer_schema CASCADE;")
    op.execute("DROP TRIGGER IF EXISTS trg_transfer_ownership ON users;")
    op.execute("DROP FUNCTION IF EXISTS transfer_ownership_on_deactivate CASCADE;")
    op.execute("DROP TABLE IF EXISTS layer_owners CASCADE;")
    op.execute("DROP TABLE IF EXISTS layers CASCADE;")
    op.execute("DROP TABLE IF EXISTS group_layers CASCADE;")
    op.execute("DROP TABLE IF EXISTS geo_databases CASCADE;")
    op.execute("DROP TABLE IF EXISTS roles CASCADE;")
    op.execute("DROP TABLE IF EXISTS ms_groups CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
