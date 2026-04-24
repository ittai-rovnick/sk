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

- **Repo:** https://github.com/ittai-rovnick/sk.git
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
| Auth | python-jose (HS256 JWT) | — | local JWT auth, OS auto-login in DEV_MODE |
| Meta DB | PostgreSQL 16 + PostGIS 3.4 | — | geo_meta on port 5432 |
| Features DB | PostgreSQL 16 + PostGIS 3.4 | — | geo_features on port 5433 |
| Connection pooler | pgbouncer (bitnami) | latest | port 6432 → 5432, transaction mode |
| Cache | Redis 7 | alpine | port 6379, used for group membership caching |
| Object storage | MinIO | latest | S3-compatible, port 9000, console 9001 |
| Web framework | React 18 + TypeScript | — | |
| Web bundler | Vite | latest | port 5173 in dev |
| Web UI library | Ant Design | latest | |
| Web map | MapLibre GL JS + terra-draw | latest | MapLibre-native drawing (not mapbox-gl-draw) |
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
│       │   ├── local.py          Local JWT auth (create_token, validate_token, auto-login)
│       │   └── permissions.py    can_user_do() → calls PostgreSQL function
│       ├── db/
│       │   ├── base.py           SQLAlchemy declarative Base
│       │   └── session.py        MetaSessionLocal, shard_sessions dict
│       ├── models/               SQLAlchemy ORM models (9 files)
│       ├── schemas/              Pydantic request/response schemas (6 files)
│       ├── routers/              FastAPI routers (13 files — all implemented)
│       └── services/             Business logic services (8 files, incl. layer_geometry.py)
├── web/                          React frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx               Routes definition
│       ├── auth/AuthContext.tsx   React auth context — token + user in localStorage
│       ├── api/client.ts         Axios instance with Bearer token interceptor
│       ├── components/           Shared + layout + layer + permission components
│       │   └── layers/           SchemaEditor.tsx, AttributeTable.tsx, LayerForm.tsx, etc.
│       └── pages/                DatabasesPage, LayersPage, MapPage, UsersPage, etc.
├── docker-compose.yml
├── Makefile
├── COMMANDS.txt                  Quick reference for start/stop/connect
└── docs/                        This folder
```

---

## Database design

### geo_meta (21 tables) — metadata, users, permissions

| Table | Purpose |
|-------|---------|
| `users` | User records synced from MS Entra ID |
| `ms_groups` | MS Entra group records + custom groups (`is_custom`, `parent_id` for nesting) |
| `custom_group_members` | Manual user → custom group membership |
| `custom_group_ms_links` | Links custom groups to real MS Entra group IDs |
| `geo_databases` | Top-level containers for layers |
| `group_layers` | Folder-like groupings of layers (tree structure, self-referencing) |
| `layers` | Vector layer definitions (`geometry_types TEXT[]` auto-derived from features, srid, status, lock state) |
| `layer_owners` | Many-to-many: which users own which layers |
| `layer_schema` | JSON Schema for feature properties validation per layer |
| `layer_styles` | ArcGIS renderer/label/popup config per layer (JSONB) |
| `permissions` | ACL entries: (user or group) × (database or group_layer or layer) × role |
| `roles` | Permission bitmasks: can_read, can_write, can_delete, can_export, etc. |
| `raster_catalog` | Metadata for raster files stored in MinIO |
| `audit_log` | Immutable log of all write actions |
| `layer_events` | Layer-specific event stream (create, publish, lock, etc.) |
| `sync_snapshots` | Records when Argo downloaded a snapshot of a layer |
| `sync_conflicts` | Optimistic lock conflicts detected during push |
| `failed_syncs` | Push attempts that failed (for retry/diagnosis) |
| `group_quotas` | Per-MS-group limits (max layers, features, export size) |

### geo_features (1 logical table, 32 physical partitions)

| Table | Purpose |
|-------|---------|
| `features` (partitioned) | All vector feature geometries and properties |

Partitioned by `HASH(layer_id)` into 32 partitions (`features_p0` through `features_p31`).
This means every query MUST include `layer_id` in the WHERE clause for partition pruning.

Columns: `id` (bigserial), `layer_id` (uuid), `geom` (PostGIS Geometry),
`properties` (JSONB), `version` (int, for optimistic locking), `created_by`, `updated_by`,
`deleted_at` (soft delete), `created_at`, `updated_at`.

---

## Permission model

Permissions are stored in the `permissions` table as ACL entries:
- **Principal:** either `ms_user_id` or `ms_group_id` (exactly one)
- **Resource:** either `database_id`, `group_layer_id`, or `layer_id` (exactly one)
- **Role:** references `roles` table (can_read, can_write, can_delete, can_export, can_manage_style, can_manage_perms, can_publish)
- **Allow/deny:** the `allow` boolean supports explicit deny rules

Permission resolution is handled by a PostgreSQL function `can_user_do(ms_object_id, ms_group_ids[], layer_id, operation)` which walks up the resource hierarchy (layer → group_layer → database) and checks both user and group entries. Superadmins bypass all checks.

---

## Sync model (for Argo offline app)

1. **Snapshot** (`POST /sync/snapshot`) — Argo downloads all features for requested layers. A `sync_snapshots` record is created with timestamp and TTL (72 hours).
2. **Delta** (`GET /sync/delta/{layer_id}`) — Argo requests changes since its last snapshot. Returns features updated/deleted after `snapshotted_at`.
3. **Push** (`POST /sync/push`) — Argo sends edits (create/update/delete). Each edit is applied with optimistic locking (`WHERE version = client_version`). Conflicts are recorded in `sync_conflicts` and returned in the response.
4. **Status** (`GET /sync/status/{layer_id}`) — Returns snapshot age, expiry, and pending conflicts.

---

## Key architectural rules (non-negotiable)

1. **Routers: HTTP only.** No business logic in routers. No DB queries in routers except through the session dependency. All logic goes in services.
2. **All DB ops async/await.** No sync calls. boto3 (synchronous) must be wrapped in `asyncio.to_thread()`.
3. **Write order:** check permission → check lock → do work → write audit log.
4. **Soft deletes everywhere.** `deleted_at = now()`, never hard DELETE on features/layers/group_layers. All list queries filter `WHERE deleted_at IS NULL`.
5. **Optimistic locking.** Features update uses `WHERE version = client_version AND deleted_at IS NULL`. If 0 rows affected → HTTP 409, record `SyncConflict`.
6. **Geometry:** always EPSG:4326. `ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(...)), 4326)` on every insert. Never store geometries in other projections.
7. **Partition queries.** Always include `layer_id` in feature queries. Without it, Postgres scans all 32 partitions.
8. **S3 keys only.** Store the S3 object key (e.g. `layers/{id}/style.lyrx`) in the DB. Call `generate_presigned_url()` at request time. Never store full MinIO URLs.
