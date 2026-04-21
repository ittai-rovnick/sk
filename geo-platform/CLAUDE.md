# Geo Platform — Claude Context

This file is auto-loaded by Claude Code at session start. Read it before touching any code.

---

## What this is

**Geo Platform** — a full-stack geographic data management system serving three clients simultaneously:
- **ArcGIS Pro** — desktop GIS authoring via REST API (read/write layers and features)
- **Esri Portal** — web GIS viewer (reads layers, features, signed URLs for rasters/styles)
- **Argo** — offline-capable .NET field app (sync: snapshot → delta → push with conflict detection)

**Repo:** `c:/Itay/sk/`, branch `develop`
**Project root:** `geo-platform/`
**API:** `geo-platform/api/` — FastAPI, Python 3.13, port 8000
**Web:** `geo-platform/web/` — React 18 + Vite, port 5173
**Docs:** `geo-platform/docs/`

---

## How to start

```powershell
# 1 — Docker (must be up before API)
cd c:\Itay\sk\geo-platform
docker compose up -d

# 2 — API
cd c:\Itay\sk\geo-platform\api
venv\Scripts\python run.py
# Verify: http://localhost:8000/health  →  {"status":"ok","db":"ok"}
# Swagger: http://localhost:8000/docs

# 3 — Web
cd c:\Itay\sk\geo-platform\web
npm run dev
# Open: http://localhost:5173
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Clients: ArcGIS Pro | Esri Portal | Argo (.NET) │
└────────────────────┬────────────────────────────┘
                     │
               FastAPI REST API  :8000
                     │
      ┌──────────────┼──────────────────┐
      │              │                  │
 pgbouncer        geo_features        MinIO
 :6432→:5432         :5433          :9000/:9001
      │                           (lyrx, COG rasters,
 geo_meta                          exports — boto3 via
 :5432                             asyncio.to_thread)
 (21 tables)
      │
   Redis :6379
 (auth cache / group membership)
```

### Stack

| Layer | Tech | Notes |
|-------|------|-------|
| API | FastAPI + SQLAlchemy 2.0 async + psycopg3 3.2.13 | async only, SelectorEventLoop on Windows |
| DB meta | PostgreSQL 16 + PostGIS 3.4 | geo_meta — 21 tables, via pgbouncer |
| DB features | PostgreSQL 16 + PostGIS 3.4 | geo_features — 32-partition features table |
| Storage | MinIO (S3-compatible) | boto3 wrapped in asyncio.to_thread |
| Cache | Redis 7 | group membership caching |
| Web | React 18 + Vite + Ant Design + React Router v6 | plain axios, no React Query |
| Map | MapLibre GL JS + terra-draw | TerraDrawMapLibreGLAdapter |
| Auth | Local HS256 JWT, 30-day expiry | OS %USERNAME% auto-login in DEV_MODE |

---

## What is built (do not redo)

### Infrastructure
- 5 Docker containers: postgres_meta :5432, postgres_features :5433, pgbouncer :6432, redis :6379, minio :9000/:9001
- Both databases migrated (6 Alembic revisions across meta + features branches)
- MinIO buckets auto-created on API startup: `geo-styles`, `geo-rasters`, `geo-exports`

### Auth
- `POST /auth/login` — `{username: email}` → `{token, user}` (HS256 JWT, 30-day)
- `GET /auth/auto-login` — reads OS `%USERNAME%`, auto-creates user as superadmin in DEV_MODE
- `GET /auth/me` — current user from token
- No MSAL, no Azure credentials needed in development
- `DEV_MODE=true` → all requests use a fixed dev superadmin context (no token required)
- Token carries: `sub` (user UUID), `email`, `is_superadmin`, `exp`
- Custom group membership resolved via recursive CTE (child→ancestor, depth ≤ 16)

### API endpoints (all implemented)

| Router | Prefix | Key endpoints |
|--------|--------|---------------|
| health | `/health` | GET — liveness + DB check |
| auth | `/auth` | POST /login, GET /auto-login, GET /me |
| databases | `/databases` | Full CRUD |
| group-layers | `/group-layers` | Full CRUD — hierarchical layer folders (superadmin only) |
| layers | `/layers` | Full CRUD + GET/PUT schema + POST/DELETE lock + POST lyrx upload |
| features | `/layers/{id}/features` | GET (bbox + geom_type filter, pagination) + POST + GET/{fid} + PUT + DELETE + POST /bulk-delete |
| permissions | `/permissions` | Full CRUD — grant/revoke roles on database/group/layer |
| roles | `/roles` | Full CRUD — system + custom roles |
| symbology | `/layers/{id}/styles` | Full CRUD + POST/GET lyrx (ArcGIS .lyrx style files) |
| users | `/users` | List + GET /me + GET/{id} + POST activate/deactivate/make-superadmin |
| groups | `/groups` | Custom group CRUD + member management + MS group links + group tree + move |
| rasters | `/rasters` | Full CRUD — COG raster catalog |
| sync | `/sync` | POST /snapshot, GET /delta, POST /push (conflict detection), GET /status, GET /conflicts, POST /conflicts/{id}/resolve |

### Permission model
- Roles have 7 boolean flags: `can_read`, `can_write`, `can_delete`, `can_export`, `can_manage_style`, `can_manage_perms`, `can_publish`
- Permissions attach a role to: a user (`ms_user_id`), a group (`ms_group_id`), at scope: database / group-layer / layer
- `can_user_do(db, ctx, layer_id, operation)` calls a PostgreSQL function — superadmins bypass all checks
- Permissions support `allow=false` for explicit deny rules

### Web — 10 pages (all wired)

| Route | Page | Notes |
|-------|------|-------|
| `/login` | LoginPage | OS auto-login on mount, falls back to email form |
| `/databases` | DatabasesPage | List + create |
| `/layers` | LayersPage | List + create/edit/delete, lock status shown |
| `/layers/:id` | LayerDetailPage | Schema editor (SchemaEditor component), layer metadata |
| `/permissions` | PermissionsPage | PermissionMatrix + PermissionForm |
| `/users` | UsersPage | Activate/deactivate/make-superadmin |
| `/groups` | GroupsPage | Custom groups + member management + MS group links |
| `/audit` | AuditLogPage | Audit log viewer |
| `/conflicts` | SyncConflictsPage | Sync conflict resolution (server/client wins) |
| `/map` | MapPage | Full map editor (see below) |

### Web — Map page (`web/src/pages/MapPage.tsx`)
- Left panel: database selector → layer list (geometry type icon, color dot, visibility toggle, edit button)
- Drawing toolbar: Select / Point / LineString / Polygon modes
- Library: `terra-draw` + `TerraDrawMapLibreGLAdapter` (NOT mapbox-gl-draw — incompatible with MapLibre)
- Save: diffs terra-draw snapshot vs original API features → batch create/update/delete
- Layer schema editor panel (opens inline on map)
- AttributeTable component (`web/src/components/layers/AttributeTable.tsx`) — inline data table with edit support

### Web — Components
- `AttributeTable` — paginated feature table, inline editing, delete, reload
- `LayerForm` — create/edit layer modal
- `LayerTree` — hierarchical group-layer tree
- `LockButton` — lock/unlock with reason
- `SchemaEditor` — JSON-schema field editor (string/number/boolean/date)
- `PermissionMatrix` / `PermissionForm` — ACL management UI
- `AppLayout` / `Sidebar` / `TopBar` — shell layout
- `ErrorBoundary` / `LoadingSpinner` — shared utilities

### Web — API layer (`web/src/api/`)
- `client.ts` — axios instance with Bearer token interceptor
- `auth.ts`, `databases.ts`, `features.ts`, `groups.ts`, `layers.ts`, `permissions.ts`, `users.ts`
- Types in `web/src/types/index.ts` — shared TypeScript interfaces

### Services (API)
- `audit_service.py` — fire-and-forget audit log writer (errors never propagate to caller)
- `feature_service.py` — feature CRUD helpers
- `layer_geometry.py` — `refresh_layer_geometry_types()` — recomputes `layers.geometry_types` after every feature mutation
- `layer_service.py` — layer business logic
- `permission_service.py` — `can_user_do` wrapper
- `storage_service.py` — boto3 MinIO wrapper (`upload_lyrx`, `get_signed_url`, `ensure_buckets_exist`)
- `symbology_service.py` — style management
- `sync_service.py` — snapshot/delta/push logic

### Tests (partial — Phase 14 in progress)
Location: `api/app/tests/`  
Done: `test_auth.py`, `test_features.py`, `test_layers.py`, `test_permissions.py`  
Pending: `test_databases.py`, `test_sync.py`, `test_groups.py`, web tests (Vitest + Playwright)  
Uses `pytest-asyncio` + separate test databases (`geo_meta_test`, `geo_features_test`).

---

## Key files — read these before making changes

| File | Purpose |
|------|---------|
| `api/app/main.py` | FastAPI app, all 13 router registrations, MinIO lifespan |
| `api/app/config.py` | All settings from `.env` |
| `api/app/dependencies.py` | `get_meta_db`, `get_current_user` — used by every authenticated endpoint |
| `api/app/auth/local.py` | JWT create/validate, `_resolve_custom_group_ids` recursive CTE |
| `api/app/auth/permissions.py` | `can_user_do()` → calls PostgreSQL function |
| `api/app/db/session.py` | `MetaSessionLocal`, `shard_sessions` dict — engine factories |
| `api/app/models/` | SQLAlchemy models — one file per domain |
| `api/app/routers/features.py` | Pattern for shard_sessions usage + optimistic locking |
| `api/app/routers/sync.py` | Full sync flow reference |
| `api/app/services/storage_service.py` | boto3 in asyncio.to_thread pattern |
| `web/src/App.tsx` | React Router route definitions |
| `web/src/auth/AuthContext.tsx` | Token + user in localStorage |
| `web/src/api/client.ts` | Axios instance with Bearer interceptor |
| `web/src/types/index.ts` | All shared TypeScript types |
| `web/src/pages/MapPage.tsx` | Map + terra-draw, layer loading, save diff logic |

---

## Alembic migrations

Two independent migration branches. Always run them separately:

```powershell
cd geo-platform/api
venv\Scripts\alembic -x db=meta upgrade meta@head
venv\Scripts\alembic -x db=features upgrade features@head
```

Migration files in `api/alembic/versions/`:
- `001_initial_schema.py` (meta branch) — core 21-table schema
- `001_features_schema.py` (features branch) — 32-partition features table
- `002_custom_groups.py` — custom group management
- `003_custom_group_ms_links.py` — MS Entra group links
- `004_local_auth.py` — local JWT auth fields
- `005_group_hierarchy.py` — parent_group_id + recursive permission inheritance
- `006_layers_geometry_types.py` — geometry_types column auto-refresh

---

## Critical Windows rules — never change these

| Rule | Why |
|------|-----|
| `run.py` uses `reload=False` | reload=True on Windows causes stale `.pyc` — routes disappear from /docs |
| `run.py` + `main.py` + `alembic/env.py` set `WindowsSelectorEventLoopPolicy` | psycopg3 async requires SelectorEventLoop; Windows defaults to ProactorEventLoop |
| pgbouncer docker-compose has `PGBOUNCER_DATABASE: geo_meta` | Without it, bitnami pgbouncer doesn't expose geo_meta as a routable DB name |
| Use `py` not `python` in bare terminal | `python` resolves to Python 2.7; `py` invokes Python 3.13 via Windows Launcher |
| Inside venv: `venv\Scripts\python` is fine | venv's python is always 3.13 |
| PowerShell env vars: `$env:VAR = "value"` | `set VAR=value` sets a PS variable, not an env var — won't reach the process |
| pydantic-settings list fields in `.env`: `API_CORS_ORIGINS=["http://..."]` | Must be JSON array, not plain string |

---

## Critical architectural rules — never break these

| Rule | Why |
|------|-----|
| Routers: HTTP only, no business logic | Services hold logic; mixing causes untestable spaghetti |
| All DB ops `async/await` | Sync calls block the event loop → timeouts under load |
| `boto3` calls in `asyncio.to_thread()` | boto3 is sync; calling it directly blocks the event loop |
| Write order: permission check → lock check → work → audit | Skipping permission = security hole; skipping lock = data corruption |
| Soft deletes: `deleted_at = now()` | ArcGIS Pro + Argo need deleted feature IDs for sync; hard delete breaks sync |
| Features UPDATE: `WHERE version = :expected_version` | 0 rows → 409 + record SyncConflict; this is the conflict detection mechanism |
| Geometry: `ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(...)), 4326)` | Other SRIDs break ArcGIS; invalid geometry causes PostGIS errors |
| Features queries: always include `layer_id` in WHERE | Without it Postgres scans all 32 partitions = full table scan |
| S3 keys stored in DB, not full URLs | MinIO URLs change on server move; keys are stable |
| Use `terra-draw` + `TerraDrawMapLibreGLAdapter`, never `@mapbox/mapbox-gl-draw` | mapbox-gl-draw is incompatible with MapLibre at runtime (internal event system conflict) |
| No React Query | Plain axios + useEffect/useState; user explicitly rejected React Query |
| `ms_object_id` is nullable on User | Auto-created local users have no MS object ID |
| `refresh_layer_geometry_types()` after every feature mutation | Keeps `layers.geometry_types` accurate for the map panel icon + ArcGIS clients |
| `audit_service.log()` is fire-and-forget | Errors are suppressed — audit failure must never crash the API |

---

## Git + branching conventions

- **Main development branch:** `develop`
- **Feature branches:** `feature/<short-description>` (e.g. `feature/export-endpoint`)
- **Bug fix branches:** `fix/<short-description>`
- **For every new feature or non-trivial change:** create a branch off `develop`, implement there, merge back via PR
- Keep commits atomic — one logical change per commit
- Commit messages: imperative mood, short subject line (`add export endpoint`, `fix sync conflict resolution`)

---

## Code quality standards

- **Routers are thin:** validate input, call service, return response — no SQL, no business logic
- **Services own logic:** all business rules, DB queries, and side effects go in `api/app/services/`
- **No inline SQL in routers** except features/sync where raw SQL is necessary for PostGIS + sharding
- **Schemas (Pydantic):** one `*Create`, `*Update`, `*Response` pattern per domain
- **Async everywhere:** every function that touches DB or external IO is `async def`
- **Type hints everywhere:** Python and TypeScript — no `Any` unless unavoidable
- **No magic numbers/strings:** constants in config or named variables
- **Frontend state:** component-local `useState`/`useEffect` + axios calls — no global state manager, no React Query
- **Error handling:** HTTP errors surface as `HTTPException` with clear `detail` messages; unexpected errors propagate to FastAPI's default 500 handler
- **Security:** `can_user_do()` called before every mutating operation on a layer; superadmin check for admin-only endpoints

---

## Workflow: completing a feature

Every time a feature is finished and ready to push:

1. **Work on a branch** — never commit directly to `develop`. Create a `feature/<name>` or `fix/<name>` branch first.
2. **Update CLAUDE.md** — add the completed feature to the "What is built" section, update the API endpoints table or web pages table as needed, add any new architectural rules discovered.
3. **Update `docs/02_build_progress.md`** — mark the phase/task done, add the new endpoints/pages/tables to the tracker.
4. **Update `docs/03_gotchas_and_fixes.md`** — if any non-obvious problem was hit and fixed during the feature, add it.
5. **Commit the doc updates** together with (or immediately after) the feature code.
6. **Merge back to `develop`** and push.

These steps are not optional — stale docs mean the next session starts with wrong context.

---

## Docs index

| File | Contents |
|------|---------|
| `docs/01_project_overview.md` | Full architecture, DB schema, permission model, sync protocol |
| `docs/02_build_progress.md` | Phase tracker, all tables, all endpoints, all web pages |
| `docs/03_gotchas_and_fixes.md` | Every non-obvious problem encountered and its fix |
| `docs/04_next_session_prompt.md` | Legacy session primer (superseded by this CLAUDE.md) |
