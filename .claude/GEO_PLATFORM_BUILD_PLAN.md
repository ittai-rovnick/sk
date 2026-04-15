# GEO PLATFORM — COMPLETE BUILD PLAN FOR CLAUDE
> Read this entire file before writing a single line of code.
> Follow every section in order. Never skip ahead.
> When in doubt, ask the user before proceeding.

---

## WHAT YOU ARE BUILDING

A full-stack geographic data management platform called **Geo Platform**. It consists of:

1. **Two PostgreSQL + PostGIS databases** — one for metadata, one for spatial features
2. **FastAPI REST API** — the single access point for all clients
3. **React + TypeScript web app** — management interface for admins, managers, and group leads

### Client applications that will consume this system
- **ArcGIS Pro** — Esri desktop GIS tool. Connects directly to PostgreSQL and via API.
- **Esri Portal** — Web GIS viewer. Connects via OGC Features API.
- **Argo** — A .NET application using ArcGIS Maps SDK. Works online AND offline.

---

## STEP 0 — CHECK PREREQUISITES BEFORE ANYTHING ELSE

Run every check below. If any command fails or returns a version below the minimum,
tell the user exactly what to install, give them the download link, and STOP.
Do not proceed until the user confirms everything is installed.

```bash
git --version        # need 2.x+         → https://git-scm.com/download/win
python --version     # need 3.11+        → https://www.python.org/downloads/
node --version       # need 20+          → https://nodejs.org/ (use LTS)
docker --version     # need 24+          → https://www.docker.com/products/docker-desktop/
docker compose version  # need 2.x+
code --version       # VS Code           → https://code.visualstudio.com/
```

### Required VS Code extensions
Tell the user to install all of these from the VS Code Extensions panel (Ctrl+Shift+X):
- Python
- Pylance
- Ruff
- Python Debugger
- ESLint
- Prettier - Code formatter
- Docker
- PostgreSQL (by Chris Kolkman)
- Thunder Client

### Windows-specific notes
- Docker Desktop requires WSL2. If not installed, Docker will prompt for it.
- Use Windows Terminal for all commands (winget install Microsoft.WindowsTerminal).
- Always run terminals as normal user, not Administrator.
- Python: during install, CHECK "Add Python to PATH".

---

## STEP 1 — CREATE THE PROJECT STRUCTURE

Create this EXACT folder structure. Do not deviate from it.
Every file listed here must be created — even if empty at first.

```
geo-platform/
├── docker-compose.yml
├── .env                          # secrets — NEVER commit this
├── .env.example                  # template — commit this
├── .gitignore
├── Makefile
│
├── api/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/             # migration files go here
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── dependencies.py
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── microsoft.py
│       │   ├── permissions.py
│       │   └── models.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── session.py
│       │   └── base.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── users.py
│       │   ├── groups.py
│       │   ├── databases.py
│       │   ├── layers.py
│       │   ├── features.py
│       │   ├── permissions.py
│       │   ├── symbology.py
│       │   ├── rasters.py
│       │   └── audit.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── users.py
│       │   ├── layers.py
│       │   ├── features.py
│       │   ├── permissions.py
│       │   ├── symbology.py
│       │   └── sync.py
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── databases.py
│       │   ├── group_layers.py
│       │   ├── layers.py
│       │   ├── features.py
│       │   ├── permissions.py
│       │   ├── symbology.py
│       │   ├── users.py
│       │   ├── groups.py
│       │   ├── rasters.py
│       │   ├── sync.py
│       │   └── health.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── layer_service.py
│       │   ├── feature_service.py
│       │   ├── permission_service.py
│       │   ├── symbology_service.py
│       │   ├── storage_service.py
│       │   ├── sync_service.py
│       │   └── audit_service.py
│       └── tests/
│           ├── conftest.py
│           ├── test_auth.py
│           ├── test_layers.py
│           ├── test_features.py
│           └── test_permissions.py
│
└── web/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── vite-env.d.ts
        ├── auth/
        │   ├── msalConfig.ts
        │   ├── AuthProvider.tsx
        │   └── useAuth.ts
        ├── api/
        │   ├── client.ts
        │   ├── databases.ts
        │   ├── layers.ts
        │   ├── features.ts
        │   ├── permissions.ts
        │   ├── users.ts
        │   └── groups.ts
        ├── pages/
        │   ├── DatabasesPage.tsx
        │   ├── LayersPage.tsx
        │   ├── LayerDetailPage.tsx
        │   ├── PermissionsPage.tsx
        │   ├── UsersPage.tsx
        │   ├── GroupsPage.tsx
        │   ├── AuditLogPage.tsx
        │   └── SyncConflictsPage.tsx
        ├── components/
        │   ├── layout/
        │   │   ├── AppLayout.tsx
        │   │   ├── Sidebar.tsx
        │   │   └── TopBar.tsx
        │   ├── layers/
        │   │   ├── LayerTree.tsx
        │   │   ├── LayerForm.tsx
        │   │   └── LockButton.tsx
        │   ├── permissions/
        │   │   ├── PermissionMatrix.tsx
        │   │   └── PermissionForm.tsx
        │   └── shared/
        │       ├── ErrorBoundary.tsx
        │       └── LoadingSpinner.tsx
        └── types/
            └── index.ts
```

---

## STEP 2 — CODING PRINCIPLES (NON-NEGOTIABLE)

Follow these throughout the entire project. Never violate them.

1. **Separation of concerns**
   - Routers handle HTTP only: parse request, call service, return response.
   - Services handle all business logic.
   - Models define database structure.
   - Never mix these layers.

2. **One file per domain**
   - Never put users and layers in the same file.
   - If a file grows beyond ~200 lines, split it.

3. **Always async**
   - All database operations use async/await.
   - All HTTP calls use async/await.
   - No synchronous blocking code anywhere.

4. **Secrets in .env only**
   - Never hardcode any secret, URL, or credential.
   - All config comes from config.py which reads from .env.
   - If a value might change between environments, it goes in .env.

5. **Always validate input**
   - Every endpoint uses a Pydantic schema for the request body.
   - Every endpoint declares a Pydantic response_model.
   - Never trust raw input.

6. **Always check permissions**
   - Every endpoint that touches a layer, group_layer, or database
     calls `permission_service.can_user_do()` BEFORE doing anything else.
   - If permission denied → raise HTTP 403 immediately.

7. **Always check layer lock**
   - Every write endpoint (create/update/delete features, update style)
     checks `layer.is_locked` before proceeding.
   - If locked → raise HTTP 423 (Locked) with the lock_reason.

8. **Always write to audit_log**
   - Every write operation calls `audit_service.log()` AFTER the operation succeeds.
   - Audit logging is async and non-blocking — never let it slow down responses.
   - Log: user_id, action, resource_type, resource_id, old_value, new_value, ip_address.

9. **Use dependency injection**
   - Never import db session or current user directly inside a router or service.
   - Always use FastAPI Depends() for: db session, current user, feature db session.

10. **Soft deletes everywhere**
    - Never hard-DELETE features, layers, or group_layers from the database.
    - Set deleted_at = now() and deleted_by = user_id.
    - Every query filters WHERE deleted_at IS NULL.
    - Hard delete is superadmin-only and requires explicit confirmation.

11. **Optimistic locking on features**
    - Every feature has a `version INT` column.
    - Every UPDATE must include WHERE version = $client_version.
    - If 0 rows updated → raise HTTP 409 Conflict → write to sync_conflicts table.

12. **Geometry validation**
    - Never insert invalid geometry.
    - Run ST_IsValid() check on every insert.
    - Auto-repair with ST_MakeValid() via trigger.
    - If geometry cannot be repaired → reject with HTTP 422.

---

## STEP 3 — TECHNOLOGY STACK

### Backend
- Python 3.11+
- FastAPI 0.111
- SQLAlchemy 2.0 (async)
- Alembic 1.13 (migrations)
- psycopg3 (PostgreSQL async driver)
- GeoAlchemy2 (PostGIS geometry types)
- Pydantic v2 + pydantic-settings
- python-jose (Microsoft JWT validation)
- msal (Microsoft auth library)
- httpx (async HTTP for Graph API)
- redis (Microsoft group lookup cache)
- boto3 (MinIO/S3 storage — same API for both)
- pytest + pytest-asyncio (testing)

### Database
- PostgreSQL 16 with PostGIS 3.4 extension
- All geometry stored as EPSG:4326 (WGS84) internally
- Always reproject on read if client needs different CRS
- features table PARTITIONED BY HASH(layer_id) with 32 partitions per shard

### Local infrastructure (Docker)
- postgres_meta — port 5432 (metadata database)
- postgres_features — port 5433 (features shard 0)
- pgbouncer — port 6432 (connection pooler, sits in front of both DBs)
- redis — port 6379
- minio — port 9000 (S3 API) and 9001 (web console)

### Frontend
- React 18 + TypeScript
- Vite (build tool)
- Ant Design (UI components — tables, trees, forms, modals)
- @azure/msal-browser + @azure/msal-react (Microsoft SSO)
- axios (HTTP client)
- @tanstack/react-query (server state management)
- react-router-dom v6 (routing)

---

## STEP 4 — DOCKER COMPOSE

Create this exact docker-compose.yml in the project root:

```yaml
services:

  postgres_meta:
    image: postgis/postgis:16-3.4
    container_name: geo_meta
    environment:
      POSTGRES_DB: geo_meta
      POSTGRES_USER: geouser
      POSTGRES_PASSWORD: geopassword
    ports:
      - "5432:5432"
    volumes:
      - meta_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U geouser -d geo_meta"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres_features:
    image: postgis/postgis:16-3.4
    container_name: geo_features
    environment:
      POSTGRES_DB: geo_features
      POSTGRES_USER: geouser
      POSTGRES_PASSWORD: geopassword
    ports:
      - "5433:5432"
    volumes:
      - features_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U geouser -d geo_features"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgbouncer:
    image: bitnami/pgbouncer:latest
    container_name: geo_pgbouncer
    environment:
      POSTGRESQL_HOST: postgres_meta
      POSTGRESQL_PORT: 5432
      POSTGRESQL_DATABASE: geo_meta
      POSTGRESQL_USERNAME: geouser
      POSTGRESQL_PASSWORD: geopassword
      PGBOUNCER_POOL_MODE: transaction
      PGBOUNCER_MAX_CLIENT_CONN: 500
      PGBOUNCER_DEFAULT_POOL_SIZE: 25
      PGBOUNCER_MIN_POOL_SIZE: 5
    ports:
      - "6432:6432"
    depends_on:
      postgres_meta:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    container_name: geo_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio
    container_name: geo_minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  meta_data:
  features_data:
  redis_data:
  minio_data:
```

---

## STEP 5 — ENVIRONMENT FILES

### .env.example (commit this to git)
```
# Microsoft Entra ID
MS_TENANT_ID=your-tenant-id-here
MS_CLIENT_ID=your-client-id-here
MS_CLIENT_SECRET=your-client-secret-here

# Metadata database (via pgbouncer)
META_DB_URL=postgresql+psycopg://geouser:geopassword@localhost:6432/geo_meta

# Features shards (add more as you scale)
FEATURES_SHARD_COUNT=1
FEATURES_SHARD_0_URL=postgresql+psycopg://geouser:geopassword@localhost:5433/geo_features

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO / S3
STORAGE_ENDPOINT=http://localhost:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_BUCKET_STYLES=geo-styles
STORAGE_BUCKET_RASTERS=geo-rasters
STORAGE_BUCKET_EXPORTS=geo-exports

# API settings
API_SECRET_KEY=change-this-to-a-random-string
API_DEBUG=true
API_CORS_ORIGINS=http://localhost:5173
```

### .env (copy from .env.example and fill in real values)
Never commit .env to git.

### .gitignore
```
.env
__pycache__/
*.pyc
.venv/
venv/
node_modules/
dist/
.DS_Store
*.egg-info/
.pytest_cache/
alembic/versions/*.py
!alembic/versions/.gitkeep
```

---

## STEP 6 — PYTHON REQUIREMENTS

### api/requirements.txt
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
alembic==1.13.1
psycopg[binary]==3.1.19
geoalchemy2==0.15.1
pydantic==2.7.1
pydantic-settings==2.2.1
python-jose[cryptography]==3.3.0
msal==1.28.0
httpx==0.27.0
redis==5.0.4
boto3==1.34.0
python-multipart==0.0.9
pytest==8.2.0
pytest-asyncio==0.23.6
```

---

## STEP 7 — METADATA DATABASE SCHEMA

Run this SQL on the metadata database (postgres_meta).
Run it as a single Alembic migration named: `001_initial_schema`.
Always run `CREATE EXTENSION IF NOT EXISTS postgis;` first.

### Table: users
```sql
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
```

### Table: ms_groups
```sql
CREATE TABLE ms_groups (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ms_group_id      TEXT NOT NULL UNIQUE,
    display_name     TEXT,
    description      TEXT,
    synced_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ms_groups_ms_group_id_idx ON ms_groups(ms_group_id);
```

### Table: roles
```sql
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

-- Seed built-in roles immediately after creating the table
INSERT INTO roles (name, description, is_system_role,
    can_read, can_write, can_delete, can_export,
    can_manage_style, can_manage_perms, can_publish)
VALUES
    ('viewer',  'Read only',                         TRUE, TRUE,  FALSE, FALSE, FALSE, FALSE, FALSE, FALSE),
    ('editor',  'Read, write and export',            TRUE, TRUE,  TRUE,  FALSE, TRUE,  FALSE, FALSE, FALSE),
    ('manager', 'Full layer control except permissions', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, TRUE),
    ('admin',   'Full control including permissions', TRUE, TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  TRUE,  TRUE);
```

### Table: geo_databases
```sql
CREATE TABLE geo_databases (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    description  TEXT,
    default_srid INT NOT NULL DEFAULT 4326,
    tags         TEXT[] NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX geo_databases_tags_idx ON geo_databases USING GIN(tags);
```

### Table: group_layers
```sql
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
```

### Table: layers
```sql
CREATE TABLE layers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    database_id    UUID NOT NULL REFERENCES geo_databases(id) ON DELETE CASCADE,
    group_layer_id UUID REFERENCES group_layers(id) ON DELETE SET NULL,
    name           TEXT NOT NULL,
    description    TEXT,
    geometry_type  TEXT NOT NULL,   -- 'POINT','LINESTRING','POLYGON','MULTIPOLYGON', etc.
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
CREATE INDEX layers_database_id_idx ON layers(database_id);
CREATE INDEX layers_group_layer_id_idx ON layers(group_layer_id);
CREATE INDEX layers_shard_id_idx ON layers(shard_id);
CREATE INDEX layers_is_locked_idx ON layers(is_locked) WHERE is_locked = TRUE;
CREATE INDEX layers_status_idx ON layers(status);
CREATE INDEX layers_tags_idx ON layers USING GIN(tags);
CREATE INDEX layers_bbox_idx ON layers USING GIST(bbox) WHERE bbox IS NOT NULL;
CREATE INDEX layers_deleted_at_idx ON layers(deleted_at) WHERE deleted_at IS NULL;
```

### Table: layer_owners
```sql
CREATE TABLE layer_owners (
    layer_id     UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by  UUID REFERENCES users(id),
    PRIMARY KEY (layer_id, user_id)
);
-- Only one primary owner per layer
CREATE UNIQUE INDEX layer_owners_primary_idx
    ON layer_owners(layer_id)
    WHERE is_primary = TRUE;
```

### Trigger: auto-transfer ownership when user deactivated
```sql
CREATE OR REPLACE FUNCTION transfer_ownership_on_deactivate()
RETURNS TRIGGER AS $$
BEGIN
    -- Find all layers where deactivated user is primary owner
    -- Transfer to the group manager
    UPDATE layer_owners lo
    SET user_id = (
        SELECT gl.id FROM users gl
        WHERE gl.id IN (
            SELECT manager_user_id FROM ms_groups
            WHERE ms_group_id IN (
                SELECT p.ms_group_id FROM permissions p
                WHERE p.layer_id = lo.layer_id
                LIMIT 1
            )
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
```

### Table: layer_schema
```sql
CREATE TABLE layer_schema (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id       UUID NOT NULL UNIQUE REFERENCES layers(id) ON DELETE CASCADE,
    json_schema    JSONB NOT NULL DEFAULT '{}',
    schema_version INT NOT NULL DEFAULT 1,
    updated_by     UUID REFERENCES users(id),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Table: layer_styles
```sql
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
```

### Table: permissions
```sql
CREATE TABLE permissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ms_user_id      TEXT,        -- Microsoft object_id
    ms_group_id     TEXT,        -- Microsoft group object_id
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
```

### Permission resolution function (use this in every write endpoint)
```sql
CREATE OR REPLACE FUNCTION can_user_do(
    p_ms_object_id TEXT,
    p_ms_group_ids TEXT[],
    p_layer_id     UUID,
    p_operation    TEXT   -- 'read','write','delete','export','manage_style','manage_perms','publish'
) RETURNS BOOLEAN AS $$
DECLARE
    v_has_explicit_deny BOOLEAN;
    v_has_permission    BOOLEAN;
    v_layer             RECORD;
BEGIN
    SELECT database_id, group_layer_id INTO v_layer FROM layers WHERE id = p_layer_id;

    -- Check for ANY explicit deny first — deny always wins
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

    -- Check for permission at any level
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
```

### Table: group_quotas
```sql
CREATE TABLE group_quotas (
    ms_group_id            TEXT PRIMARY KEY,
    max_layers             INT NOT NULL DEFAULT 100,
    max_features_per_layer BIGINT NOT NULL DEFAULT 1000000,
    max_export_mb          INT NOT NULL DEFAULT 500,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Table: raster_catalog
```sql
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
```

### Table: audit_log
```sql
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
CREATE INDEX audit_log_user_id_idx       ON audit_log(user_id);
CREATE INDEX audit_log_resource_idx      ON audit_log(resource_type, resource_id);
CREATE INDEX audit_log_created_at_idx    ON audit_log(created_at DESC);
CREATE INDEX audit_log_action_idx        ON audit_log(action);
```

### Table: layer_events
```sql
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
```

### Table: sync_snapshots
```sql
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
```

### Table: sync_conflicts
```sql
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
CREATE INDEX sync_conflicts_layer_id_idx  ON sync_conflicts(layer_id);
CREATE INDEX sync_conflicts_user_id_idx   ON sync_conflicts(user_id);
CREATE INDEX sync_conflicts_resolution_idx ON sync_conflicts(resolution) WHERE resolution = 'pending';
```

### Table: failed_syncs
```sql
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
```

---

## STEP 8 — FEATURES DATABASE SCHEMA

Run this SQL on the features database (postgres_features).
Run as Alembic migration named: `001_features_schema`.
Run `CREATE EXTENSION IF NOT EXISTS postgis;` first.

```sql
-- Main features table — partitioned by layer_id
CREATE TABLE features (
    id         BIGSERIAL,
    layer_id   UUID NOT NULL,
    geom       GEOMETRY NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    version    INT NOT NULL DEFAULT 1,
    created_by TEXT,          -- ms_object_id of creator
    updated_by TEXT,          -- ms_object_id of last editor
    deleted_at TIMESTAMPTZ,
    deleted_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, layer_id),
    CONSTRAINT features_geom_valid CHECK (ST_IsValid(geom))
) PARTITION BY HASH (layer_id);

-- Create 32 hash partitions
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

-- Create indexes on each partition
DO $$
BEGIN
    FOR i IN 0..31 LOOP
        EXECUTE format('CREATE INDEX features_p%s_geom_idx ON features_p%s USING GIST(geom)', i, i);
        EXECUTE format('CREATE INDEX features_p%s_layer_id_idx ON features_p%s(layer_id)', i, i);
        EXECUTE format('CREATE INDEX features_p%s_props_idx ON features_p%s USING GIN(properties)', i, i);
        EXECUTE format('CREATE INDEX features_p%s_updated_at_idx ON features_p%s(updated_at DESC)', i, i);
        EXECUTE format('CREATE INDEX features_p%s_deleted_at_idx ON features_p%s(deleted_at) WHERE deleted_at IS NULL', i, i);
    END LOOP;
END $$;

-- Auto-repair invalid geometry on insert
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

-- Auto-update updated_at on every update
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
```

---

## STEP 9 — API STRUCTURE

### api/app/config.py
```python
from pydantic_settings import BaseSettings
from typing import Dict

class Settings(BaseSettings):
    # Microsoft
    ms_tenant_id: str
    ms_client_id: str
    ms_client_secret: str

    # Databases
    meta_db_url: str
    features_shard_count: int = 1
    features_shard_0_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    storage_endpoint: str
    storage_access_key: str
    storage_secret_key: str
    storage_bucket_styles: str = "geo-styles"
    storage_bucket_rasters: str = "geo-rasters"
    storage_bucket_exports: str = "geo-exports"

    # API
    api_secret_key: str
    api_debug: bool = False
    api_cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def shard_urls(self) -> Dict[int, str]:
        urls = {}
        for i in range(self.features_shard_count):
            url = getattr(self, f"features_shard_{i}_url")
            urls[i] = url
        return urls

    class Config:
        env_file = ".env"

settings = Settings()
```

### api/app/db/session.py
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from typing import Dict, AsyncGenerator

# Metadata DB engine
meta_engine = create_async_engine(settings.meta_db_url, echo=settings.api_debug)
MetaSessionLocal = async_sessionmaker(meta_engine, expire_on_commit=False)

# Features shard engines — one per shard
shard_engines: Dict[int, any] = {}
shard_sessions: Dict[int, async_sessionmaker] = {}

for shard_id, url in settings.shard_urls.items():
    engine = create_async_engine(url, echo=settings.api_debug)
    shard_engines[shard_id] = engine
    shard_sessions[shard_id] = async_sessionmaker(engine, expire_on_commit=False)

async def get_meta_db() -> AsyncGenerator[AsyncSession, None]:
    async with MetaSessionLocal() as session:
        yield session

async def get_feature_db(shard_id: int) -> AsyncGenerator[AsyncSession, None]:
    async with shard_sessions[shard_id]() as session:
        yield session
```

### api/app/dependencies.py
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_meta_db, get_feature_db
from app.auth.microsoft import validate_token
from app.auth.models import RequestContext
from app.models.layers import Layer
from typing import Callable

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_meta_db)
) -> RequestContext:
    token = credentials.credentials
    context = await validate_token(token, db)
    if not context:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return context

async def get_layer_feature_db(
    layer_id: str,
    db: AsyncSession = Depends(get_meta_db)
) -> AsyncSession:
    """Get the correct feature shard session for a given layer_id"""
    layer = await db.get(Layer, layer_id)
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    # Return a generator for the correct shard
    async for session in get_feature_db(layer.shard_id):
        return session
```

### api/app/auth/microsoft.py
```python
from jose import jwt, JWTError
import httpx
from app.config import settings
from app.auth.models import RequestContext

MICROSOFT_KEYS_URL = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/discovery/v2.0/keys"
_keys_cache = None

async def get_microsoft_keys():
    global _keys_cache
    if _keys_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(MICROSOFT_KEYS_URL)
            _keys_cache = resp.json()
    return _keys_cache

async def validate_token(token: str, db) -> RequestContext | None:
    try:
        keys = await get_microsoft_keys()
        claims = jwt.decode(
            token,
            keys,
            algorithms=["RS256"],
            audience=settings.ms_client_id
        )
        ms_object_id = claims["oid"]
        ms_group_ids = claims.get("groups", [])

        # Handle Microsoft 200-group overage
        if "_claim_names" in claims and "groups" in claims["_claim_names"]:
            ms_group_ids = await fetch_groups_from_graph(token)

        # Upsert user profile
        user = await upsert_user(db, ms_object_id, claims.get("email",""), claims.get("name",""))

        return RequestContext(
            ms_object_id=ms_object_id,
            ms_group_ids=ms_group_ids,
            user_id=str(user.id),
            is_superadmin=user.is_superadmin
        )
    except JWTError:
        return None

async def fetch_groups_from_graph(token: str) -> list[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me/memberOf",
            headers={"Authorization": f"Bearer {token}"}
        )
        data = resp.json()
        return [g["id"] for g in data.get("value", [])]
```

### api/app/auth/models.py
```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class RequestContext:
    ms_object_id: str
    ms_group_ids: List[str]
    user_id: str
    is_superadmin: bool = False
```

---

## STEP 10 — ROUTER PATTERN

Every router follows this exact pattern. Never deviate.

```python
# api/app/routers/layers.py — example pattern
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_meta_db, get_current_user, get_layer_feature_db
from app.auth.models import RequestContext
from app.services import layer_service, permission_service, audit_service
from app.schemas.layers import LayerCreate, LayerUpdate, LayerResponse

router = APIRouter(prefix="/layers", tags=["layers"])

@router.get("/{layer_id}", response_model=LayerResponse)
async def get_layer(
    layer_id: str,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user)
):
    # 1. Permission check FIRST
    allowed = await permission_service.can_user_do(db, ctx, layer_id, "read")
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    # 2. Business logic in service
    layer = await layer_service.get_layer(db, layer_id)
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")

    return layer

@router.put("/{layer_id}", response_model=LayerResponse)
async def update_layer(
    layer_id: str,
    data: LayerUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user)
):
    # 1. Permission check
    allowed = await permission_service.can_user_do(db, ctx, layer_id, "write")
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    # 2. Lock check
    layer = await layer_service.get_layer(db, layer_id)
    if layer.is_locked:
        raise HTTPException(status_code=423, detail=layer.lock_reason or "Layer is locked")

    # 3. Business logic
    updated = await layer_service.update_layer(db, layer_id, data)

    # 4. Audit log (always after success, never before)
    await audit_service.log(db, ctx, "update", "layer", layer_id,
                            old_value=layer.dict(), new_value=updated.dict())

    return updated
```

---

## STEP 11 — SYNC PROTOCOL (ARGO OFFLINE)

Argo works offline for up to 7 days. Here is the full sync protocol:

### Snapshot (Argo going offline)
```
POST /sync/snapshot
Body: { layer_ids: ["uuid1", "uuid2", ...], device_id: "argo-device-xyz" }

1. Validate user has 'read' permission on all requested layers
2. Check each layer's snapshot has not expired (7 days)
3. For each layer:
   a. Record sync_snapshots row (layer_id, user_id, device_id, snapshotted_at, expires_at)
   b. Return all features WHERE deleted_at IS NULL
4. Return: { snapshots: [...], features_by_layer: {...} }
```

### Delta sync (Argo coming back online — what changed?)
```
GET /sync/delta?layer_id=X&since=<ISO timestamp>&device_id=Y

1. Check snapshot has not expired (expires_at > now())
2. Return: {
     updated: [ features where updated_at > since AND deleted_at IS NULL ],
     deleted: [ feature ids where deleted_at > since ]
   }
```

### Push (Argo pushing its offline edits)
```
POST /sync/push
Body: {
  device_id: "argo-device-xyz",
  edits: [
    { feature_id: 123, layer_id: "uuid", operation: "update",
      version: 5, geom: {...}, properties: {...} }
  ]
}

For each edit:
1. Check layer is not locked → if locked, add to failed_syncs
2. Check permission → if denied, add to failed_syncs
3. Attempt UPDATE WHERE id = feature_id AND version = client_version
   a. If 1 row updated → success, increment version
   b. If 0 rows updated → version conflict → add to sync_conflicts, resolution = 'server_wins'
4. Return: {
     succeeded: [feature_ids],
     conflicts: [{ feature_id, server_version, client_version }],
     failed: [{ feature_id, reason }]
   }
```

### Staleness check
```
GET /sync/status?layer_id=X&device_id=Y

Returns:
{
  snapshot_age_hours: 42,
  is_expired: false,
  server_updated_at: "2024-01-15T10:00:00Z",
  local_snapshotted_at: "2024-01-14T12:00:00Z",
  pending_conflicts: 2
}

If is_expired = true, Argo must do a full snapshot before editing.
```

---

## STEP 12 — STORAGE SERVICE

All file operations go through `storage_service.py`. Never use boto3 directly in routers or other services.

```python
# api/app/services/storage_service.py
import boto3
from app.config import settings

_client = None

def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
        )
    return _client

async def upload_lyrx(layer_id: str, file_bytes: bytes, filename: str) -> str:
    """Upload .lyrx file. Returns S3 key."""
    key = f"layers/{layer_id}/{filename}"
    get_client().put_object(
        Bucket=settings.storage_bucket_styles,
        Key=key,
        Body=file_bytes
    )
    return key

async def get_signed_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL that expires after expires_in seconds."""
    return get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in
    )

async def ensure_buckets_exist():
    """Run on startup — create buckets if they don't exist."""
    client = get_client()
    for bucket in [
        settings.storage_bucket_styles,
        settings.storage_bucket_rasters,
        settings.storage_bucket_exports
    ]:
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            client.create_bucket(Bucket=bucket)
```

---

## STEP 13 — WEB APP STRUCTURE

### Install commands
```bash
cd geo-platform
npm create vite@latest web -- --template react-ts
cd web
npm install \
  @azure/msal-browser@3 \
  @azure/msal-react@2 \
  antd \
  @ant-design/icons \
  axios \
  react-router-dom \
  @tanstack/react-query \
  dayjs
```

### Pages to build (in this order)
1. **AppLayout** — sidebar navigation, top bar with user info and logout
2. **DatabasesPage** — list all databases, create/edit/delete
3. **LayersPage** — tree view of group_layers and layers, with lock/unlock button
4. **LayerDetailPage** — layer metadata, schema editor, style viewer, feature count
5. **PermissionsPage** — matrix view: rows=layers, columns=users/groups, cells=role
6. **UsersPage** — list all users (from Microsoft), show their groups and roles
7. **AuditLogPage** — filterable table: by user, by resource, by date, by action
8. **SyncConflictsPage** — list pending conflicts, allow manager to resolve

### API client pattern
```typescript
// web/src/api/client.ts
import axios from "axios";
import { msalInstance } from "../auth/msalConfig";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

// Attach Microsoft JWT to every request automatically
client.interceptors.request.use(async (config) => {
  const account = msalInstance.getActiveAccount();
  if (account) {
    const result = await msalInstance.acquireTokenSilent({
      scopes: [`api://${import.meta.env.VITE_MS_CLIENT_ID}/access_as_user`],
      account,
    });
    config.headers.Authorization = `Bearer ${result.accessToken}`;
  }
  return config;
});

export default client;
```

---

## STEP 14 — MAKEFILE

Create this Makefile in the project root for common commands:

```makefile
.PHONY: up down logs migrate seed api web test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	cd api && alembic upgrade head

seed:
	cd api && python -m app.seed

api:
	cd api && uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	cd api && pytest tests/ -v

install-api:
	cd api && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt

install-web:
	cd web && npm install

setup: up migrate seed
	@echo "Geo Platform is ready."
	@echo "API: http://localhost:8000/docs"
	@echo "Web: http://localhost:5173"
	@echo "MinIO: http://localhost:9001"
```

---

## STEP 15 — BUILD ORDER

Build in this exact order. Do not skip steps. Confirm each step works before moving to the next.

### Phase 1 — Infrastructure
1. Create folder structure
2. Write docker-compose.yml
3. Write .env and .env.example
4. Run `docker compose up -d` and verify all containers are healthy
5. Run `make logs` and confirm no errors

### Phase 2 — Database
6. Set up Alembic (alembic init, configure env.py for both databases)
7. Write migration 001 for metadata schema (all tables above)
8. Write migration 001 for features schema (partitioned features table)
9. Run `make migrate`
10. Open DBeaver, connect to both databases, verify all tables exist

### Phase 3 — API core
11. Write config.py and verify settings load from .env
12. Write db/session.py with both meta and shard engines
13. Write auth/microsoft.py JWT validation
14. Write auth/permissions.py (calls can_user_do SQL function)
15. Write dependencies.py
16. Write main.py with CORS, all routers registered, startup events
17. Run `make api` and verify `/docs` loads at http://localhost:8000/docs

### Phase 4 — API endpoints
18. health.py router (GET /health — no auth required)
19. auth.py router (GET /auth/me — returns current user from JWT)
20. databases.py router (CRUD for geo_databases)
21. group_layers.py router (CRUD + tree structure)
22. layers.py router (CRUD + lock/unlock)
23. features.py router (spatial query + CRUD)
24. permissions.py router (grant/deny/list)
25. symbology.py router (get/update style, upload .lyrx)
26. sync.py router (snapshot/delta/push)
27. audit.py router (read-only log viewer)

### Phase 5 — Web app
28. Set up Vite + React + TypeScript
29. Configure MSAL for Microsoft login
30. Build AppLayout with sidebar
31. Build DatabasesPage
32. Build LayersPage (tree view is the most complex — use Ant Design Tree)
33. Build PermissionsPage
34. Build AuditLogPage
35. Build SyncConflictsPage

### Phase 6 — Testing
36. Write pytest tests for auth, permissions, features
37. Write integration tests for sync protocol
38. Manual test with DBeaver: verify data written correctly
39. Manual test with Thunder Client: verify all endpoints

---

## IMPORTANT REMINDERS

- **Microsoft auth**: The user's Microsoft tenant is already set up. Ask the user for their MS_TENANT_ID and MS_CLIENT_ID before writing any auth code.
- **Geometry CRS**: Always store geometry as EPSG:4326 internally. Never store mixed CRS.
- **Shard routing**: Always look up layer.shard_id from metadata DB before querying features. Never hardcode shard_id = 0 except in config.
- **Layer lock**: Check is_locked BEFORE every write to features, not after.
- **Audit log**: Write AFTER success, not before. Use async fire-and-forget so it never slows responses.
- **Soft deletes**: WHERE deleted_at IS NULL on every query, every time.
- **Optimistic lock**: WHERE version = client_version on every feature UPDATE. 0 rows = conflict.
- **S3 paths**: Never store full URLs in the database. Store only the S3 key (path). Generate signed URLs on demand.
- **Partitioning**: Always include layer_id in feature queries. Without it, PostgreSQL scans all 32 partitions.
- **Testing**: Run `make test` after completing each phase. Fix all failures before moving to the next phase.

---

## SCALING REFERENCE

| Tier | Layers | Action |
|------|--------|--------|
| Tier 1 | 0–5,000 | features_shard_count=1. No changes needed. |
| Tier 2 | 5k–50k | Add features_shard_1_url to .env. Increase features_shard_count=2. Run migration script to redistribute layers across shards. |
| Tier 3 | 50k+ | Add shards 2–7. Increase features_shard_count. Run migration. Add read replica per shard for Argo sync and exports. |

The API code never changes between tiers. Only config.py and .env change.

---

*End of build plan. Start with STEP 0 and work through to STEP 15 in order.*
