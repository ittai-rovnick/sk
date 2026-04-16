# Next Session Prompt — Geo Platform Phase 5

Paste this entire file into Claude at the start of the next session.

---

## Context

You are continuing the build of **Geo Platform** — a full-stack geographic data management
platform at `c:/git/sk/geo-platform/` on branch `develop`.

Repo: https://github.com/ittai-rovnick/sk.git

## What is already done

Everything through Phase 4 is complete and committed:
- Docker: all 5 containers running (postgres_meta :5432, postgres_features :5433, pgbouncer :6432, redis :6379, minio :9000)
- Database: geo_meta (19 tables) and geo_features (32-partition features table) — migrations already run
- API: 54 endpoints implemented and working at localhost:8000 (see docs/02_build_progress.md for full list)
- Web: React + Vite scaffold at localhost:5173 — pages scaffolded but NOT wired to API

## What to do next: Phase 5 — Wire web app to API

**First:** Ask the user for their Microsoft Entra credentials before writing any auth code:
- MS_TENANT_ID
- MS_CLIENT_ID
- MS_CLIENT_SECRET
These are placeholders in `api/.env`. Auth will not work without them.

### Phase 5 tasks in order

1. **MSAL auth in web**
   - Install `@azure/msal-browser` and `@azure/msal-react`
   - Configure MSAL with the tenant/client IDs
   - Login button → redirect to Microsoft login → handle callback
   - Store access token, attach as Bearer to all API calls

2. **API client**
   - Create `web/src/api/client.ts` — axios instance with Bearer interceptor
   - Create typed hooks per resource using React Query

3. **Working pages** (wire one at a time, test each)
   - Login page
   - Database list
   - Layer list + create/edit/delete
   - Feature map view — render features using Leaflet or MapLibre GL JS
   - Permissions management

4. **End-to-end test:** login → browse databases → browse layers → view features on map

## How to start the platform

```powershell
# 1. Docker
cd c:\git\sk\geo-platform
docker compose up -d

# 2. API
cd c:\git\sk\geo-platform\api
venv\Scripts\python run.py

# 3. Web
cd c:\git\sk\geo-platform\web
npm run dev
```

Verify:
- http://localhost:8000/health → {"status":"ok","db":"ok"}
- http://localhost:8000/docs → all 54 endpoints visible
- http://localhost:5173 → web app

## Critical rules — never break these

- `run.py` uses `reload=False` — do not change to True (causes stale module cache on Windows)
- `run.py` and `main.py` both set `asyncio.WindowsSelectorEventLoopPolicy` — required for psycopg3 on Windows
- pgbouncer has `PGBOUNCER_DATABASE: geo_meta` in docker-compose — do not remove
- Use `py` not `python` for any new terminal commands (python = Python 2.7 on this machine)
- In PowerShell: `$env:VAR = "value"` not `set VAR=value`

## Architectural rules — never break these

- Routers: HTTP only. Services: business logic. Models: DB schema. Never mix.
- All DB ops async/await. No sync blocking.
- Every write: check permission FIRST, check lock SECOND, do work THIRD.
- Soft deletes everywhere — never hard DELETE features/layers/group_layers.
- Optimistic locking on features: WHERE version = client_version → 0 rows = 409 conflict.
- Geometry always EPSG:4326. ST_MakeValid on every insert.
- Features table partitioned BY HASH(layer_id), 32 partitions — always include layer_id in queries.
- Store S3 keys in DB, generate signed URLs on demand.

## Docs in this repo

- `docs/01_project_overview.md` — stack, architecture diagram, rules
- `docs/02_build_progress.md` — what's done, what's next, full endpoint list
- `docs/03_gotchas_and_fixes.md` — every problem hit + fix (read before touching infra)
- `docs/04_next_session_prompt.md` — this file
- `COMMANDS.txt` — quick reference for start/stop commands and DB connection details
