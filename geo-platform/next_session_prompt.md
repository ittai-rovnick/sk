# Next Session Prompt — Geo Platform

## What this project is
A full-stack geographic data management platform at `c:/git/sk/geo-platform/`.
Serves ArcGIS Pro, Esri Portal, and an offline .NET app called Argo.
Branch: `develop` on https://github.com/ittai-rovnick/sk.git

## Stack
- **API:** FastAPI + SQLAlchemy 2.0 async + psycopg3 + GeoAlchemy2, port 8000
- **DBs:** PostgreSQL 16 + PostGIS — `geo_meta` (port 5432), `geo_features` (port 5433)
- **Pooler:** pgbouncer port 6432 (in front of geo_meta)
- **Cache:** Redis port 6379
- **Storage:** MinIO port 9000 (S3-compatible), console port 9001
- **Web:** React 18 + TypeScript + Vite + Ant Design + MSAL, port 5173
- **Auth:** Microsoft Entra ID (JWT), groups cached in Redis

## What is already done
- All Docker infrastructure working (docker-compose.yml committed)
- Both PostgreSQL databases migrated (geo_meta: 19 tables, geo_features: 32-partition features table)
- All 54 API endpoints implemented and working:
  - /health, /auth/me
  - /databases, /group-layers, /layers (CRUD + lock + schema + lyrx)
  - /layers/{id}/features (CRUD + bbox query + optimistic locking)
  - /layers/{id}/styles (CRUD + lyrx upload/download)
  - /roles, /permissions (grant/revoke)
  - /users, /groups, /rasters
  - /sync (snapshot/delta/push/status for offline Argo app)
- Web scaffold installed and running (pages and components scaffolded but not wired to API)

## What to do next: Phase 5 — Wire web app to API

**Before starting:** Ask the user for their Microsoft Entra credentials:
- MS_TENANT_ID
- MS_CLIENT_ID
- MS_CLIENT_SECRET
These are placeholders in `api/.env` and `api/app/config.py`. Auth will not work without them.

### Phase 5 tasks in order
1. MSAL authentication in web (login button, token acquisition, store token)
2. Axios instance with Bearer token interceptor (`web/src/api/client.ts`)
3. React Query hooks for each resource (databases, layers, features)
4. Login page — redirect to MS login, handle callback
5. Database list page — fetch and display databases
6. Layer list page — fetch layers per database, create/edit/delete
7. Feature map view — display features on a map (Leaflet or MapLibre)
8. Permissions management page

## How to start the platform

```powershell
# 1. Start Docker
cd c:\git\sk\geo-platform
docker compose up -d

# 2. Start API (in a terminal from the api/ directory)
cd c:\git\sk\geo-platform\api
venv\Scripts\python run.py

# 3. Start Web (separate terminal)
cd c:\git\sk\geo-platform\web
npm run dev
```

Verify:
- http://localhost:8000/health → {"status":"ok","db":"ok"}
- http://localhost:8000/docs → Swagger UI with all 54 endpoints
- http://localhost:5173 → Web app

## Critical Windows gotchas (already fixed in code, do not revert)
- `run.py` has `reload=False` — reload=True on Windows causes stale module cache hiding routes
- `run.py` and `main.py` both set `asyncio.WindowsSelectorEventLoopPolicy` — psycopg3 async requires SelectorEventLoop
- pgbouncer docker-compose has `PGBOUNCER_DATABASE: geo_meta` — required for database routing
- Use `py` not `python` — `python` resolves to Python 2.7 on this machine
- In PowerShell use `$env:VAR = "value"` to set env vars, not `set VAR=value`

## Key architectural rules (never break these)
- Routers: HTTP only. Services: business logic. Models: DB structure. Never mix.
- All DB ops async/await. No sync blocking.
- Every write: check permission FIRST, check lock SECOND, do work THIRD.
- Soft deletes everywhere — never hard DELETE features/layers/group_layers.
- Optimistic locking on features: WHERE version = client_version → 0 rows = 409 conflict.
- Geometry always EPSG:4326. ST_MakeValid on every insert.
- Features table partitioned BY HASH(layer_id), 32 partitions — always include layer_id in queries.
- Store S3 keys in DB, generate signed URLs on demand.

## Memory files location
Auto-memory is saved at:
`C:\Users\Ittai\.claude\projects\c--git-sk\memory\`
- MEMORY.md — index
- project_geo_platform.md — stack and rules
- project_build_status.md — exact progress
- feedback_build_conventions.md — Windows-specific fixes and conventions
