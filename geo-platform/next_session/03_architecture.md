# Architecture & Design Decisions

Rules and patterns that must be followed throughout the implementation.

---

## Project Structure

```
geo-platform/
├── api/                         FastAPI backend (Python 3.13)
│   ├── app/
│   │   ├── main.py              App + all router registrations + lifespan
│   │   ├── config.py            All settings from .env
│   │   ├── dependencies.py      get_meta_db, get_current_user (used by every endpoint)
│   │   ├── cache.py             Redis helpers — always import from here
│   │   ├── auth/
│   │   │   ├── local.py         JWT create/validate + group resolution + Redis caching
│   │   │   └── permissions.py   can_user_do() → PostgreSQL function
│   │   ├── db/
│   │   │   └── session.py       MetaSessionLocal, shard_sessions dict
│   │   ├── models/              SQLAlchemy ORM — one file per domain
│   │   ├── schemas/             Pydantic — Create/Update/Response per domain
│   │   ├── routers/             FastAPI routers — HTTP only, no business logic
│   │   └── services/            All business logic, DB queries, side effects
│   └── alembic/
│       └── versions/            Migrations — meta branch (001-010) + features branch (001f, 002f)
└── web/                         React 18 + Vite frontend
    └── src/
        ├── api/                 Axios API modules (one per domain)
        ├── components/          Reusable React components
        ├── pages/               Page-level components (one per route)
        └── types/index.ts       All shared TypeScript interfaces
```

---

## Critical Rules (never break these)

### Backend

| Rule | Why |
|------|-----|
| Routers are thin — validate input, call service, return response | No SQL or business logic in routers |
| All DB ops `async/await` | Sync calls block the event loop |
| `boto3` calls in `asyncio.to_thread()` | boto3 is sync |
| `pyshp` and `fiona` calls in `asyncio.to_thread()` | Both are sync |
| `can_user_do()` before every mutating endpoint | Security — never skip this |
| Soft deletes: `deleted_at = now()` | ArcGIS Pro + Argo sync needs deleted feature IDs |
| `refresh_layer_geometry_types()` after every geom mutation | Keeps geometry_types accurate |
| `refresh_layer_feature_stamp()` after EVERY feature mutation | Unconditional — even property-only changes |
| `refresh_layer_bbox()` after every geom mutation | Keeps bbox accurate for map extent |
| Features queries always include `layer_id` in WHERE | Without it: full table scan across 32 partitions |
| Features shard DB: raw `text()` SQL only | No ORM in features DB — it's a partitioned table |
| `record_version()` in same transaction as the UPDATE it records | One commit for both — prevents version without matching state |

### Frontend

| Rule | Why |
|------|-----|
| Use `terra-draw` + `TerraDrawMapLibreGLAdapter` | `@mapbox/mapbox-gl-draw` incompatible with MapLibre at runtime |
| No React Query | User explicitly rejected it — plain axios + useEffect/useState |
| No global state manager | Same — component-local state only |

### Windows-specific

| Rule | Why |
|------|-----|
| `run.py` uses `reload=False` | reload=True on Windows causes stale .pyc — routes disappear |
| `WindowsSelectorEventLoopPolicy` set in run.py + main.py + alembic/env.py | psycopg3 async requires SelectorEventLoop |
| Use `py` not `python` in bare terminal | `python` resolves to Python 2.7 |

---

## Fire-and-Forget Pattern

Used for all side effects that should not block the API response or propagate errors:

```python
async def refresh_something(layer_id, ...) -> None:
    try:
        # do the work
        await db.commit()
    except Exception as exc:
        logger.warning("refresh_something failed for %s: %s", layer_id, exc)
        # NEVER re-raise — caller doesn't care if this fails
```

Call sites use `asyncio.create_task()` for cross-service calls (e.g., propagating feature changes to maps):
```python
asyncio.create_task(refresh_map_content_for_layer(layer_id, ctx.user_id, meta_db))
```

Direct calls (without `create_task`) for same-service work like `refresh_layer_bbox` — these still use the same try/except pattern.

---

## Injection-Safe DSL Filter Compiler

**File:** `api/app/services/feature_filter.py`

The DSL compiles JSON expression trees to parameterized SQL. The key security invariant:

> Field names and values are NEVER interpolated into SQL strings. They always go into the `params` dict.

```python
# CORRECT — field name goes as a param VALUE to the >>: operator
params[f_key] = field_name          # e.g., params["e_f1"] = "status"
f"properties->>:{f_key}"           # SQL: properties->>:e_f1

# CORRECT — comparison value goes as a param
params[v_key] = value               # e.g., params["e_v1"] = "active"
f":{v_key}"                         # SQL: :e_v1

# WRONG — never do this
f"properties->>'{field_name}'"      # SQL injection risk
```

DSL format example:
```json
{
  "op": "AND",
  "conditions": [
    {"field": "status", "op": "eq", "value": "active"},
    {"field": "population", "op": "gt", "value": 1000},
    {
      "op": "OR",
      "conditions": [
        {"field": "name", "op": "starts_with", "value": "Road"},
        {"field": "category", "op": "in", "value": ["highway", "primary"]}
      ]
    }
  ]
}
```

Limits: `MAX_DEPTH = 10`, `MAX_CONDITIONS = 50`. Both raise `ValueError` → HTTP 400 in caller.

---

## Redis Cache Keys

| Key | TTL | Value | Invalidate when |
|-----|-----|-------|-----------------|
| `groups:{user_id}` | 300s | `list[str]` of group IDs | Group membership changes |
| `lastseen:{user_id}` | 60s | `1` (sentinel) | Expires naturally |
| `maptree:{map_id}` | 30s | Flat row dicts from `get_map_layer_tree()` | Any map_layers or map_groups change |
| `mapfresh:{map_id}` | 30s | Freshness response dict | Feature mutation in any layer of this map |
| `stats:{layer_id}` | 60s | Full stats dict | Feature mutation on this layer |
| `expr:{expression_id}` | 300s | Expression JSONB dict | Expression updated or deleted |
| `layermaps:{layer_id}` | 3600s | Redis set of map_id strings | Layer added to or removed from a map |

**Do not use Redis directly** — import from `app.cache`:
```python
from app.cache import cache_get, cache_set, cache_delete, cache_sadd, cache_smembers
```

---

## Version History Design

Full snapshots, not diffs. Version N contains the complete state of the resource at that point.

Race-condition-free counter: `next_resource_version()` SQL function uses `FOR UPDATE` within the same transaction, preventing two concurrent updates from getting the same version number.

Always call `record_version()` in the same transaction as the UPDATE:
```python
# In the router, before commit:
old_snapshot = {field: getattr(layer, field) for field in LAYER_VERSION_FIELDS}
changed = [f for f in LAYER_VERSION_FIELDS if body.dict(exclude_unset=True).get(f) != getattr(layer, f)]
# ... apply updates ...
await record_version(db, "layer", layer.id, old_snapshot, changed, ctx.user_id)
await db.commit()  # ONE commit for both UPDATE and version INSERT
```

---

## Map Content Version vs Updated At

A `Map` has two separate change signals:

- `updated_at` / `updated_by` — metadata changed (name, description)
- `content_version` / `content_updated_at` / `content_updated_by` — structural change (layers added/removed, features edited)

`content_version` increments when:
1. A layer is added to or removed from the map
2. Any feature in any layer of the map is mutated (propagated via `refresh_map_content_for_layer`)

The `/maps/{id}/open` endpoint uses `content_version` in its ETag:
```python
etag = f'"{map_id}-{map.content_version}-{int(max_features_ts.timestamp())}"'
```

---

## Embedded Maps

A `MapGroup` can have `embedded_map_id` set — meaning that group is a live reference to another map. When `/maps/{id}/open` resolves, embedded map groups expand their children from the embedded map's layer tree, subject to the user's permissions on the embedded map (not the parent map).

Rules:
- Self-embed blocked at DB level: `CHECK (embedded_map_id IS NULL OR embedded_map_id <> map_id)`
- Circular embeds (A→B→A) blocked at API level in `map_service._check_embed_cycle()` (max depth 5)
- Layers from embedded maps are NOT duplicated in `map_layers` — resolved at query time
- User must have viewer+ on the embedded map to see any of its layers

---

## Identify Layers by Polygon

`POST /layers/identify` — must be registered BEFORE `/{layer_id}` routes in `routers/layers.py`. FastAPI matches routes in order and "identify" would otherwise be parsed as a UUID path parameter.

The endpoint:
1. Returns ALL accessible layers (not just those with features in the polygon)
2. Each layer has `feature_count_in_area` — 0 if no features, actual count otherwise
3. Uses the existing `group_layer_id` folder system for hierarchy (NOT map groups)
4. Uses a single SQL query per shard grouping by `layer_id` — not N separate queries
5. Layers the user cannot read are entirely absent from the response

Frontend loads individual layers on demand via `GET /layers/{id}/features?spatial_op=intersects&filter_geojson=...`

---

## Spatial Query Ops (features.py list_features)

All spatial clauses use parameterized geometry — never user-controlled text in SQL:
```python
SPATIAL_CLAUSES = {
    "intersects": "ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "within":     "ST_Within(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "contains":   "ST_Contains(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "dwithin":    "ST_DWithin(geom::geography, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326)::geography, :dist_m)",
}
```

Geometry zoom simplification tolerance: `360.0 / (256 * (2 ** zoom))`. Apply only when `zoom < 14`.

---

## Alembic Migration Branches

Two independent branches. Always run separately:

```powershell
# Meta branch (geo_meta DB via pgbouncer :6432)
venv\Scripts\alembic -x db=meta upgrade meta@head

# Features branch (geo_features DB :5433)
venv\Scripts\alembic -x db=features upgrade features@head
```

New migrations added (not yet run):
- `007` → `008` → `009` → `010` (meta branch, in sequence)
- `002f` (features branch, after `001f`)

---

## Export Service Notes

- **pyshp:** Shapefile field names max 10 characters — truncate longer names. Run in `asyncio.to_thread()`.
- **fiona:** GeoPackage via `fiona.open(path, 'w', driver='GPKG', ...)`. Run in `asyncio.to_thread()`.
- **SRID validation:** Check `srid in request.app.state.valid_srids` (frozenset loaded at startup from `spatial_ref_sys`). Return 400 for invalid SRIDs. Default SRID is 4326 if not specified.
- **ST_Transform:** Always transform in the DB, not in Python: `ST_AsGeoJSON(ST_Transform(geom, :target_srid))`.

---

## Permission Check Pattern

```python
from app.auth.permissions import can_user_do

# In router:
if not await can_user_do(meta_db, ctx, str(resource_id), "read"):
    raise HTTPException(status_code=403, detail="Read permission required")
```

Superadmins bypass all checks (handled inside `can_user_do`).

For maps: pass `str(map_id)` as the resource_id. The underlying PostgreSQL function handles both layer and map IDs.
