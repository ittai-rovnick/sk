# What Has Been Implemented

All items here are written to disk and committed. None of the migrations have been run against the DB yet — run them before testing anything.

---

## Step 1 — Migration 007: Maps, Map Groups, Map Layers

**File:** `api/alembic/versions/007_maps_and_map_groups.py`
**Branch:** meta (`down_revision = "006"`)

Creates three tables and one SQL function:

- **`maps`** — first-class map containers scoped to a database. Has `content_version` (INT) and `content_updated_at`/`content_updated_by` to track structural changes (layers added/removed), separately from `updated_at` which tracks metadata changes (name/description).
- **`map_groups`** — organizational groups inside a map. Nestable via `parent_id` self-FK. Has `embedded_map_id` for embedding another map as a group. Constraints: `chk_no_self_parent`, `chk_no_self_embed`. Unique index per (map, parent, name).
- **`map_layers`** — join table linking layers to maps. Has `group_id` (ON DELETE SET NULL so deleting a group moves its layers to root), `sort_order`, `is_visible`, `filter_expression JSONB` (DSL filter applied when viewing this layer in this map).
- **`get_map_layer_tree(p_map_id UUID)`** — SQL function returning flat rows for both groups and layers of a map. Python assembles into nested tree. Returns: `row_type`, `row_id`, `parent_id`, `name`, `sort_order`, `is_expanded`, `embedded_map_id`, `layer_id`, `is_visible`, `srid`, `geometry_types`, `bbox_arr FLOAT8[]`.

---

## Step 2 — Migration 008: Resource Version History

**File:** `api/alembic/versions/008_resource_versions.py`
**Branch:** meta (`down_revision = "007"`)

- **`resource_type` ENUM** — `('layer', 'map')`
- **`resource_versions`** — stores FULL snapshots (not diffs) at each version. Columns: `id BIGSERIAL`, `resource_type`, `resource_id UUID`, `version INT`, `snapshot JSONB` (complete state), `changed_fields TEXT[]`, `message TEXT`, `changed_by UUID`, `changed_at TIMESTAMPTZ`. UNIQUE on `(resource_type, resource_id, version)`.
- **`next_resource_version(p_type, p_id)`** — SQL function using `SELECT MAX(version) ... FOR UPDATE` inside the same transaction. Prevents race conditions when two concurrent updates try to record the same version number.

---

## Step 3 — Migration 009: Layer Change Tracking Columns

**File:** `api/alembic/versions/009_change_tracking.py`
**Branch:** meta (`down_revision = "008"`)

Adds to existing `layers` table:
- `features_updated_at TIMESTAMPTZ` — when any feature in this layer was last created/updated/deleted
- `features_updated_by UUID → users(id)` — who did it
- `updated_by UUID → users(id)` — who last updated layer metadata

Creates partial index: `layers_features_updated_at_idx ON layers(features_updated_at DESC NULLS LAST) WHERE deleted_at IS NULL`

Used by the `/maps/{id}/freshness` endpoint to find layers changed since a given timestamp.

---

## Step 4 — Migration 010: Saved Expressions

**File:** `api/alembic/versions/010_saved_expressions.py`
**Branch:** meta (`down_revision = "009"`)

Creates `saved_expressions` table — named, reusable filter expressions scoped per layer:
- `id UUID`, `layer_id UUID FK → layers ON DELETE CASCADE`
- `name TEXT`, `description TEXT`
- `expression JSONB` — the DSL tree (see architecture doc for DSL format)
- `created_by UUID → users`, timestamps
- UNIQUE on `(layer_id, name)`

---

## Step 5 — Migration 002f: Feature Stats Indexes

**File:** `api/alembic/versions/002f_feature_stats_indexes.py`
**Branch:** features (`down_revision = "001f"`)

Creates per-partition partial indexes on all 32 features partitions. PostgreSQL 16 does not propagate parent-table partial indexes to partitions automatically, so each must be created individually:

```sql
CREATE INDEX features_p{N}_layer_del_idx
    ON features_p{N} (layer_id, deleted_at) WHERE deleted_at IS NULL
```

Required for the stats endpoint to avoid full partition scans when counting features by layer.

---

## Step 6 — requirements.txt

**File:** `api/requirements.txt`

Added:
- `redis[asyncio]==5.0.4` — async Redis client (was `redis==5.0.4`, missing `[asyncio]` extra)
- `pyshp==2.3.1` — pure-Python Shapefile writer, zero system deps
- `fiona==1.9.6` — GeoPackage export via GDAL (already present in PostGIS Docker image)

---

## Step 7 — Redis Cache Module

**File:** `api/app/cache.py` (new file)

Thin async wrapper around `redis.asyncio`. All other code imports from here — never import redis directly.

Functions:
- `get_redis()` — lazy singleton connection from `settings.redis_url`
- `cache_get(key)` → `dict | list | str | int | None` — deserializes JSON
- `cache_set(key, value, ttl)` — serializes JSON, sets with TTL
- `cache_delete(key)` — deletes one key
- `cache_sadd(key, *members, ttl=None)` — Redis SADD + optional EXPIRE
- `cache_smembers(key)` → `set[str]` — Redis SMEMBERS

---

## Step 8 — Auth: Redis Caching

**File:** `api/app/auth/local.py`

Two changes:

**`_resolve_custom_group_ids(db, user_id)`** — added Redis cache check at the top:
- Key: `groups:{user_id}`, TTL: 300 seconds (5 min)
- On cache hit: returns cached list, skips the recursive CTE entirely (saves ~3 DB round-trips per request)
- On cache miss: runs existing CTE, stores result in Redis

**`validate_token(token, db)`** — added `last_seen_at` write debounce:
- Key: `lastseen:{user_id}`, TTL: 60 seconds
- If sentinel present: skips the `UPDATE users SET last_seen_at = NOW()` DB write
- If absent: writes to DB, sets sentinel
- Reduces DB writes from "every request" to "at most once per 60 seconds per user"

**Cache invalidation:** When group membership changes (groups router add/remove member), delete `groups:{user_id}` for affected users. This is NOT yet wired in `routers/groups.py` — it's a pending task.

---

## Step 9 — Layer Geometry Service + Features Bug Fix

**File:** `api/app/services/layer_geometry.py`

Two new functions added (same fire-and-forget pattern as `refresh_layer_geometry_types`):

**`refresh_layer_bbox(layer_id, shard_db, meta_db)`**:
- Queries: `SELECT ST_AsText(ST_Envelope(ST_Collect(geom))) FROM features WHERE layer_id=... AND deleted_at IS NULL`
- If no features → sets `layers.bbox = NULL`
- If features exist → sets `layers.bbox = ST_GeomFromText(:wkt, 4326)`, then reads back `[xmin, ymin, xmax, ymax]`
- Returns list of 4 floats or None

**`refresh_layer_feature_stamp(layer_id, actor_id, meta_db)`**:
- Updates `layers.features_updated_at = NOW()`, `layers.features_updated_by = actor_id`, `layers.updated_at = NOW()`
- `actor_id` is `ctx.user_id` (UUID string) — NOT `ctx.ms_object_id`

**File:** `api/app/routers/features.py`

Bug fix + new calls at all 4 mutation endpoints (create, update, delete, bulk-delete):
- **Bug fixed:** `update_feature()` previously called `refresh_layer_geometry_types()` only inside `if body.geom is not None:`. Property-only edits (field value changes) produced zero change signal. Fixed: `refresh_layer_feature_stamp()` is now called unconditionally on ALL mutations, outside the geom-check block.
- `refresh_layer_bbox()` called alongside `refresh_layer_geometry_types()` at all geometry-changing sites
- `refresh_layer_feature_stamp()` called OUTSIDE `async with shard_sessions[...]()` (it only touches meta_db)

---

## Step 10 — Schemas: Layers

**File:** `api/app/schemas/layers.py`

Added to `LayerResponse`:
- `bbox: list[float] | None = None` — `[lon_min, lat_min, lon_max, lat_max]`
- `features_updated_at: datetime | None = None`
- `features_updated_by: uuid.UUID | None = None`
- `updated_by: uuid.UUID | None = None`

New schema groups added:
- **Identify schemas:** `LayerIdentifyRequest`, `LayerIdentifyLayerNode`, `LayerIdentifyGroupNode`, `LayerIdentifyResponse`
- **Version schemas:** `VersionListItem`, `VersionDetail`, `VersionRestoreResponse`
- **Expression schemas:** `ExpressionCreate`, `ExpressionUpdate`, `ExpressionResponse`, `ExpressionListItem`

Also added `GEOJSON_GEOMETRY_TYPES` frozenset at top of file (for validate geometry input to identify endpoint).

---

## Step 11 — Feature Filter DSL Compiler

**File:** `api/app/services/feature_filter.py` (new file)

`compile_expression(expr, schema_fields, params, prefix, depth, _counter)` — recursive function that compiles a DSL JSON tree into a parameterized SQL clause string.

**Security design:** Field names and values NEVER go into the SQL string. They always go through the `params` dict:
- Field name → `params[f"{prefix}_f{idx}"] = field_name` → accessed as `properties->>:{f_key}` in SQL
- Value → `params[v_key] = value` → accessed as `:{v_key}` in SQL

**Limits:** `MAX_DEPTH = 10`, `MAX_CONDITIONS = 50` — raises `ValueError` (→ HTTP 400 in caller)

Supported ops: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`, `is_null`, `is_not_null`

Boolean combinators: `AND`, `OR` (with a `conditions: [...]` list)

---

## Step 13 (partial) — ORM Models

Three new SQLAlchemy model files:

**`api/app/models/maps.py`** — `Map`, `MapGroup`, `MapLayer` ORM classes matching the migration 007 schema exactly.

**`api/app/models/versions.py`** — `ResourceTypeEnum(str, enum.Enum)` with `layer`/`map` values; `ResourceVersion` model with BigInteger PK, snapshot JSONB, changed_fields ARRAY(String).

**`api/app/models/expressions.py`** — `SavedExpression` model with UUID PK, layer_id FK (CASCADE), name, expression JSONB, timestamps.

---

## How to run the migrations

```powershell
cd geo-platform\api

# Meta branch — runs 007, 008, 009, 010 in sequence
venv\Scripts\alembic -x db=meta upgrade meta@head

# Features branch — runs 002f
venv\Scripts\alembic -x db=features upgrade features@head
```
