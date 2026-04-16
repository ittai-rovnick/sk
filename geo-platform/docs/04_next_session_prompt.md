# Next Session Prompt — Geo Platform Phase 5

Paste this entire file into Claude at the start of the next session.

---

## What you are working on

**Geo Platform** — a full-stack geographic data management platform.
- Repo: https://github.com/ittai-rovnick/sk.git, branch `develop`
- Project root: `geo-platform/`
- Full docs: `geo-platform/docs/`

## What is already done (do not redo any of this)

### Infrastructure — fully working
- Docker: 5 containers running (postgres_meta :5432, postgres_features :5433, pgbouncer :6432, redis :6379, minio :9000)
- Both databases migrated: geo_meta has 19 tables, geo_features has 32-partition features table

### API — fully working (54 endpoints)
- `GET /health` — liveness check, no auth
- `GET /auth/me` — current user from JWT
- Full CRUD: `/databases`, `/group-layers`, `/layers`, `/rasters`, `/groups`, `/users`
- Layer extras: `/layers/{id}/lock`, `/layers/{id}/unlock`, `/layers/{id}/schema`, `/layers/{id}/lyrx`
- Features: `GET/POST/PUT/DELETE /layers/{id}/features/{fid}` with bbox filter and optimistic locking
- Symbology: `GET/POST/PUT/DELETE /layers/{id}/styles/{sid}` with .lyrx upload and signed URL download
- Permissions: `GET /roles`, `GET/POST /permissions`, `DELETE /permissions/{id}`
- Sync (for Argo offline app): `POST /sync/snapshot`, `GET /sync/delta/{id}`, `POST /sync/push`, `GET /sync/status/{id}`

### Web — scaffold only, NOT wired
- React 18 + Vite + Ant Design + React Router v6 running at localhost:5173
- Pages exist as shells: DatabasesPage, LayersPage, LayerDetailPage, PermissionsPage, UsersPage, GroupsPage, AuditLogPage, SyncConflictsPage
- Components exist as shells: AppLayout, TopBar, Sidebar, LayerTree, LayerForm, LockButton, PermissionForm, PermissionMatrix, AuthProvider

---

## What to build next: Phase 5 — Wire web app to API

### Step 0 — Get credentials (do this first, block until user provides)
Ask the user for their Microsoft Entra credentials. Do not write any auth code until you have them.
```
MS_TENANT_ID=?
MS_CLIENT_ID=?
MS_CLIENT_SECRET=?
```
Add to `api/.env` and the MSAL config in the web app.

### Step 1 — MSAL auth in web
- Install: `npm install @azure/msal-browser @azure/msal-react`
- Create `web/src/auth/msalConfig.ts` with the PublicClientApplication config
- Wire `AuthProvider.tsx` (scaffold exists) to actually wrap the app with MsalProvider
- Add login button to TopBar → triggers MSAL redirect login
- After login, acquire token silently for the API scope
- Store token, expose it via a `useAccessToken()` hook

### Step 2 — API client
- Create `web/src/api/client.ts` — axios instance with base URL `http://localhost:8000`
- Add request interceptor: attach `Authorization: Bearer <token>` to every request
- Add response interceptor: handle 401 (redirect to login), 403 (show permission error), 409 (conflict warning)

### Step 3 — React Query hooks (one file per resource)
Create `web/src/api/hooks/` with:
- `useDatabases.ts` — useQuery for list, useMutation for create/update/delete
- `useLayers.ts` — list, create, update, delete, lock, unlock, schema
- `useFeatures.ts` — list with bbox, create, update, delete
- `useStyles.ts` — list, create, update, delete, lyrx upload
- `usePermissions.ts` + `useRoles.ts`
- `useUsers.ts`, `useGroups.ts`, `useRasters.ts`

### Step 4 — Wire pages one by one (test each before moving on)

**DatabasesPage** — list databases in a table, create button (superadmin), click to navigate to layers

**LayersPage** — list layers for selected database, create layer form (geometry type, name, group),
edit, delete, lock/unlock buttons

**LayerDetailPage** — show layer info, feature map using **MapLibre GL JS** or **Leaflet**:
- Fetch features from `GET /layers/{id}/features` with bbox query as map pans/zooms
- Render as GeoJSON layer on the map
- Click feature → show properties panel

**PermissionsPage** — show ACL table for a layer, grant/revoke form with role selector

**UsersPage** — list users, activate/deactivate, make-superadmin (superadmin only)

**AuditLogPage** — read-only table of audit_log entries

**SyncConflictsPage** — list pending sync conflicts, allow resolution

---

## How to start the platform

```powershell
# Terminal 1 — Docker (must be running before API)
cd c:\git\sk\geo-platform
docker compose up -d

# Terminal 2 — API
cd c:\git\sk\geo-platform\api
venv\Scripts\python run.py
# Verify: http://localhost:8000/health → {"status":"ok","db":"ok"}
# Verify: http://localhost:8000/docs → shows all 54 endpoints

# Terminal 3 — Web
cd c:\git\sk\geo-platform\web
npm run dev
# Open: http://localhost:5173
```

---

## Critical Windows rules — do not change these

| Rule | Why |
|------|-----|
| `run.py` uses `reload=False` | reload=True on Windows causes stale module cache — routes disappear from /docs |
| `run.py` and `main.py` set `WindowsSelectorEventLoopPolicy` | psycopg3 async requires SelectorEventLoop, Windows defaults to ProactorEventLoop |
| docker-compose pgbouncer has `PGBOUNCER_DATABASE: geo_meta` | Without it, bitnami pgbouncer doesn't expose geo_meta as a routable database name |
| Use `py` not `python` in terminal commands | `python` resolves to Python 2.7 on this machine |
| In PowerShell: `$env:VAR = "value"` | `set VAR=value` sets a PS variable, not an env var |
| pydantic-settings list fields: `API_CORS_ORIGINS=["http://..."]` | Must be JSON array format in .env, not plain string |

## Critical architectural rules — do not break these

| Rule | Why |
|------|-----|
| Routers: HTTP only, no logic | Services hold business logic; mixing causes untestable spaghetti |
| All DB ops async/await | Sync calls block the event loop and cause timeouts under load |
| boto3 calls in `asyncio.to_thread()` | boto3 is synchronous; calling it directly blocks the event loop |
| Write order: permission → lock → work → audit | Skipping permission check = security hole; skipping lock = data corruption |
| Soft deletes: `deleted_at = now()` | ArcGIS Pro and Argo need deleted feature IDs for sync; hard delete breaks sync |
| Features: `WHERE version = client_version` | 0 rows = 409 + record SyncConflict; this is the entire conflict detection mechanism |
| Geometry: EPSG:4326 + ST_MakeValid | Other projections break ArcGIS clients; invalid geometry causes PostGIS errors |
| Features queries: always include `layer_id` | Without it Postgres scans all 32 partitions = full table scan |
| S3 keys in DB, not URLs | MinIO URLs change if you move servers; keys are stable |

---

## Key files to read before making changes

| File | What it does |
|------|-------------|
| `api/app/main.py` | FastAPI app setup, all router registrations |
| `api/app/config.py` | All settings read from .env |
| `api/app/dependencies.py` | `get_meta_db`, `get_current_user` — used by every authenticated endpoint |
| `api/app/auth/permissions.py` | `can_user_do()` — calls the PostgreSQL permission function |
| `api/app/db/session.py` | `MetaSessionLocal`, `shard_sessions` — engine and session factories |
| `api/app/routers/features.py` | Shows how to query geo_features DB via `shard_sessions` |
| `api/app/routers/sync.py` | Full sync flow: snapshot, delta, push with conflict detection |
| `web/src/App.tsx` | React Router route definitions |
| `web/src/auth/AuthProvider.tsx` | MSAL wrapper (scaffold — needs implementation) |

---

## Docs in this repo

- `docs/01_project_overview.md` — full architecture, database schema, permission model, sync model
- `docs/02_build_progress.md` — detailed phase tracker, all tables, all endpoints, all web pages
- `docs/03_gotchas_and_fixes.md` — every problem hit during build and how it was fixed
- `docs/04_next_session_prompt.md` — this file
- `COMMANDS.txt` — quick start/stop commands and DB connection details for TablePlus/DBeaver
