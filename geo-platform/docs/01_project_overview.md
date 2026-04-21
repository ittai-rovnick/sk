# Geo Platform — Project Overview

## What is this?

Geo Platform is a full-stack geographic data management system. It manages vector layers,
features (geometries + properties), raster catalogs, and symbology (ArcGIS `.lyrx` styles).

It serves three types of clients simultaneously:
- **ArcGIS Pro** — desktop GIS authoring. Uses the REST API to read/write layers and features.
- **Esri Portal** — web GIS viewer. Reads layers, features, and signed URLs for rasters/styles.
- **Argo** — an offline-capable .NET field app. Uses the sync endpoints (snapshot → delta → push)
  to download data, work offline, and push edits back with conflict detection.

## Repository

- **Branch:** `develop`
- **Project root:** `geo-platform/`
- **API:** `geo-platform/api/`
- **Web app:** `geo-platform/web/`
- **Docs:** `geo-platform/docs/`

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         Clients                              │
│    ArcGIS Pro       Esri Portal        Argo (.NET offline)   │
└────────┬────────────────┬──────────────────┬─────────────────┘
         │                │                  │
         └────────────────▼──────────────────┘
                   FastAPI REST API
                   localhost:8000
                   /docs → Swagger UI
                         │
         ┌───────────────┼─────────────────────┐
         │               │                     │
    pgbouncer        geo_features            MinIO
    :6432→:5432         :5433              :9000/:9001
         │                                  (S3 storage for
    geo_meta                               .lyrx files and
    :5432                                   raster COGs)
    (21 tables)
         │
      Redis
      :6379
    (auth cache,
     group membership)
```

---

## Stack

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| API framework | FastAPI | latest | async, OpenAPI auto-docs at /docs |
| ORM | SQLAlchemy | 2.0.40 | async mode only (no sync sessions) |
| DB driver | psycopg3 (psycopg[binary]) | 3.2.13 | async, requires SelectorEventLoop on Windows |
| Geometry | GeoAlchemy2 | latest | PostGIS geometry columns in SQLAlchemy models |
| Validation | Pydantic v2 | 2.10.6 | request/response schemas |
| Settings | pydantic-settings | 2.7.1 | reads from api/.env |
| Auth | python-jose + MSAL | — | validates MS Entra ID JWTs; local JWT in dev mode |
| Meta DB | PostgreSQL 16 + PostGIS 3.4 | — | geo_meta on port 5432 |
| Features DB | PostgreSQL 16 + PostGIS 3.4 | — | geo_features on port 5433 |
| Connection pooler | pgbouncer (bitnami) | latest | port 6432 → 5432, transaction mode |
| Cache | Redis 7 | alpine | port 6379, used for group membership caching |
| Object storage | MinIO | latest | S3-compatible, port 9000, console 9001 |
| Web framework | React 18 + TypeScript | — | |
| Web bundler | Vite | latest | port 5173 in dev |
| Web UI library | Ant Design | latest | |
| Web auth | @azure/msal-react | latest | Microsoft login |
| Web data fetching | React Query (TanStack) | latest | |
| Web routing | React Router v6 | — | |

---

## Folder structure

```
geo-platform/
├── api/                          FastAPI backend
│   ├── run.py                    Entry point (sets WindowsSelectorEventLoopPolicy)
│   ├── requirements.txt
│   ├── .env                      Config (never committed — copy from .env.example)
│   ├── .env.example
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py                Async migrations + Windows SelectorEventLoop fix
│   │   └── versions/
│   │       ├── 001_initial_schema.py      geo_meta schema (branch_labels=("meta",))
│   │       └── 001_features_schema.py     geo_features schema (branch_labels=("features",))
│   └── app/
│       ├── main.py               FastAPI app, middleware, router registration
│       ├── config.py             pydantic-settings Settings class
│       ├── dependencies.py       get_meta_db, get_current_user FastAPI dependencies
│       ├── auth/
│       │   ├── models.py         RequestContext dataclass
│       │   ├── microsoft.py      JWT validation via python-jose
│       │   ├── local.py          Local JWT for dev mode (no MS required)
│       │   └── permissions.py    can_user_do() → calls PostgreSQL function
│       ├── db/
│       │   ├── base.py           SQLAlchemy declarative Base
│       │   └── session.py        MetaSessionLocal, shard_sessions dict
│       ├── models/               SQLAlchemy ORM models (9 files)
│       ├── schemas/              Pydantic request/response schemas (6 files)
│       ├── routers/              FastAPI routers (13 files — all implemented)
│       └── services/             Business logic services (7 files)
├── web/                          React frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx               Routes definition
│       ├── auth/AuthProvider.tsx MSAL wrapper
│       ├── components/           Shared + layout + layer + permission components
│       └── pages/                DatabasesPage, LayersPage, UsersPage, etc.
├── docker-compose.yml
├── Makefile
├── COMMANDS.txt                  Quick reference for start/stop/connect
└── docs/                        This folder
```

---

## API Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`  
Auth: `Authorization: Bearer <token>` on all protected endpoints.

All endpoints return JSON. Errors follow the pattern `{"detail": "message"}`.

---

### Authentication (`/auth`)

Two modes controlled by `dev_mode` in `.env`:

- **MS Entra ID mode** (production): standard MSAL OAuth flow, tokens validated with `python-jose` against Microsoft JWKS.
- **Local mode** (development): simple JWT issued by the server, no Microsoft required. The server auto-creates the user on first login.

#### `POST /auth/login`
Dev mode only. Log in by username (email prefix).
```json
// Request
{ "username": "itay" }

// Response
{ "token": "eyJ...", "user": { ...UserResponse } }
```
Auto-creates the user as superadmin if not found.

#### `GET /auth/auto-login`
Dev mode only. Auto-detects username from OS environment variable (`%USERNAME%` on Windows, `$USER` on Unix) and returns a token. Useful for scripts and first-time setup.
```json
// Response
{ "token": "eyJ...", "user": { ...UserResponse } }
```

#### `GET /auth/me`
Returns the current user based on the Bearer token.
```json
// Response: UserResponse
```

---

### Databases (`/databases`)

Databases are the top-level containers. A database groups layers and group-layers together.

#### `GET /databases`
List all databases sorted by name.
```json
// Response: List[DatabaseResponse]
[{
  "id": "uuid",
  "name": "israel-survey",
  "description": "...",
  "default_srid": 4326,
  "tags": ["production"],
  "created_at": "2024-01-01T00:00:00"
}]
```

#### `POST /databases` — superadmin only
```json
// Request
{
  "name": "israel-survey",         // required, unique
  "description": "...",            // optional
  "default_srid": 4326,            // optional, default 4326
  "tags": ["production"]           // optional
}
// Response: DatabaseResponse, 201
```

#### `GET /databases/{database_id}`
Single database by ID.

#### `PUT /databases/{database_id}` — superadmin only
All fields optional. Returns updated DatabaseResponse.

#### `DELETE /databases/{database_id}` — superadmin only
Hard delete. Returns 204.

---

### Layers (`/layers`)

Layers hold vector feature data (points, lines, polygons). A layer belongs to one database and optionally to a group-layer folder. Features are stored separately in `geo_features`.

#### `GET /layers`
List non-deleted layers. Sorted by `sort_order` then `name`.
```
Query params:
  database_id    (UUID)  filter by database
  group_layer_id (UUID)  filter by folder
```
```json
// Response: List[LayerResponse]
[{
  "id": "uuid",
  "database_id": "uuid",
  "group_layer_id": "uuid or null",
  "name": "roads",
  "description": "...",
  "geometry_types": ["LINESTRING"],   // inferred from actual features
  "srid": 4326,
  "tags": [],
  "status": "published",             // draft | published | archived
  "health": "ok",
  "is_locked": false,
  "locked_by": null,
  "locked_at": null,
  "lock_reason": null,
  "sort_order": 0,
  "created_at": "...",
  "updated_at": "..."
}]
```

#### `POST /layers`
Creates a layer and assigns the creator as primary owner.
```json
// Request
{
  "database_id": "uuid",            // required
  "group_layer_id": "uuid",         // optional, folder
  "name": "roads",                  // required
  "description": "...",             // optional
  "srid": 4326,                     // optional, default 4326
  "tags": [],                       // optional
  "sort_order": 0                   // optional
}
// Response: LayerResponse, 201
```

#### `GET /layers/{layer_id}`
Single layer.

#### `PUT /layers/{layer_id}` — requires write permission
All fields optional: `name`, `description`, `group_layer_id`, `tags`, `status`, `sort_order`.

#### `DELETE /layers/{layer_id}` — requires delete permission
Soft delete (`deleted_at = now()`). Returns 204. Layer is never hard-deleted.

#### `POST /layers/{layer_id}/lock` — requires write permission
Prevents any feature edits on this layer.
```json
// Request
{ "reason": "sending to review" }    // optional
// Response: LayerResponse (is_locked: true)
// Error 409 if already locked
```

#### `DELETE /layers/{layer_id}/lock`
Unlock. Only the user who locked it or a superadmin can unlock. Returns LayerResponse.

---

### Features (`/layers/{layer_id}/features`)

Features are the actual geometries and attribute data. They live in `geo_features` (partitioned by `layer_id`).

Geometry is always GeoJSON, always EPSG:4326. On write the server runs `ST_MakeValid` before storing.

#### `GET /layers/{layer_id}/features` — requires read permission
```
Query params:
  limit         int     default 1000
  offset        int     default 0
  min_lon       float   ┐
  min_lat       float   │  bounding-box filter
  max_lon       float   │  (all four required together)
  max_lat       float   ┘
  geometry_type string  POINT | LINESTRING | POLYGON | MULTI*
```
```json
// Response: List[FeatureResponse]
[{
  "id": 42,
  "layer_id": "uuid",
  "geom": { "type": "Point", "coordinates": [34.78, 31.97] },
  "properties": { "name": "junction-1", "lane_count": 3 },
  "version": 1,
  "created_by": "entra-oid-or-local",
  "updated_by": "entra-oid-or-local",
  "created_at": "...",
  "updated_at": "..."
}]
```

#### `GET /layers/{layer_id}/features/{feature_id}` — requires read permission
Single feature.

#### `POST /layers/{layer_id}/features` — requires write permission
```json
// Request
{
  "geom": { "type": "Point", "coordinates": [34.78, 31.97] },
  "properties": { "name": "junction-1" }
}
// Response: FeatureResponse with version=1, 201
// Error 409 if layer is locked
```

#### `PUT /layers/{layer_id}/features/{feature_id}` — requires write permission
Uses **optimistic locking**: the `version` in the request must match the server's current version. If it doesn't, the update is rejected with 409 and a conflict is recorded in `sync_conflicts`.
```json
// Request
{
  "geom": { "type": "Point", "coordinates": [34.79, 31.98] },  // optional
  "properties": { "name": "junction-1-updated" },              // optional
  "version": 1                                                  // required — must match server
}
// Response: FeatureResponse with version incremented to 2
// Error 409: version conflict, or layer is locked
```

#### `DELETE /layers/{layer_id}/features/{feature_id}` — requires delete permission
Soft delete. Returns 204. Error 409 if layer is locked.

#### `POST /layers/{layer_id}/features/bulk-delete` — requires delete permission
```json
// Request
{ "feature_ids": [1, 2, 3] }
// Response
{ "deleted": 3 }
// Error 409 if layer is locked
```

---

### Group-Layers (`/group-layers`)

Group-layers are folders that organize layers within a database. They support a tree structure via `parent_id`.

#### `GET /group-layers`
```
Query params:
  database_id  (UUID)  filter by database
```
Returns `List[GroupLayerResponse]` sorted by `sort_order`, then `name`.

#### `POST /group-layers` — superadmin only
```json
{
  "database_id": "uuid",
  "parent_id": "uuid or null",     // parent folder
  "name": "Survey 2024",
  "description": "...",
  "tags": [],
  "sort_order": 0
}
// Response: GroupLayerResponse, 201
```

#### `GET /group-layers/{group_layer_id}`

#### `PUT /group-layers/{group_layer_id}` — superadmin only
Optional fields: `name`, `description`, `tags`, `sort_order`, `parent_id`.

#### `DELETE /group-layers/{group_layer_id}` — superadmin only
Soft delete. Returns 204.

---

### Permissions (`/roles`, `/permissions`)

The ACL system. Permissions associate a **principal** (user or group) with a **resource** (database, folder, or layer) and a **role** (viewer/editor/admin).

#### `GET /roles`
List all roles sorted by name.
```json
[{
  "id": "uuid",
  "name": "editor",
  "description": "...",
  "can_read": true,
  "can_write": true,
  "can_delete": true,
  "can_export": true,
  "can_manage_style": false,
  "can_manage_perms": false,
  "can_publish": false,
  "is_system_role": true
}]
```

Built-in system roles:
| Role | read | write | delete | export | manage_style | manage_perms | publish |
|------|------|-------|--------|--------|--------------|--------------|---------|
| viewer | ✓ | | | | | | |
| editor | ✓ | ✓ | ✓ | ✓ | | | |
| admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

#### `GET /permissions`
List permissions. At least one filter required.
```
Query params:
  layer_id       UUID
  database_id    UUID
  group_layer_id UUID
```
```json
[{
  "id": "uuid",
  "ms_user_id": "entra-oid or null",
  "ms_group_id": "entra-oid or custom-group-id or null",
  "database_id": "uuid or null",
  "group_layer_id": "uuid or null",
  "layer_id": "uuid or null",
  "role_id": "uuid",
  "allow": true,
  "granted_by": "uuid",
  "granted_at": "..."
}]
```

#### `POST /permissions`
Grant or deny access. Exactly one principal and exactly one resource must be set.
```json
// Request
{
  "ms_user_id": "entra-oid",       // set this OR ms_group_id
  "ms_group_id": "entra-oid",      // set this OR ms_user_id
  "database_id": "uuid",           // set exactly one of these three
  "group_layer_id": "uuid",
  "layer_id": "uuid",
  "role_id": "uuid",
  "allow": true                    // false = explicit deny (deny always wins)
}
// Response: PermissionResponse, 201
```
Authorization:
- Superadmin: always allowed.
- Non-superadmin: only allowed to grant on layers they have `manage_perms` for.
- Database/group-layer grants currently require superadmin.

#### `DELETE /permissions/{permission_id}`
Revoke permission. Returns 204. Requires superadmin or `manage_perms` on the resource.

---

### Symbology (`/layers/{layer_id}/styles`)

Each layer can have multiple named styles. A style holds the ArcGIS renderer spec, label config, and popup config as JSONB. Only one style per layer can be marked `is_default`.

#### `GET /layers/{layer_id}/styles`
```json
[{
  "id": "uuid",
  "layer_id": "uuid",
  "name": "default",
  "renderer": { "type": "simple", "symbol": { ... } },   // ArcGIS JSON renderer
  "label_config": { ... },    // nullable
  "popup_config": { ... },    // nullable
  "is_default": true,
  "lyrx_s3_key": "geo-styles/layers/uuid/default.lyrx",  // nullable
  "created_by": "uuid",
  "created_at": "..."
}]
```

#### `POST /layers/{layer_id}/styles` — requires manage_style permission
```json
{
  "name": "default",
  "renderer": { "type": "simple", "symbol": { ... } },
  "label_config": null,
  "popup_config": null,
  "is_default": false    // setting true clears is_default on all other styles
}
// Response: StyleResponse, 201
```

#### `GET /layers/{layer_id}/styles/{style_id}`

#### `PUT /layers/{layer_id}/styles/{style_id}` — requires manage_style permission
All fields optional.

#### `DELETE /layers/{layer_id}/styles/{style_id}` — requires manage_style permission
Returns 204.

#### `POST /layers/{layer_id}/styles/{style_id}/lyrx` — requires manage_style permission
Upload an ArcGIS `.lyrx` file. Multipart form-data.
```json
// Response
{ "key": "geo-styles/layers/uuid/style-uuid.lyrx" }
```

#### `GET /layers/{layer_id}/styles/{style_id}/lyrx`
Get a presigned S3 download URL (valid for a short window).
```json
{ "url": "http://minio:9000/geo-styles/...?X-Amz-Signature=..." }
```

---

### Rasters (`/rasters`)

The raster catalog stores metadata for Cloud-Optimized GeoTIFFs (COGs) stored in MinIO. The API manages metadata only — file upload is out-of-band.

#### `GET /rasters`
```
Query params:
  database_id  UUID  filter by database
```

#### `POST /rasters` — superadmin only
```json
{
  "database_id": "uuid or null",
  "group_layer_id": "uuid or null",
  "name": "elevation-2024",
  "s3_key": "rasters/elevation-2024.tif",   // MinIO key
  "format": "COG",
  "srid": 4326,
  "resolution_m": 0.5,
  "band_count": 1,
  "tags": []
}
// Response: RasterResponse, 201
```

#### `GET /rasters/{raster_id}`

#### `PUT /rasters/{raster_id}` — superadmin only
Optional: `name`, `tags`, `status`, `resolution_m`, `band_count`, `group_layer_id`.

#### `DELETE /rasters/{raster_id}` — superadmin only
Returns 204.

---

### Users (`/users`)

#### `GET /users` — superadmin only
```
Query params:
  is_active  bool  filter active/inactive
```

#### `GET /users/me`
Current user from token.

#### `GET /users/{user_id}`
Superadmin or self only.

#### `POST /users/{user_id}/deactivate` — superadmin only
Sets `is_active=false`, `deactivated_at=now()`. Returns UserResponse.

#### `POST /users/{user_id}/activate` — superadmin only
Reactivates a deactivated user. Returns UserResponse.

#### `POST /users/{user_id}/make-superadmin` — superadmin only
Grants superadmin flag. Returns UserResponse.

---

### Custom Groups (`/groups`)

Custom groups are platform-created groups (as opposed to MS Entra groups). They support a tree hierarchy and can be linked to MS Entra groups so that Entra members are automatically included.

#### `GET /groups`
List all custom groups flat.

#### `GET /groups/tree`
Returns groups as a recursive tree.
```json
[{
  "id": "uuid",
  "display_name": "Field Teams",
  "children": [{
    "id": "uuid",
    "display_name": "North Team",
    "children": []
  }]
}]
```

#### `POST /groups`
```json
{
  "display_name": "North Team",
  "description": "...",
  "parent_group_id": "uuid or null"
}
```

#### `PUT /groups/{group_id}`
Optional: `display_name`, `description`.

#### `POST /groups/{group_id}/move`
Re-parent a group. Validates that the target is not a descendant (no cycles).
```json
{ "parent_group_id": "uuid or null" }
```

#### `GET /groups/{group_id}/members`
List users manually added to this group.

#### `POST /groups/{group_id}/members`
```json
{ "user_id": "uuid" }
```

#### `DELETE /groups/{group_id}/members/{user_id}`
Returns 204.

#### `GET /groups/{group_id}/ms-links`
List MS Entra groups linked to this custom group.

#### `POST /groups/{group_id}/ms-links`
Link an Entra group. Members of the Entra group will be treated as members of this custom group for permission resolution.
```json
{ "ms_group_id": "entra-oid", "ms_display_name": "GIS Department" }
```

#### `DELETE /groups/{group_id}/ms-links/{ms_group_id}`
Returns 204.

---

### Sync (`/sync`) — for Argo offline app

The sync system lets the Argo field app download data, edit offline, and push changes back. Each round-trip is: **snapshot → [work offline] → delta (to catch server changes) → push**.

#### `POST /sync/snapshot`
Downloads all features for the requested layers. Creates a `SyncSnapshot` record with a 72-hour TTL. Requires read permission on each layer.
```json
// Request
{
  "layer_ids": ["uuid", "uuid"],
  "device_id": "argo-device-abc123",
  "geometry_type": "POINT"         // optional — filter to one geometry type
}

// Response
{
  "snapshots": [{
    "layer_id": "uuid",
    "snapshotted_at": "2024-01-01T10:00:00Z",
    "feature_count": 1500,
    "expires_at": "2024-01-04T10:00:00Z"
  }],
  "features_by_layer": {
    "uuid": [
      { "id": 1, "layer_id": "uuid", "geom": {...}, "properties": {...}, "version": 3, ... }
    ]
  }
}
```

#### `GET /sync/delta/{layer_id}`
Returns only the changes since the device's snapshot. Error 410 if the snapshot has expired — device must re-snapshot.
```
Query params:
  device_id      string  required
  geometry_type  string  optional
```
```json
{
  "updated": [
    { "id": 1, "layer_id": "uuid", "geom": {...}, "properties": {...}, "version": 4, "updated_at": "..." }
  ],
  "deleted": [2, 3, 7]
}
```

#### `POST /sync/push`
Applies a batch of edits. Uses optimistic locking for updates and deletes. Conflicts are recorded and returned — the server never silently drops data.

The `version` for `update`/`delete` operations must match the server's current version for that feature. Mismatches become conflicts.
```json
// Request
{
  "device_id": "argo-device-abc123",
  "edits": [
    {
      "feature_id": 0,                          // 0 = create (server assigns id)
      "layer_id": "uuid",
      "operation": "create",
      "geom": { "type": "Point", "coordinates": [34.78, 31.97] },
      "properties": { "name": "new-point" }
    },
    {
      "feature_id": 42,
      "layer_id": "uuid",
      "operation": "update",
      "version": 3,                             // must match server version
      "geom": { "type": "Point", "coordinates": [34.79, 31.98] },
      "properties": { "name": "updated-name" }
    },
    {
      "feature_id": 7,
      "layer_id": "uuid",
      "operation": "delete",
      "version": 1
    }
  ]
}

// Response
{
  "succeeded": [101, 42],          // feature IDs (creates get new server-assigned IDs)
  "conflicts": [{
    "feature_id": 42,
    "server_version": 5,
    "client_version": 3
  }],
  "failed": [{
    "feature_id": 7,
    "reason": "Layer is locked"
  }]
}
```

#### `GET /sync/status/{layer_id}`
```
Query params:
  device_id  string  required
```
```json
{
  "snapshot_age_hours": 24.5,
  "is_expired": false,
  "server_updated_at": "2024-01-02T08:00:00Z",
  "local_snapshotted_at": "2024-01-01T10:00:00Z",
  "pending_conflicts": 3
}
```

---

### Health

#### `GET /health`
No auth. Used by Docker healthchecks and load balancers.
```json
{ "status": "ok" }
```

---

## Pydantic Schemas

Schemas are in `api/app/schemas/`. They validate all request bodies and shape all responses.

### Layer schemas (`schemas/layers.py`)
| Schema | Used for |
|--------|---------|
| `LayerCreate` | `POST /layers` request |
| `LayerUpdate` | `PUT /layers/{id}` request — all fields optional |
| `LayerLockRequest` | `POST /layers/{id}/lock` request |
| `LayerResponse` | all layer responses |

### Feature schemas (`schemas/features.py`)
| Schema | Used for |
|--------|---------|
| `FeatureCreate` | `POST .../features` request |
| `FeatureUpdate` | `PUT .../features/{id}` request — geom/props optional, version required |
| `BulkDeleteRequest` | `POST .../features/bulk-delete` request |
| `FeatureResponse` | all feature responses |

### Permission schemas (`schemas/permissions.py`)
| Schema | Used for |
|--------|---------|
| `PermissionGrant` | `POST /permissions` request |
| `PermissionResponse` | all permission responses |
| `RoleResponse` | `GET /roles` response |

### Symbology schemas (`schemas/symbology.py`)
| Schema | Used for |
|--------|---------|
| `StyleCreate` | `POST .../styles` request |
| `StyleUpdate` | `PUT .../styles/{id}` request |
| `StyleResponse` | all style responses |

### User schemas (`schemas/users.py`)
| Schema | Used for |
|--------|---------|
| `UserResponse` | all user responses |

### Sync schemas (`schemas/sync.py`)
| Schema | Used for |
|--------|---------|
| `SnapshotRequest` | `POST /sync/snapshot` request |
| `PushRequest` | `POST /sync/push` request |
| `EditItem` | one edit within a PushRequest |
| `DeltaResponse` | `GET /sync/delta/{id}` response |
| `PushResponse` | `POST /sync/push` response |
| `SyncStatusResponse` | `GET /sync/status/{id}` response |
| `ConflictItem` | one conflict entry in PushResponse |
| `FailedItem` | one failure entry in PushResponse |

---

## Database Design

### geo_meta (21 tables) — metadata, users, permissions

| Table | Purpose |
|-------|---------|
| `users` | User records (synced from MS Entra ID, or local in dev) |
| `ms_groups` | MS Entra groups + custom platform groups (is_custom flag) |
| `custom_group_members` | Manual user→custom-group memberships |
| `custom_group_ms_links` | Links an Entra group into a custom group |
| `geo_databases` | Top-level containers for layers |
| `group_layers` | Folder tree (self-referencing parent_id) |
| `layers` | Vector layer definitions |
| `layer_owners` | Who owns/manages a layer (many-to-many, one is_primary) |
| `layer_schema` | JSON Schema v7 for feature property validation per layer |
| `layer_styles` | ArcGIS renderer/label/popup config (JSONB) |
| `permissions` | ACL entries |
| `roles` | Permission capability bitmasks |
| `raster_catalog` | Metadata for COG rasters in MinIO |
| `audit_log` | Immutable log of all write actions |
| `layer_events` | Layer-specific event stream |
| `sync_snapshots` | Records Argo snapshot downloads (TTL: 72 hours) |
| `sync_conflicts` | Optimistic lock conflicts during push |
| `failed_syncs` | Failed push attempts (for retry/diagnosis) |
| `group_quotas` | Per-group limits (max layers, features, export size) |

**Key columns of note:**

`layers`:
- `geometry_types: String[]` — inferred from actual features, updated by `refresh_layer_geometry_types()`
- `shard_id: int` — which geo_features shard this layer's features live in
- `is_locked / locked_by / lock_reason` — editorial lock mechanism
- `bbox: Geometry(POLYGON, 4326)` — cached bounding box

`permissions`:
- `ms_user_id` XOR `ms_group_id` — exactly one principal
- `database_id` XOR `group_layer_id` XOR `layer_id` — exactly one resource
- `allow: bool` — false = explicit deny (deny always beats allow)

`ms_groups`:
- `is_custom: bool` — true = created in the platform, false = synced from Entra
- `parent_group_id` — enables group hierarchy for custom groups

### geo_features — 1 logical table, 32 physical partitions

Partitioned by `HASH(layer_id)` into `features_p0` through `features_p31`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | bigserial | PK within partition |
| `layer_id` | uuid | partition key — always include in WHERE |
| `geom` | Geometry (PostGIS) | any type, EPSG:4326 |
| `properties` | JSONB | feature attributes |
| `version` | int | starts at 1, incremented on every update |
| `created_by` | string | Entra OID |
| `updated_by` | string | Entra OID |
| `deleted_at` | timestamptz | null = alive; soft delete |
| `deleted_by` | string | Entra OID |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Every query MUST include `layer_id` in the WHERE clause** to enable partition pruning.

---

## Permission Model

### Resolution

Permissions are resolved by the PostgreSQL function `can_user_do(p_ms_object_id, p_ms_group_ids[], p_layer_id, p_operation) → bool`:

1. Look up the layer's `database_id` and `group_layer_id`.
2. Walk the hierarchy: **layer → group_layer → database**.
3. At each level, check both user-level (`ms_user_id = p_ms_object_id`) and all group-level (`ms_group_id = ANY(p_ms_group_ids)`) entries.
4. Collect all matching rows.
5. **Deny wins:** if any matching row has `allow = false` and the role has the requested capability → return false.
6. If any matching row has `allow = true` and the role has the requested capability → return true.
7. Otherwise → return false (implicit deny).

Superadmins bypass `can_user_do` entirely.

The Python wrapper in `auth/permissions.py` calls this function via `SELECT can_user_do(...)`.

### Operations
`read`, `write`, `delete`, `export`, `manage_style`, `manage_perms`, `publish`

### Cascading
A permission on `database_id` cascades live to all layers in that database — the function walks up to database level automatically. No copying or materialization needed.

### Custom group resolution
On login, the server resolves:
1. The user's direct MS Entra group memberships (from the JWT `groups` claim).
2. Any custom groups the user belongs to (via `custom_group_members`).
3. Any custom groups linked to any of their Entra groups (via `custom_group_ms_links`).

The resulting list of group IDs is stored in `RequestContext.ms_group_ids` and passed to `can_user_do`.

---

## Sync Model (for Argo)

```
Device                                  Server
  │                                        │
  │── POST /sync/snapshot ───────────────> │  saves SyncSnapshot (TTL 72h)
  │<─ {features_by_layer, snapshots} ──── │
  │                                        │
  │  [works offline, edits features]       │  [other users may edit too]
  │                                        │
  │── GET /sync/delta/{layer_id} ───────> │  returns changes since snapshotted_at
  │<─ {updated: [...], deleted: [...]} ── │
  │                                        │
  │── POST /sync/push ──────────────────> │  applies edits with optimistic locking
  │<─ {succeeded, conflicts, failed} ──── │  conflicts saved in sync_conflicts
```

**Conflict handling:** The server never silently discards data. A version mismatch creates a `SyncConflict` row and returns the conflict to the client. Resolution is manual and tracked in `sync_conflicts.resolution`.

---

## Key Architectural Rules (non-negotiable)

1. **Routers: HTTP only.** No business logic in routers. All logic in services.
2. **All DB ops async/await.** No sync calls. boto3 (synchronous) wrapped in `asyncio.to_thread()`.
3. **Write order:** check permission → check lock → do work → write audit log.
4. **Soft deletes everywhere.** `deleted_at = now()`, never hard DELETE on features/layers/group_layers.
5. **Optimistic locking.** Feature update uses `WHERE version = client_version AND deleted_at IS NULL`. 0 rows affected → HTTP 409 → record `SyncConflict`.
6. **Geometry:** always EPSG:4326. `ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(...)), 4326)` on every insert.
7. **Partition queries.** Always include `layer_id` in feature queries. Without it, Postgres scans all 32 partitions.
8. **S3 keys only.** Store the S3 object key in the DB. Call `generate_presigned_url()` at request time. Never store full MinIO URLs.
