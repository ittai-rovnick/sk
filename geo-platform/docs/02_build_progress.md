# Geo Platform — Build Progress

Last updated: 2026-04-17

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
| 12 | All API endpoints implemented | ✅ Done |
| 13 | Auth replaced (local JWT + OS auto-login), web wired to API | ✅ Done |
| 13a | Custom groups architecture (generic, not MS-only) | ✅ Done |
| 13b | Map page with MapLibre + terra-draw editing | ✅ Done |
| 13c | Multi-geometry layers (dynamic `geometry_types` array) | ✅ Done |
| 13d | Schema editor + attribute table with inline editing | ✅ Done |
| 13e | Resizable bottom panel + tabbed multi-table (ArcGIS Pro style) | ✅ Done |
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

**geo_meta** (21 tables):

| Table | Key columns | Notes |
|-------|-------------|-------|
| `users` | id, ms_object_id (nullable), email, is_superadmin, is_active | ms_object_id nullable for local-auth users |
| `ms_groups` | id, ms_group_id, display_name, is_custom, synced_at | Custom groups have `ms_group_id = "custom:{uuid}"` |
| `custom_group_members` | group_id, user_id | Manual user → custom group membership |
| `custom_group_ms_links` | custom_group_id, ms_group_id, ms_display_name | Links custom group to real MS Entra group IDs |
| `geo_databases` | id, name, default_srid, tags | Top-level containers |
| `group_layers` | id, database_id, parent_id, name, sort_order, deleted_at | Folder tree |
| `layers` | id, database_id, group_layer_id, name, **geometry_types** (TEXT[]), srid, status, is_locked, shard_id, deleted_at | Vector layer metadata — geometry_types auto-derived from features |
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

Migrations applied:
- `001_initial.py` — full schema
- `002_custom_groups.py` — adds `is_custom` to ms_groups, creates custom_group_members
- `003_custom_group_ms_links.py` — creates custom_group_ms_links
- `004_local_auth.py` — makes ms_object_id nullable
- `005_group_hierarchy.py` — adds `parent_id` to `ms_groups` for nested custom groups
- `006_layers_geometry_types.py` — replaces `geometry_type TEXT` with `geometry_types TEXT[]` (auto-derived, CHECK constraint, GIN index)

**geo_features** — partitioned features table:
- `features` partitioned `BY HASH(layer_id)` into 32 partitions: `features_p0` … `features_p31`
- Columns: `id` (bigserial PK), `layer_id` (uuid), `geom` (PostGIS Geometry), `properties` (JSONB), `version` (int), `created_by`, `updated_by`, `deleted_at`, `created_at`, `updated_at`

Run migrations:
```powershell
cd geo-platform/api
venv\Scripts\alembic -x db=meta upgrade meta@head
venv\Scripts\alembic -x db=features upgrade features@head
```

### API — all endpoints implemented

Start: `cd geo-platform/api && venv\Scripts\python run.py`
Swagger UI: http://localhost:8000/docs

**Auth** (local JWT — no Microsoft required)
- `POST /auth/login` — `{username: email}` → `{token, user}`. In DEV_MODE any email creates a user.
- `GET /auth/auto-login` — reads OS `%USERNAME%`, auto-creates as superadmin in DEV_MODE if not found.
- `GET /auth/me` — returns current user from JWT

**Databases**
- `GET /databases`, `POST /databases`, `GET /databases/{id}`, `PUT /databases/{id}`, `DELETE /databases/{id}`

**Group Layers** (folder tree)
- `GET /group-layers?database_id=`, `POST /group-layers`, `GET /group-layers/{id}`, `PUT /group-layers/{id}`, `DELETE /group-layers/{id}`

**Layers**
- `GET /layers?database_id=&group_layer_id=`, `POST /layers`, `GET /layers/{id}`, `PUT /layers/{id}`, `DELETE /layers/{id}`
- `POST /layers/{id}/lock`, `DELETE /layers/{id}/lock`
- `GET /layers/{id}/schema`, `PUT /layers/{id}/schema`
- `POST /layers/{id}/lyrx`

**Features**
- `GET /layers/{id}/features?min_lon=&min_lat=&max_lon=&max_lat=&geometry_type=&limit=&offset=` — now supports `geometry_type` filter (e.g. `?geometry_type=POINT`)
- `POST /layers/{id}/features`, `GET /layers/{id}/features/{fid}`, `PUT /layers/{id}/features/{fid}`, `DELETE /layers/{id}/features/{fid}`
- `POST /layers/{id}/features/bulk-delete` — batch soft-delete by feature ID list

**Symbology**
- `GET/POST/PUT/DELETE /layers/{id}/styles/{sid}`, `POST /layers/{id}/styles/{sid}/lyrx`, `GET /layers/{id}/styles/{sid}/lyrx`

**Permissions**
- `GET /roles`, `GET /permissions`, `POST /permissions`, `DELETE /permissions/{id}`

**Users**
- `GET /users`, `GET /users/me`, `GET /users/{id}`, `POST /users/{id}/activate`, `POST /users/{id}/deactivate`, `POST /users/{id}/make-superadmin`

**Groups** (custom groups, not MS-only)
- `GET /groups` — list custom groups (`is_custom=True`)
- `POST /groups` — create a custom group
- `GET /groups/{id}`, `PUT /groups/{id}`, `DELETE /groups/{id}`
- `GET /groups/{id}/members`, `POST /groups/{id}/members`, `DELETE /groups/{id}/members/{user_id}`
- `GET /groups/{id}/ms-links`, `POST /groups/{id}/ms-links`, `DELETE /groups/{id}/ms-links/{ms_group_id}`
- `GET /groups/ms/search?q=` — search MS Entra groups (returns which custom groups each is already linked to)

**Rasters**
- `GET /rasters?database_id=`, `POST /rasters`, `GET /rasters/{id}`, `PUT /rasters/{id}`, `DELETE /rasters/{id}`

**Sync** (for Argo offline app)
- `POST /sync/snapshot` — now accepts optional `geometry_type` filter
- `GET /sync/delta/{layer_id}?device_id=&geometry_type=` — now supports `geometry_type` filter
- `POST /sync/push` — auto-refreshes `geometry_types` after edits
- `GET /sync/status/{layer_id}?device_id=`
- `GET /sync/conflicts`, `PATCH /sync/conflicts/{id}`

### Web app — fully wired to API

Start: `cd geo-platform/web && npm run dev`
URL: http://localhost:5173

**Auth flow:**
1. App opens → `LoginPage` fires `GET /auth/auto-login`
2. API reads OS `%USERNAME%`, finds/creates user, returns JWT
3. Token stored in `localStorage` as `geo_token`; user stored as `geo_user`
4. All subsequent requests attach `Authorization: Bearer <token>` automatically
5. Falls back to manual email form if auto-login returns 404

**Working pages:**

| Page | Route | What it does |
|------|-------|-------------|
| LoginPage | `/login` | OS auto-login → manual fallback |
| DatabasesPage | `/databases` | List databases, create new (superadmin) |
| LayersPage | `/layers` | List layers by database, create/edit/delete |
| LayerDetailPage | `/layers/:id` | Layer info + feature count |
| PermissionsPage | `/permissions` | ACL table for selected layer |
| UsersPage | `/users` | User list, activate/deactivate (superadmin) |
| GroupsPage | `/groups` | Custom group list, member management |
| AuditLogPage | `/audit` | Read-only audit trail |
| SyncConflictsPage | `/conflicts` | List pending sync conflicts, server/client wins |
| **MapPage** | `/map` | **See below** |

**MapPage (`/map`):**
- Left panel (260 px): database selector → layer list with:
  - Colored dot (auto-assigned by index)
  - Geometry types tags (multi-geometry: Point / LineString / Polygon / etc.)
  - Eye toggle to show/hide layer on map
  - Edit button — loads features from API, activates terra-draw editing
  - Table button — opens attribute table tab at bottom
  - Gear button — opens schema editor modal
  - Draw mode toolbar: Select / Point / Line / Polygon buttons
  - Save button — diffs terra-draw snapshot vs original, batch creates/updates/deletes via API; auto-refreshes `geometry_types` from server
  - "+ New Layer" button — modal to create a new layer (name only, geometry types auto-derived)
- Map: MapLibre GL JS with OSM base tiles (no API key needed)
- Drawing: `terra-draw` with `TerraDrawMapLibreGLAdapter` (MapLibre-native, not mapbox-gl-draw)
- Feature tracking: `_api_id` and `_api_version` stored in feature properties for diff/save
- **Bottom panel — tabbed attribute tables (ArcGIS Pro style):**
  - Drag handle for vertical resize (min 120px, max 70% viewport)
  - Tab strip: one tab per opened layer, click to switch, X to close
  - All open tables stay mounted (`display: none` for inactive) — preserves loaded data and scroll position
  - Each table: row count, Refresh button, bulk Delete button, Ant Design Table with inline editable cells
  - Inline editing: type-specific inputs (text → Input, number → InputNumber, boolean → Switch, date → DatePicker), clear button to null values
  - Schema editor modal: define fields (name, type, required), auto-refreshes open tables on save

**Key tech decisions:**
- No MSAL / Microsoft auth — local HS256 JWT only
- No React Query — plain axios with Bearer token interceptor
- `terra-draw` (not `@mapbox/mapbox-gl-draw`) — mapbox lib is incompatible with maplibre at runtime
- Custom groups are the primary permission entity; MS group IDs are optional linked sources
- `geometry_types` are auto-derived from features (no user declaration step); `layer_geometry.py` service refreshes after every feature mutation

---

## Next: Phase 14 — Tests

See `docs/04_next_session_prompt.md`.
