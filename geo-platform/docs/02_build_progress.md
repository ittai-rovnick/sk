# Geo Platform — Build Progress

Last updated: 2026-04-16

## Build plan: 15 steps across phases

| Step | Description | Status |
|------|-------------|--------|
| 0 | Prerequisites verified | ✅ Done |
| 1 | Project folder structure | ✅ Done |
| 2 | Coding principles documented | ✅ Done |
| 3 | Technology stack locked | ✅ Done |
| 4 | docker-compose.yml | ✅ Done |
| 5 | .env, .env.example, .gitignore | ✅ Done |
| 6 | api/requirements.txt | ✅ Done |
| 7 | SQLAlchemy models (9 files) | ✅ Done |
| 8 | Pydantic schemas (6 files) | ✅ Done |
| 9 | Alembic migrations — run successfully | ✅ Done |
| 10 | Web scaffold (React + Vite) | ✅ Done |
| 11 | API starts, /health works (Phase 3) | ✅ Done |
| 12 | All 54 API endpoints implemented (Phase 4) | ✅ Done |
| 13 | Web app wired to API (Phase 5) | ⏳ Next |
| 14 | Tests | ⬜ Pending |
| 15 | Deployment | ⬜ Pending |

## What exists and works right now

### Docker (all 5 containers healthy)
- `postgres_meta` — PostgreSQL + PostGIS on port 5432
- `postgres_features` — PostgreSQL + PostGIS on port 5433
- `pgbouncer` — connection pooler on port 6432 → 5432
- `redis` — cache on port 6379
- `minio` — object storage on port 9000, console on 9001

### Database schema
- **geo_meta** — 19 tables: users, ms_groups, geo_databases, group_layers, layers, layer_owners, layer_schema, permissions, roles, layer_styles, raster_catalog, audit_log, layer_events, sync_snapshots, sync_conflicts, failed_syncs, group_quotas, and feature-related tables
- **geo_features** — partitioned features table with 32 hash partitions on layer_id

### API (54 endpoints at localhost:8000)
- `GET /health` — liveness check (no auth)
- `GET /auth/me` — get current user from JWT
- `GET/POST /databases`, `GET/PUT/DELETE /databases/{id}`
- `GET/POST /group-layers`, `GET/PUT/DELETE /group-layers/{id}`
- `GET/POST /layers`, `GET/PUT/DELETE /layers/{id}`
- `POST /layers/{id}/lock`, `DELETE /layers/{id}/lock`
- `GET/PUT /layers/{id}/schema`
- `POST /layers/{id}/lyrx`
- `GET/POST /layers/{id}/features`, `GET/PUT/DELETE /layers/{id}/features/{fid}`
- `GET/POST /layers/{id}/styles`, `GET/PUT/DELETE /layers/{id}/styles/{sid}`
- `POST /layers/{id}/styles/{sid}/lyrx`, `GET /layers/{id}/styles/{sid}/lyrx`
- `GET /roles`
- `GET/POST /permissions`, `DELETE /permissions/{id}`
- `GET /users`, `GET /users/me`, `GET /users/{id}`
- `POST /users/{id}/activate`, `POST /users/{id}/deactivate`, `POST /users/{id}/make-superadmin`
- `GET /groups`, `GET /groups/{id}`
- `GET/POST /rasters`, `GET/PUT/DELETE /rasters/{id}`
- `POST /sync/snapshot`, `GET /sync/delta/{layer_id}`, `POST /sync/push`, `GET /sync/status/{layer_id}`

### Web app (localhost:5173)
- React 18 + Vite scaffold installed and running
- Pages and components scaffolded but NOT yet wired to the API

## Next: Phase 5 — Wire web app to API

See `docs/04_next_session_prompt.md` for the full briefing.

**Blocker:** Microsoft Entra credentials needed before auth can be tested:
- `MS_TENANT_ID`
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
These are placeholders in `api/.env` — fill them in before starting Phase 5.
