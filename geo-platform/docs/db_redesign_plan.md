# Database Redesign: Workspace + Permission System

## Context

The current geo-platform uses `GeoDatabase > GroupLayer (folders) > Layer` with a complex permission system (allow/deny ACL, bitmask roles, hierarchy walk at query time). This redesign introduces:

- **Workspaces** (replaces databases) with nestable **folders** and **maps**
- **Maps** as first-class containers for layers (layers can be shared across maps)
- Simplified permission model: **no deny rules**, flat grants, highest-role-wins
- New role ladder: **viewer < editor < manager < admin** + system-level **superviewer/superadmin**
- `is_public` flag on maps and layers (visible to any authenticated user)
- Creator auto-gets admin; no ownership concept
- Version history for maps and layers

---

## 1. New Hierarchy

```
Workspace
 ├── Folder (nestable, unlimited depth)
 │    ├── Folder
 │    │    └── Map
 │    └── Map
 └── Map (can live at workspace root)
      ├── Layer (via join table)
      └── Layer
```

- A **Layer** belongs to one workspace but can appear in **multiple maps** via `map_layers` join table
- Folders are organizational only — no permissions cascade automatically
- When granting permissions on a folder/map, the UI asks which children to include and issues a bulk grant (individual rows per resource)

---

## 2. Database Schema (migration `007_permission_redesign.py`)

### 2.1 Workspaces (rename `geo_databases`)

```sql
ALTER TABLE geo_databases RENAME TO workspaces;
ALTER TABLE workspaces ADD COLUMN created_by UUID REFERENCES users(id);
-- keeps: id, name, description, default_srid, tags, created_at
```

### 2.2 Folders (rename `group_layers`)

```sql
ALTER TABLE group_layers RENAME TO folders;
ALTER TABLE folders RENAME COLUMN database_id TO workspace_id;
ALTER TABLE folders ADD COLUMN created_by UUID REFERENCES users(id);
-- keeps: id, workspace_id, parent_id (self-ref), name, description, tags, sort_order, deleted_at/by, created_at
```

### 2.3 Maps (new table)

```sql
CREATE TABLE maps (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    folder_id     UUID REFERENCES folders(id) ON DELETE SET NULL,
    name          TEXT NOT NULL,
    description   TEXT,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    is_public     BOOLEAN NOT NULL DEFAULT FALSE,
    thumbnail_s3_key TEXT,
    sort_order    INT NOT NULL DEFAULT 0,
    created_by    UUID REFERENCES users(id),
    deleted_at    TIMESTAMPTZ,
    deleted_by    UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX maps_workspace_id_idx ON maps(workspace_id);
CREATE INDEX maps_folder_id_idx    ON maps(folder_id);
CREATE INDEX maps_is_public_idx    ON maps(is_public) WHERE is_public = TRUE;
CREATE INDEX maps_tags_idx         ON maps USING GIN(tags);
CREATE INDEX maps_deleted_at_idx   ON maps(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX maps_created_by_idx   ON maps(created_by);
```

### 2.4 Layers (modify existing)

```sql
ALTER TABLE layers RENAME COLUMN database_id TO workspace_id;
ALTER TABLE layers ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE layers ADD COLUMN created_by UUID REFERENCES users(id);
ALTER TABLE layers DROP COLUMN group_layer_id;  -- replaced by map_layers

CREATE INDEX layers_is_public_idx  ON layers(is_public) WHERE is_public = TRUE;
CREATE INDEX layers_created_by_idx ON layers(created_by);
```

### 2.5 Map-Layer Join Table (new)

```sql
CREATE TABLE map_layers (
    map_id     UUID NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
    layer_id   UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    sort_order INT NOT NULL DEFAULT 0,
    is_visible BOOLEAN NOT NULL DEFAULT TRUE,
    opacity    REAL NOT NULL DEFAULT 1.0 CHECK (opacity >= 0.0 AND opacity <= 1.0),
    added_by   UUID REFERENCES users(id),
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (map_id, layer_id)
);

CREATE INDEX map_layers_layer_id_idx   ON map_layers(layer_id);
CREATE INDEX map_layers_map_id_sort_idx ON map_layers(map_id, sort_order);
```

### 2.6 Users (add superviewer)

```sql
ALTER TABLE users ADD COLUMN is_superviewer BOOLEAN NOT NULL DEFAULT FALSE;
```

### 2.7 Unified Resource Permissions (replaces `permissions` + `roles` tables)

```sql
CREATE TYPE resource_type AS ENUM ('workspace', 'folder', 'map', 'layer');

CREATE TABLE resource_permissions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Principal: exactly one must be set
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,
    group_id     UUID REFERENCES ms_groups(id) ON DELETE CASCADE,

    -- Resource: exactly one must be set
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    folder_id    UUID REFERENCES folders(id) ON DELETE CASCADE,
    map_id       UUID REFERENCES maps(id) ON DELETE CASCADE,
    layer_id     UUID REFERENCES layers(id) ON DELETE CASCADE,

    -- Role: 1=viewer, 2=editor, 3=manager, 4=admin
    role_level   SMALLINT NOT NULL CHECK (role_level BETWEEN 1 AND 4),

    granted_by   UUID REFERENCES users(id),
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT rp_one_principal CHECK (
        (user_id IS NOT NULL)::INT + (group_id IS NOT NULL)::INT = 1
    ),
    CONSTRAINT rp_one_resource CHECK (
        (workspace_id IS NOT NULL)::INT + (folder_id IS NOT NULL)::INT +
        (map_id IS NOT NULL)::INT + (layer_id IS NOT NULL)::INT = 1
    ),
    -- One role per principal+resource pair (PG16 NULLS NOT DISTINCT)
    CONSTRAINT rp_unique_user_workspace  UNIQUE NULLS NOT DISTINCT (user_id, workspace_id),
    CONSTRAINT rp_unique_user_folder     UNIQUE NULLS NOT DISTINCT (user_id, folder_id),
    CONSTRAINT rp_unique_user_map        UNIQUE NULLS NOT DISTINCT (user_id, map_id),
    CONSTRAINT rp_unique_user_layer      UNIQUE NULLS NOT DISTINCT (user_id, layer_id),
    CONSTRAINT rp_unique_group_workspace UNIQUE NULLS NOT DISTINCT (group_id, workspace_id),
    CONSTRAINT rp_unique_group_folder    UNIQUE NULLS NOT DISTINCT (group_id, folder_id),
    CONSTRAINT rp_unique_group_map       UNIQUE NULLS NOT DISTINCT (group_id, map_id),
    CONSTRAINT rp_unique_group_layer     UNIQUE NULLS NOT DISTINCT (group_id, layer_id)
);

-- Lookup indexes
CREATE INDEX rp_user_id_idx      ON resource_permissions(user_id)      WHERE user_id IS NOT NULL;
CREATE INDEX rp_group_id_idx     ON resource_permissions(group_id)     WHERE group_id IS NOT NULL;
CREATE INDEX rp_workspace_id_idx ON resource_permissions(workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX rp_folder_id_idx    ON resource_permissions(folder_id)    WHERE folder_id IS NOT NULL;
CREATE INDEX rp_map_id_idx       ON resource_permissions(map_id)       WHERE map_id IS NOT NULL;
CREATE INDEX rp_layer_id_idx     ON resource_permissions(layer_id)     WHERE layer_id IS NOT NULL;

-- Hot path: user's effective role on a layer
CREATE INDEX rp_user_layer_idx   ON resource_permissions(user_id, layer_id, role_level)
                                 WHERE user_id IS NOT NULL AND layer_id IS NOT NULL;
CREATE INDEX rp_group_layer_idx  ON resource_permissions(group_id, layer_id, role_level)
                                 WHERE group_id IS NOT NULL AND layer_id IS NOT NULL;
```

### 2.8 Version History (new)

```sql
CREATE TABLE resource_versions (
    id            BIGSERIAL PRIMARY KEY,
    resource_type resource_type NOT NULL,
    resource_id   UUID NOT NULL,
    version       INT NOT NULL,
    changes       JSONB NOT NULL,    -- snapshot of changed fields
    changed_by    UUID REFERENCES users(id),
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (resource_type, resource_id, version)
);

CREATE INDEX rv_resource_idx   ON resource_versions(resource_type, resource_id);
CREATE INDEX rv_changed_at_idx ON resource_versions(changed_at DESC);
```

### 2.9 Drop Old Objects

```sql
DROP TABLE permissions;
DROP TABLE roles;
DROP TABLE layer_owners;
DROP FUNCTION IF EXISTS can_user_do;
```

---

## 3. Role System

Roles are a Python `IntEnum` — no database table. The integer is stored directly in `resource_permissions.role_level`.

```python
# app/auth/roles.py
from enum import IntEnum

class RoleLevel(IntEnum):
    VIEWER  = 1   # read only
    EDITOR  = 2   # edit features/data
    MANAGER = 3   # + grant/revoke viewer & editor to others
    ADMIN   = 4   # + grant/revoke manager & admin, remove managers

    @property
    def can_read(self) -> bool:
        return self >= RoleLevel.VIEWER

    @property
    def can_edit(self) -> bool:
        return self >= RoleLevel.EDITOR

    @property
    def can_manage_perms(self) -> bool:
        return self >= RoleLevel.MANAGER

    @property
    def can_admin(self) -> bool:
        return self >= RoleLevel.ADMIN

    def can_grant(self, target_role: "RoleLevel") -> bool:
        """Managers can grant viewer/editor. Admins can grant anything."""
        if self >= RoleLevel.ADMIN:
            return True
        if self >= RoleLevel.MANAGER:
            return target_role <= RoleLevel.EDITOR
        return False
```

**System-level roles** (flags on `users` table, not per-resource):
- `is_superviewer` — viewer on everything, no edits
- `is_superadmin` — full access to everything

**Grant rules:**
- Manager can grant/revoke: viewer, editor
- Admin can grant/revoke: viewer, editor, manager, admin
- Cannot remove the last admin from a resource (orphan protection)
- Creator auto-gets admin (inserted on resource creation)

**To add a new role:** Add an enum member, adjust integer ordering if needed (migration to renumber existing rows).

---

## 4. Permission Resolution

### No cascade at query time

Unlike the old system which walked `layer → group_layer → database`, the new system stores **flat permission rows per resource**. When a user grants permissions on a folder, the UI asks which children to include and issues a bulk `POST /permissions/bulk` creating individual rows.

### Group hierarchy expansion (once per request)

```sql
CREATE OR REPLACE FUNCTION get_user_group_ids(p_user_id UUID, p_ms_group_ids TEXT[])
RETURNS UUID[] AS $$
DECLARE
    v_result UUID[];
BEGIN
    WITH RECURSIVE
    direct_groups AS (
        -- MS groups from token
        SELECT id FROM ms_groups WHERE ms_group_id = ANY(p_ms_group_ids)
        UNION
        -- Custom groups user is a direct member of
        SELECT group_id FROM custom_group_members WHERE user_id = p_user_id
        UNION
        -- Custom groups linked to user's MS groups
        SELECT cgml.custom_group_id
        FROM custom_group_ms_links cgml
        WHERE cgml.ms_group_id = ANY(p_ms_group_ids)
    ),
    ancestors(id, depth) AS (
        SELECT id, 0 FROM direct_groups
        UNION ALL
        SELECT g.parent_group_id, a.depth + 1
        FROM ms_groups g
        JOIN ancestors a ON g.id = a.id
        WHERE g.parent_group_id IS NOT NULL
          AND a.depth < 16
    )
    SELECT ARRAY(SELECT DISTINCT id FROM ancestors WHERE id IS NOT NULL)
    INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql STABLE;
```

### Effective role check

```sql
CREATE OR REPLACE FUNCTION get_effective_role(
    p_user_id UUID, p_group_ids UUID[],
    p_resource_type resource_type, p_resource_id UUID
) RETURNS SMALLINT AS $$
    SELECT MAX(rp.role_level)
    FROM resource_permissions rp
    WHERE (rp.user_id = p_user_id OR rp.group_id = ANY(p_group_ids))
      AND CASE p_resource_type
          WHEN 'workspace' THEN rp.workspace_id = p_resource_id
          WHEN 'folder'    THEN rp.folder_id = p_resource_id
          WHEN 'map'       THEN rp.map_id = p_resource_id
          WHEN 'layer'     THEN rp.layer_id = p_resource_id
      END;
$$ LANGUAGE sql STABLE;
```

Highest role wins. No deny. One query.

### Python permission check

```python
# app/auth/permissions.py
async def get_effective_role(db, ctx, resource_type, resource_id) -> RoleLevel | None:
    if ctx.is_superadmin:
        return RoleLevel.ADMIN
    group_ids = await get_user_group_ids(db, ctx)
    level = await db.execute(text("SELECT get_effective_role(...)"), {...})
    result = level.scalar()
    if ctx.is_superviewer:
        return max(RoleLevel.VIEWER, RoleLevel(result)) if result else RoleLevel.VIEWER
    return RoleLevel(result) if result else None

async def can_user_do(db, ctx, resource_type, resource_id, operation) -> bool:
    role = await get_effective_role(db, ctx, resource_type, resource_id)
    if role is None:
        return False
    match operation:
        case "read":          return role.can_read
        case "edit" | "write": return role.can_edit
        case "manage_perms":  return role.can_manage_perms
        case "admin":         return role.can_admin
```

### Permission fetch on map open

When a user opens a map, **one SQL function** returns all accessible layers with their effective roles:

```sql
CREATE OR REPLACE FUNCTION get_map_layers_for_user(
    p_user_id UUID, p_group_ids UUID[], p_map_id UUID
) RETURNS TABLE (
    layer_id UUID, layer_name TEXT, sort_order INT,
    is_visible BOOLEAN, opacity REAL, is_public BOOLEAN,
    effective_role SMALLINT
) AS $$
    SELECT l.id, l.name, ml.sort_order, ml.is_visible, ml.opacity, l.is_public,
        (SELECT MAX(rp.role_level) FROM resource_permissions rp
         WHERE (rp.user_id = p_user_id OR rp.group_id = ANY(p_group_ids))
           AND rp.layer_id = l.id) AS effective_role
    FROM map_layers ml
    JOIN layers l ON l.id = ml.layer_id
    WHERE ml.map_id = p_map_id AND l.deleted_at IS NULL
      AND (
          EXISTS (SELECT 1 FROM resource_permissions rp
                  WHERE (rp.user_id = p_user_id OR rp.group_id = ANY(p_group_ids))
                    AND rp.layer_id = l.id)
          OR l.is_public = TRUE
      )
    ORDER BY ml.sort_order;
$$ LANGUAGE sql STABLE;
```

**Total queries to open a map:** 3 (group expansion + map role check + layers with roles). Constant regardless of layer count.

---

## 5. API Endpoints

### Workspaces
| Method | Path | Auth |
|--------|------|------|
| GET | `/workspaces` | authenticated (filtered to accessible) |
| POST | `/workspaces` | superadmin |
| GET | `/workspaces/{id}` | viewer+ on workspace |
| PUT | `/workspaces/{id}` | admin on workspace |
| DELETE | `/workspaces/{id}` | superadmin |

### Folders
| Method | Path | Auth |
|--------|------|------|
| GET | `/workspaces/{ws_id}/folders` | viewer+ on workspace |
| POST | `/workspaces/{ws_id}/folders` | editor+ on workspace |
| GET | `/folders/{id}` | viewer+ on folder |
| PUT | `/folders/{id}` | editor+ on folder |
| DELETE | `/folders/{id}` | admin on folder |
| PATCH | `/folders/{id}/move` | admin on folder |

### Maps
| Method | Path | Auth |
|--------|------|------|
| GET | `/workspaces/{ws_id}/maps` | authenticated (filtered) |
| POST | `/workspaces/{ws_id}/maps` | editor+ on workspace |
| GET | `/maps/{id}` | viewer+ on map OR is_public |
| GET | `/maps/{id}/open` | viewer+ on map OR is_public (returns layers w/ roles) |
| PUT | `/maps/{id}` | editor+ on map |
| DELETE | `/maps/{id}` | admin on map |
| POST | `/maps/{id}/layers` | editor+ on map AND viewer+ on layer |
| DELETE | `/maps/{id}/layers/{layer_id}` | editor+ on map |
| PUT | `/maps/{id}/layers/{layer_id}` | editor+ on map (sort/visibility/opacity) |

### Layers
| Method | Path | Auth |
|--------|------|------|
| GET | `/workspaces/{ws_id}/layers` | authenticated (filtered) |
| POST | `/workspaces/{ws_id}/layers` | editor+ on workspace |
| GET | `/layers/{id}` | viewer+ OR is_public |
| PUT | `/layers/{id}` | editor+ on layer |
| DELETE | `/layers/{id}` | admin on layer |
| GET | `/layers/{id}/maps` | viewer+ on layer (which maps contain it) |
| POST/DELETE | `/layers/{id}/lock` | editor+ on layer |
| GET/PUT | `/layers/{id}/schema` | viewer/editor+ on layer |

### Permissions
| Method | Path | Auth |
|--------|------|------|
| GET | `/permissions?resource_type=X&resource_id=Y` | manager+ on resource |
| POST | `/permissions` | manager+ (grant rules apply) |
| POST | `/permissions/bulk` | manager+ on each resource |
| PUT | `/permissions/{id}` | manager+ (update role level) |
| DELETE | `/permissions/{id}` | manager+ (revoke rules apply) |
| GET | `/permissions/my` | authenticated (own permissions) |
| GET | `/permissions/effective?resource_type=X&resource_id=Y` | authenticated |

### Users
| Method | Path | Auth |
|--------|------|------|
| PATCH | `/users/{id}/flags` | superadmin (set is_superadmin / is_superviewer) |

---

## 6. Migration Strategy

### Alembic migration `007_permission_redesign.py`

**Order of operations:**
1. Create `resource_type` enum, `maps`, `map_layers`, `resource_permissions`, `resource_versions` tables
2. Add columns: `users.is_superviewer`, `layers.is_public`, `layers.created_by`, `workspaces.created_by`, `folders.created_by`
3. Rename `geo_databases` → `workspaces`, `group_layers` → `folders`, FK columns `database_id` → `workspace_id`
4. Migrate data from `permissions` → `resource_permissions` (map old role names to integers, map `ms_user_id` → `users.id`, `ms_group_id` → `ms_groups.id`)
5. Migrate `layer_owners` → `resource_permissions` with role_level=4 (admin)
6. Drop `layers.group_layer_id` column
7. Drop old tables: `permissions`, `roles`, `layer_owners`
8. Drop old function: `can_user_do()`
9. Create new SQL functions: `get_user_group_ids`, `get_effective_role`, `get_map_layers_for_user`
10. Create indexes

---

## 7. Files to Modify

### Backend — Rewrite
- `api/app/models/permissions.py` — `Permission`+`Role` → `ResourcePermission` model
- `api/app/models/databases.py` — `GeoDatabase` → `Workspace`
- `api/app/models/layers.py` — `GroupLayer` → `Folder`, update `Layer` (drop group_layer_id, add is_public/created_by), drop `LayerOwner`
- `api/app/auth/permissions.py` — new `get_effective_role`, `can_user_do`, `get_user_group_ids`
- `api/app/auth/models.py` — add `is_superviewer`, `expanded_group_ids` to `RequestContext`
- `api/app/routers/permissions.py` — rewrite with new grant/revoke/bulk logic
- `api/app/routers/databases.py` → rename to `routers/workspaces.py`
- `api/app/routers/group_layers.py` → rename to `routers/folders.py`
- `api/app/routers/layers.py` — update for new model
- `api/app/schemas/permissions.py` — new Pydantic schemas
- `api/app/main.py` — update router imports

### Backend — New
- `api/alembic/versions/007_permission_redesign.py` — the migration
- `api/app/auth/roles.py` — `RoleLevel` IntEnum
- `api/app/routers/maps.py` — map CRUD + open + layer management
- `api/app/models/maps.py` — `Map` and `MapLayer` ORM models
- `api/app/schemas/maps.py` — Pydantic schemas for maps

### Frontend — Update (later phase)
- Replace all `database` references with `workspace`
- Replace `group_layer` references with `folder`
- Add Map CRUD pages
- Update permission UI (simplified: no deny, role level picker, bulk grant modal)

---

## 8. Verification

```bash
docker compose up -d
cd api && venv\Scripts\alembic -x db=meta upgrade meta@head
cd api && venv\Scripts\python run.py
cd web && npm run dev
```

**Test scenarios:**
1. Create workspace → creator auto-gets admin
2. Create map in workspace → creator auto-gets admin on map
3. Create layer → creator auto-gets admin on layer
4. Add layer to map → layer appears in map
5. Add same layer to second map → shared layer works
6. Grant user viewer on map → user sees map but no layers (no layer perms yet)
7. Grant user viewer on specific layers → user now sees those layers in the map
8. Set layer `is_public=true` → all authenticated users see it
9. Bulk grant on folder → UI creates individual permission rows for selected children
10. Manager grants viewer/editor → works. Manager tries to grant admin → rejected.
11. Admin grants manager → works. Admin removes another admin → works (if not last).
12. Superviewer → sees everything, edits blocked.
13. Group hierarchy: user in child group, permission on parent group → user has access.
14. Open map → single API call returns all accessible layers with effective roles.
