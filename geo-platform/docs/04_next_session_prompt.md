# Next Session Prompt — Geo Platform

Paste this entire file into Claude at the start of the next session.

---

## What you are working on

**Geo Platform** — a full-stack geographic data management platform.
- Repo: `c:/git/sk`, branch `develop`
- Project root: `geo-platform/`
- Full docs: `geo-platform/docs/`

## What is already done (do not redo any of this)

### Infrastructure — fully working
- Docker: 5 containers running (postgres_meta :5432, postgres_features :5433, pgbouncer :6432, redis :6379, minio :9000)
- Both databases migrated: geo_meta has 21 tables (including custom groups + MS links), geo_features has 32-partition features table

### Auth — local JWT, no Microsoft required
- `POST /auth/login` — `{username: email}` → `{token, user}`
- `GET /auth/auto-login` — reads OS `%USERNAME%` environment variable, auto-creates user as superadmin in DEV_MODE
- No MSAL, no Azure credentials needed
- Web: `LoginPage` tries auto-login on mount, falls back to email form; token stored in localStorage

### API — all endpoints implemented
- `GET /health` — liveness check
- Full CRUD: `/databases`, `/group-layers`, `/layers`, `/rasters`
- Features: `GET/POST/PUT/DELETE /layers/{id}/features/{fid}` with bbox filter + optimistic locking
- Permissions: `/roles`, `/permissions`
- Users: `/users`, `/users/me`, activate/deactivate/make-superadmin
- Groups: custom groups CRUD + member management + MS group links
- Sync (for Argo): `/sync/snapshot`, `/sync/delta`, `/sync/push`, `/sync/status`, `/sync/conflicts`
- Auth: `/auth/login`, `/auth/auto-login`, `/auth/me`

### Web — fully wired, 10 working pages
- Login (OS auto-login)
- Databases (list + create)
- Layers (list + create/edit/delete)
- Layer Detail
- Permissions (ACL per layer)
- Users (list + activate/deactivate)
- Groups (custom groups + members)
- Audit Log
- Sync Conflicts (resolve server/client wins)
- **Map page** at `/map`:
  - Left panel: database selector → layer list with geometry type, color dot, visibility toggle, edit button
  - Drawing: `terra-draw` with `TerraDrawMapLibreGLAdapter` (NOT mapbox-gl-draw)
  - Modes: Select / Point / LineString / Polygon
  - Save: diffs terra-draw snapshot vs original features → batch API create/update/delete
  - Create new layer via modal

### Key tech stack
- API: FastAPI + SQLAlchemy 2.0 async + psycopg3 + Alembic (on Python 3.13)
- Web: React 18 + Vite + Ant Design + React Router v6 + plain axios (no React Query)
- Map: MapLibre GL JS + terra-draw
- Auth: local HS256 JWT, OS username auto-login in DEV_MODE

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
# Verify: http://localhost:8000/docs

# Terminal 3 — Web
cd c:\git\sk\geo-platform\web
npm run dev
# Open: http://localhost:5173
```

---

## What to build next: Phase 14 — Tests

### API tests (pytest)
```
geo-platform/api/tests/
  test_auth.py        — auto-login, manual login, bad token
  test_databases.py   — CRUD, permission enforcement
  test_layers.py      — CRUD, lock/unlock, schema
  test_features.py    — CRUD, optimistic locking (version conflict → 409), bbox filter
  test_sync.py        — snapshot, delta, push with conflict detection
  test_permissions.py — grant/revoke, can_user_do() enforcement
  test_groups.py      — custom groups CRUD, members, MS links
```

Use `pytest-asyncio` + test database (separate `geo_meta_test` + `geo_features_test` databases).
Set `DEV_MODE=true` in test env so auto-login creates test users.

### Web tests (Vitest + Playwright)
- Vitest for unit tests on utility functions
- Playwright E2E: login flow, create database, create layer, draw a point, save

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
| Use terra-draw, NOT @mapbox/mapbox-gl-draw | mapbox-gl-draw is incompatible with MapLibre at runtime (internal event system mismatch) |
| No React Query | Plain axios + useEffect/useState. User explicitly rejected React Query. |
| ms_object_id is nullable | Auto-created local users have no MS object ID |

---

## Key files to read before making changes

| File | What it does |
|------|-------------|
| `api/app/main.py` | FastAPI app setup, all router registrations |
| `api/app/config.py` | All settings read from .env |
| `api/app/dependencies.py` | `get_meta_db`, `get_current_user` — used by every authenticated endpoint |
| `api/app/auth/local.py` | Local JWT auth — `create_token`, `validate_token`, `resolve_custom_group_ids` |
| `api/app/auth/permissions.py` | `can_user_do()` — calls the PostgreSQL permission function |
| `api/app/db/session.py` | `MetaSessionLocal`, `shard_sessions` — engine and session factories |
| `api/app/routers/features.py` | Shows how to query geo_features DB via `shard_sessions` |
| `api/app/routers/sync.py` | Full sync flow: snapshot, delta, push with conflict detection |
| `web/src/App.tsx` | React Router route definitions |
| `web/src/auth/AuthContext.tsx` | React auth context — token + user in localStorage |
| `web/src/api/client.ts` | Axios instance with Bearer token interceptor |
| `web/src/pages/MapPage.tsx` | Full map + terra-draw editing page |

---

## Docs in this repo

- `docs/01_project_overview.md` — full architecture, database schema, permission model, sync model
- `docs/02_build_progress.md` — detailed phase tracker, all tables, all endpoints, all web pages
- `docs/03_gotchas_and_fixes.md` — every problem hit during build and how it was fixed
- `docs/04_next_session_prompt.md` — this file
