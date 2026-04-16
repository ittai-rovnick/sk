# Geo Platform — Build Progress

Last updated: 2026-04-16

---

## Phase tracker

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Prerequisites verified (Python 3.13, Node, Docker, VS Code extensions) | ✅ Done |
| 1 | Project folder structure created | ✅ Done |
| 2 | Coding principles documented | ✅ Done |
| 3 | Technology stack locked in | ✅ Done |
| 4 | docker-compose.yml written — 5 services | ✅ Done |
| 5 | .env, .env.example, .gitignore, Makefile written | ✅ Done |
| 6 | api/requirements.txt written (Python 3.13-compatible versions) | ✅ Done |
| 7 | SQLAlchemy models — 9 model files | ✅ Done |
| 8 | Pydantic schemas — 6 schema files | ✅ Done |
| 9 | Alembic migrations written and run successfully | ✅ Done |
| 10 | Web scaffold — React + Vite + Ant Design installed and running | ✅ Done |
| 11 | API starts, /health returns {"status":"ok","db":"ok"} | ✅ Done |
| 12 | All 54 API endpoints implemented | ✅ Done |
| 13 | Web app wired to API (MSAL auth + React Query + working pages) | ⏳ Next |
| 14 | Tests (pytest for API, Playwright or Vitest for web) | ⬜ Pending |
| 15 | Deployment | ⬜ Pending |

---

## What is working right now

### Docker — 5 containers, all healthy

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| geo_meta | postgis/postgis:16-3.4 | 5432 | Metadata PostgreSQL database |
| geo_features | postgis/postgis:16-3.4 | 5433 | Features PostgreSQL database |
| geo_pgbouncer | public.ecr.aws/bitnami/pgbouncer | 6432→5432 | Connection pooler for geo_meta |
| geo_redis | redis:7-alpine | 6379 | Cache |
| geo_minio | minio/minio | 9000, 9001 | Object storage (S3-compatible) |

Start: `docker compose up -d` from `geo-platform/`

### Database schema — fully migrated

**geo_meta** (19 tables):

| Table | Key columns | Notes |
|-------|-------------|-------|
| `users` | id, ms_object_id, email, is_superadmin, is_active | Synced from MS Entra |
| `ms_groups` | id, ms_group_id, display_name, synced_at | MS Entra groups |
| `geo_databases` | id, name, default_srid, tags | Top-level containers |
| `group_layers` | id, database_id, parent_id, name, sort_order, deleted_at | Folder tree |
| `layers` | id, database_id, group_layer_id, name, geometry_type, srid, status, is_locked, shard_id, deleted_at | Vector layer metadata |
| `layer_owners` | layer_id, user_id, is_primary | Who owns each layer |
| `layer_schema` | layer_id, json_schema, schema_version | Property validation schema |
| `layer_styles` | id, layer_id, name, renderer (JSONB), label_config, popup_config, is_default, lyrx_s3_key | ArcGIS styles |
| `permissions` | id, ms_user_id or ms_group_id, database_id or group_layer_id or layer_id, role_id, allow | ACL entries |
| `roles` | id, name, can_read, can_write, can_delete, can_export, can_manage_style, can_manage_perms, can_publish | Permission bitmasks |
| `raster_catalog` | id, database_id, name, s3_key, format, srid, bbox, tags | Raster file metadata |
| `audit_log` | id, user_id, action, resource_type, resource_id, old_value, new_value, ip_address | All write events |
| `layer_events` | id, layer_id, user_id, event_type, payload | Layer-specific event stream |
| `sync_snapshots` | id, layer_id, user_id, device_id, snapshotted_at, expires_at | Argo download records |
| `sync_conflicts` | id, layer_id, feature_id, client_payload, server_version, client_version, resolution | Push conflicts |
| `failed_syncs` | id, user_id, layer_id, device_id, payload, error_code, resolved | Failed push attempts |
| `group_quotas` | ms_group_id, max_layers, max_features_per_layer, max_export_mb | Group limits |

**geo_features** — partitioned features table:
- `features` partitioned `BY HASH(layer_id)` into 32 partitions: `features_p0` … `features_p31`
- Columns: `id` (bigserial PK), `layer_id` (uuid), `geom` (PostGIS Geometry), `properties` (JSONB), `version` (int), `created_by`, `updated_by`, `deleted_at`, `created_at`, `updated_at`

Run migrations:
```powershell
cd geo-platform/api
venv\Scripts\alembic -x db=meta upgrade meta@head
venv\Scripts\alembic -x db=features upgrade features@head
```

### API — 54 endpoints, all implemented

Start: `cd geo-platform/api && venv\Scripts\python run.py`
Swagger UI: http://localhost:8000/docs

**Health**
- `GET /health` — returns `{"status":"ok","db":"ok"}`, no auth required

**Auth**
- `GET /auth/me` — returns the current user record from the JWT token

**Databases** — top-level containers for layers
- `GET /databases` — list all databases
- `POST /databases` — create (superadmin only)
- `GET /databases/{id}` — get one
- `PUT /databases/{id}` — update (superadmin only)
- `DELETE /databases/{id}` — delete (superadmin only)

**Group Layers** — folder tree for organising layers
- `GET /group-layers?database_id=` — list (optionally filtered by database)
- `POST /group-layers` — create (superadmin only)
- `GET /group-layers/{id}` — get one
- `PUT /group-layers/{id}` — update (superadmin only)
- `DELETE /group-layers/{id}` — soft delete (superadmin only)

**Layers** — vector layer definitions
- `GET /layers?database_id=&group_layer_id=` — list (filtered)
- `POST /layers` — create, auto-assigns creator as primary owner
- `GET /layers/{id}` — get one
- `PUT /layers/{id}` — update (requires write permission)
- `DELETE /layers/{id}` — soft delete (requires delete permission)
- `POST /layers/{id}/lock` — lock layer with optional reason (requires write)
- `DELETE /layers/{id}/lock` — unlock (lock owner or superadmin only)
- `GET /layers/{id}/schema` — get JSON Schema for feature properties
- `PUT /layers/{id}/schema` — update schema, auto-increments schema_version
- `POST /layers/{id}/lyrx` — upload ArcGIS .lyrx file to MinIO (requires manage_style)

**Features** — vector geometries in geo_features database
- `GET /layers/{id}/features?min_lon=&min_lat=&max_lon=&max_lat=&limit=&offset=` — list with optional bbox filter
- `POST /layers/{id}/features` — create, geometry auto-validated with ST_MakeValid
- `GET /layers/{id}/features/{fid}` — get one feature as GeoJSON
- `PUT /layers/{id}/features/{fid}` — update with optimistic locking (body must include current `version`)
- `DELETE /layers/{id}/features/{fid}` — soft delete

**Symbology** — ArcGIS renderer/label/popup styles
- `GET /layers/{id}/styles` — list all styles for a layer
- `POST /layers/{id}/styles` — create style (requires manage_style)
- `GET /layers/{id}/styles/{sid}` — get one style
- `PUT /layers/{id}/styles/{sid}` — update style
- `DELETE /layers/{id}/styles/{sid}` — delete style
- `POST /layers/{id}/styles/{sid}/lyrx` — upload .lyrx file to MinIO
- `GET /layers/{id}/styles/{sid}/lyrx` — get pre-signed download URL (1 hour TTL)

**Permissions**
- `GET /roles` — list all roles with their permission flags
- `GET /permissions?layer_id=&database_id=&group_layer_id=` — list ACL entries
- `POST /permissions` — grant permission (requires manage_perms on target or superadmin)
- `DELETE /permissions/{id}` — revoke permission

**Users**
- `GET /users?is_active=` — list users (superadmin only)
- `GET /users/me` — current user
- `GET /users/{id}` — get one (superadmin or self)
- `POST /users/{id}/activate` — reactivate a user (superadmin)
- `POST /users/{id}/deactivate` — deactivate a user (superadmin)
- `POST /users/{id}/make-superadmin` — grant superadmin (superadmin)

**Groups**
- `GET /groups` — list all MS Entra groups
- `GET /groups/{id}` — get one group

**Rasters**
- `GET /rasters?database_id=` — list raster catalog entries
- `POST /rasters` — register a raster (superadmin)
- `GET /rasters/{id}` — get one
- `PUT /rasters/{id}` — update metadata (superadmin)
- `DELETE /rasters/{id}` — remove from catalog (superadmin)

**Sync** (for Argo offline app)
- `POST /sync/snapshot` — download all features for given layer IDs, records snapshot timestamp
- `GET /sync/delta/{layer_id}?device_id=` — get features changed since last snapshot
- `POST /sync/push` — push edits from device, returns succeeded/conflicts/failed per edit
- `GET /sync/status/{layer_id}?device_id=` — snapshot age, expiry, pending conflicts

### Web app — scaffold running, not wired to API

Start: `cd geo-platform/web && npm run dev`
URL: http://localhost:5173

Pages exist as scaffolds (UI shell, no real data):
- `DatabasesPage.tsx` — list databases
- `LayersPage.tsx` — list layers per database
- `LayerDetailPage.tsx` — layer detail + feature map
- `PermissionsPage.tsx` — manage permissions
- `UsersPage.tsx` — user management
- `GroupsPage.tsx` — group list
- `AuditLogPage.tsx` — audit trail
- `SyncConflictsPage.tsx` — conflict resolution

Components exist as scaffolds:
- `AppLayout.tsx`, `TopBar.tsx`, `Sidebar.tsx` — shell layout
- `LayerTree.tsx`, `LayerForm.tsx`, `LockButton.tsx` — layer management
- `PermissionForm.tsx`, `PermissionMatrix.tsx` — permissions UI
- `AuthProvider.tsx` — MSAL wrapper (scaffold only, not wired)

---

## Next: Phase 5

See `docs/04_next_session_prompt.md`.

**Blocker before starting:** Need real Microsoft Entra credentials in `api/.env`:
```
MS_TENANT_ID=<your-tenant-id>
MS_CLIENT_ID=<your-client-id>
MS_CLIENT_SECRET=<your-client-secret>
```
