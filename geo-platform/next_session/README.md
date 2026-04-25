# Next Session — Geo-Platform Implementation Handoff

This folder exists so any developer can `git pull` and continue implementation without needing the original Claude conversation.

---

## What is being built

9 new capabilities on top of the existing geo-platform:

1. **Map objects with layer groups** — hierarchical, ordered layer organization inside maps
2. **Layer bounding box** — auto-maintained extent after every feature mutation
3. **Advanced feature queries** — spatial predicates + attribute filters (injection-safe DSL)
4. **Export formats** — GeoJSON, Shapefile, GeoPackage
5. **CRS / reprojection** — `?srid=` on features + export endpoints
6. **Attribute statistics** — per-field stats endpoint with Redis TTL cache
7. **Geometry simplification** — `?zoom=` param applies `ST_SimplifyPreserveTopology`
8. **Version history** — full snapshots (not diffs), race-condition-free counter
9. **Identify layers by polygon** — draw a polygon, see which layers have features inside it

---

## How to start the system

```powershell
# 1 — Docker (must be up first)
cd c:\Itay\sk\geo-platform
docker compose up -d

# 2 — API
cd c:\Itay\sk\geo-platform\api
venv\Scripts\python run.py
# Verify: http://localhost:8000/health → {"status":"ok","db":"ok"}
# Swagger: http://localhost:8000/docs

# 3 — Web
cd c:\Itay\sk\geo-platform\web
npm run dev
# Open: http://localhost:5173
```

---

## How to run migrations

Always run both branches. Run `meta` first (it has FKs that features branch doesn't depend on):

```powershell
cd geo-platform\api

# Meta branch (maps, versions, change tracking, expressions)
venv\Scripts\alembic -x db=meta upgrade meta@head

# Features branch (partition indexes)
venv\Scripts\alembic -x db=features upgrade features@head
```

New migrations added (not yet run):
- `007_maps_and_map_groups.py` — meta branch
- `008_resource_versions.py` — meta branch
- `009_change_tracking.py` — meta branch
- `010_saved_expressions.py` — meta branch
- `002f_feature_stats_indexes.py` — features branch

---

## How to continue

Read the files in this folder in order:

1. **`01_done.md`** — what's already implemented (do not redo)
2. **`02_todo.md`** — what still needs to be implemented (start here)
3. **`03_architecture.md`** — design decisions and rules to follow

Then read `geo-platform/CLAUDE.md` for the full project context (tech stack, critical rules, existing endpoints).

The master implementation plan is at `geo-platform/in-the-map-object-rustling-planet.md` — it has the full SQL, API design, and step-by-step order with dependency graph.

---

## Key files to read before making changes

| File | Purpose |
|------|---------|
| `api/app/main.py` | FastAPI app + router registrations + lifespan |
| `api/app/dependencies.py` | `get_meta_db`, `get_current_user` — used everywhere |
| `api/app/auth/permissions.py` | `can_user_do()` — call this before every mutation |
| `api/app/db/session.py` | `MetaSessionLocal`, `shard_sessions` dict |
| `api/app/routers/features.py` | Pattern for shard_sessions + fire-and-forget service calls |
| `api/app/services/layer_geometry.py` | Fire-and-forget pattern to copy for new services |
| `api/app/services/feature_filter.py` | Injection-safe DSL compiler — read before touching filters |
| `api/app/cache.py` | Redis helpers — use these, don't import redis directly |
| `web/src/types/index.ts` | All TypeScript interfaces |
| `web/src/pages/MapPage.tsx` | Main map page — being refactored |
