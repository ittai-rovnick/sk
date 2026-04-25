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

## Step 12 — Advanced Feature Query Params (DONE)

**File:** `api/app/routers/features.py`

`list_features()` now accepts:
- `spatial_op` ∈ `{intersects, within, contains, dwithin}` + `filter_geojson` (+ `filter_distance_m` for dwithin)
- `expression_id: UUID` — loads saved expression (Redis `expr:{id}` 300s, fallback DB)
- `expression: str` — inline DSL JSON
- `zoom: int` — applies `ST_SimplifyPreserveTopology` when zoom < 14, tolerance = `360 / (256 * 2^zoom)`
- `srid: int` — validated against `request.app.state.valid_srids`, applies `ST_Transform`

All spatial clauses come from a static `SPATIAL_CLAUSES` dict (no user text in SQL). Geometry SELECT is composed via `_build_geom_select()`.

After every mutation (`create`, `update`, `delete`, `bulk_delete`): `_invalidate_after_mutation()` runs:
- `refresh_layer_feature_stamp()` (existing)
- `cache_delete(f"stats:{layer_id}")`
- `asyncio.create_task(refresh_map_content_for_layer(...))` (fire-and-forget)

---

## Step 13 — Map Pydantic Schemas (DONE)

**File:** `api/app/schemas/maps.py` (new)

All schemas: `MapCreate/Update/Response`, `MapGroupCreate/Update/Response`, `MapLayerAdd/Update/Response`, `MapLayerNode`, `MapGroupNode` (recursive — `model_rebuild()` called), `MapOpenResponse`, `MapFreshnessChangedLayer`, `MapFreshnessResponse`, `GroupPermissionGrantRequest/Response`.

---

## Step 14 — Map Service (DONE)

**File:** `api/app/services/map_service.py` (new)

Implements:
- CRUD: `get_map`, `list_maps`, `create_map`, `update_map`, `delete_map` (soft), `get_map_extent`
- Group CRUD: `create_map_group` (with `_check_embed_cycle` max depth 5), `update_map_group`, `delete_map_group`
- Layer membership: `add_layer_to_map` (bumps content_version + sadd Redis set + invalidate maptree), `remove_layer_from_map` (srem), `update_map_layer`
- Tree: `get_map_layer_tree` (Redis `maptree:{map_id}` 30s) + `assemble_tree` (nested groups + layers, sorted by sort_order)
- `refresh_map_extent` — union of layer bboxes
- `refresh_map_content_for_layer` — fire-and-forget, opens own MetaSessionLocal session, bumps content_version on every map containing the layer
- `get_map_freshness` — Redis `mapfresh:{map_id}:{since-iso}` 30s
- `expand_group_layers` — recursive collection of layer_ids in group + sub-groups
- `_invalidate_map_caches` — wildcard mapfresh delete via `scan_iter`

---

## Step 15 — Version Service (DONE)

**File:** `api/app/services/version_service.py` (new)

- `record_version()` — calls `next_resource_version()` SQL fn (FOR UPDATE → race-safe), inserts into `resource_versions`. **Does not commit** — the caller commits in the same transaction as the UPDATE it records.
- `get_versions()`, `get_version()` — list / detail.
- `restore_version()` — captures pre-restore snapshot, applies snapshot fields to live row, records new version with `message="Restored from v{n}"`, commits.
- Whitelists: `LAYER_VERSION_FIELDS = ["name","description","status","srid","tags","sort_order","group_layer_id"]`, `MAP_VERSION_FIELDS = ["name","description"]`.
- `_json_safe()` serializes UUIDs/datetimes via `default=str`.

---

## Step 16 — Maps Router + main.py wiring (DONE)

**File:** `api/app/routers/maps.py` (new)
**File:** `api/app/main.py` (edited)

Endpoints registered (all gated by `can_user_do(map_id, op)`):
- `POST/GET /maps`, `GET/PUT/DELETE /maps/{id}`
- `GET /maps/{id}/open` — ETag `"{map_id}-{content_version}-{max_features_ts}"`, returns 304 on If-None-Match. Pulls flat rows from `get_map_layer_tree()` (Redis 30s) + assembles via `map_service.assemble_tree`. Includes `extent` array.
- `GET /maps/{id}/freshness?since=<iso>` — Redis `mapfresh:{map_id}:{since}` 30s
- `GET/POST/PUT/DELETE /maps/{id}/groups[/{gid}]`
- `POST/DELETE/PUT /maps/{id}/layers[/{lid}]`
- `POST /maps/{id}/groups/{gid}/permissions` — bulk grant per-layer Permission rows for the expanded group's layers
- `GET/GET/POST /maps/{id}/versions[/{v}[/restore]]`

`update_map_endpoint` records a version IFF any whitelisted field changed (record_version + final commit happen in one transaction).

`main.py`:
- Adds `import maps` and `app.include_router(maps.router)`
- Lifespan now calls `_load_valid_srids(app)` populating `app.state.valid_srids: frozenset[int]` from `spatial_ref_sys`. Logged warning + empty frozenset on failure (so the API still boots if PostGIS isn't ready).

---

## Step 17 — Layer router: identify, expressions, versions (DONE)

**File:** `api/app/routers/layers.py` (rewritten)
**File:** `api/app/routers/groups.py` (cache invalidation wired)
**File:** `api/app/schemas/layers.py` (bbox coercion validator added)

- `POST /layers/identify` — registered FIRST (before `/{layer_id}` routes). Validates GeoJSON type ∈ `GEOJSON_GEOMETRY_TYPES`, filters layers to `can_user_do(read)`, runs one COUNT(*) GROUP BY layer_id per shard with parameterized polygon, builds tree using `group_layer_id` (existing folder system, not map groups), returns `LayerIdentifyResponse`.
- `update_layer()` now records a version (LAYER_VERSION_FIELDS whitelist, in-tx) when whitelisted fields change, sets `updated_by`.
- Expression CRUD: `POST/GET/GET/{eid}/PUT/DELETE /layers/{id}/expressions`. Calls `compile_expression(...)` against schema fields; raises 400 on invalid DSL. PUT/DELETE bust `expr:{eid}` Redis key.
- Version endpoints: `GET /layers/{id}/versions`, `GET /layers/{id}/versions/{v}`, `POST /layers/{id}/versions/{v}/restore`.
- `LayerResponse.bbox` field validator coerces non-list (e.g. WKBElement) values to `None` so geoalchemy2's Geometry attribute doesn't break Pydantic serialization. Live extent values are populated separately when needed.

`groups.py`: `add_member` and `remove_member` now `cache_delete(f"groups:{user_id}")` so the next auth check rebuilds the cached membership list.

---

## Step 18 — Export Service (DONE)

**File:** `api/app/services/export_service.py` (new)
**File:** `api/requirements.txt` (added `shapely==2.0.6`)

- `export_geojson(shard_db, layer, target_srid)` — builds FeatureCollection with `crs.name = urn:ogc:def:crs:EPSG::{srid}`, returns bytes.
- `export_shapefile(shard_db, meta_db, layer, target_srid)` — uses pyshp via `asyncio.to_thread`. Field names truncated to 10 chars (with dedup suffix). Geometry parsed via shapely from `ST_AsBinary(ST_Transform(geom, srid))`. Writes .shp/.shx/.dbf/.prj into a tempdir, zips them, returns the .zip bytes. Schema fields read from `LayerSchema`; falls back to first feature's properties.
- `export_gpkg(shard_db, meta_db, layer, target_srid)` — uses fiona with `'GPKG'` driver via `asyncio.to_thread`. Writes to a tempfile, returns its bytes.
- `validate_srid(app_state, srid)` — checks against `app.state.valid_srids` (returns True if unset).

## Step 19 — Export endpoint (DONE)

**File:** `api/app/routers/layers.py`

`GET /layers/{id}/export?format=geojson|shapefile|gpkg&srid=<int>` — `can_user_do(export)`, validates SRID via `request.app.state.valid_srids`, returns `Response` with `Content-Disposition: attachment` and matching media type (`application/geo+json`, `application/zip`, `application/geopackage+sqlite3`). Default SRID = 4326.

---

## Step 20 — Stats Service (DONE)

**File:** `api/app/services/stats_service.py` (new)

`get_layer_stats(shard_db, layer_id, json_schema)`:
- Redis check `stats:{layer_id}` (60s TTL)
- Total count via partition-friendly `WHERE layer_id = ... AND deleted_at IS NULL`
- Geometry-type breakdown `GROUP BY ST_GeometryType(geom)`
- BBox via `ST_Envelope(ST_Collect(geom))`
- Per-field stats from `json_schema["fields"]`:
  - `number` → MIN/MAX/AVG (cast to numeric) + null_count
  - `boolean` → true/false/null counts
  - `string`/other → null_count + unique_count + top 10 values
- Per-field exceptions are caught and reported as `{"type": …, "error": …}` so a single bad field doesn't tank the response.

Stats cache invalidation already wired in features.py via `_invalidate_after_mutation`.

## Step 21 — Stats endpoint (DONE)

**File:** `api/app/routers/layers.py`

`GET /layers/{id}/stats` — `can_user_do(read)`, loads `LayerSchema.json_schema` and delegates to `stats_service.get_layer_stats`.

---

## Step 22 — Frontend types (DONE)

**File:** `web/src/types/index.ts`

Added `bbox`, `features_updated_at`, `features_updated_by` to `Layer`. New interfaces:
- `GeoMap`, `MapGroup`, `MapLayerNode`, `MapGroupNode`, `MapTreeNode`, `MapOpenResponse`, `MapFreshnessChangedLayer`, `MapFreshnessResponse`
- `FieldStat` (string/number/boolean discriminated union, plus an `error` fallback variant), `LayerStats`
- `IdentifyLayerNode`, `IdentifyGroupNode`, `IdentifyTreeNode`, `LayerIdentifyResponse`
- `VersionListItem`, `VersionDetail`, `SavedExpressionListItem`, `SavedExpressionDetail`

## Step 23 — Frontend API modules (DONE)

**File:** `web/src/api/maps.ts` (new) + extends `web/src/api/layers.ts`

`maps.ts`:
- `mapsApi`: list, create, get, update, delete
- `open(id, etag?)` — sends `If-None-Match` and `validateStatus: 200|304` so a 304 doesn't throw; returns the full Axios `AxiosResponse` so callers can read the `etag` header
- `freshness(id, sinceISO)`
- Group CRUD, layer add/remove/update, bulk group permission grant
- `layerExportUrl(layerId, format, srid?)` — base URL only (Bearer is on axios interceptor; raw `<a href>` won't work)
- `downloadLayerExport(...)` — axios blob → temporary `<a download>` so the auth header is included
- `layerStatsApi.get(layerId)`

`layers.ts`: appended `layers.identify(databaseId, geometry)`, `layers.versions.{list,get,restore}`, `layers.expressions.{list,get,create,update,delete}`.

---

## Step 24 — MapGroupTree component (DONE)

**File:** `web/src/components/maps/MapGroupTree.tsx` (new)

- Recursive AntD `<Tree>` renderer over `MapTreeNode[]` from `mapsApi.open(...).tree`.
- Layer nodes: geometry-typed icon (point=blue / line=green / polygon=orange / fallback=grey), name (clickable when `onLayerClick` provided, dimmed when hidden), eye toggle (`mapsApi.updateLayer({ is_visible })`), Export dropdown (GeoJSON/Shapefile/GeoPackage via `downloadLayerExport` so the Bearer header is included), more menu (Remove from map).
- Group nodes: folder icon, kebab menu (Add sub-group, Rename, Grant permissions [if `onGrantPermissions` provided], Delete). Embedded maps surface a purple "embedded" tag.
- Modals for Rename / Add sub-group (top-level via the "Add group" button at the top).
- Drag-and-drop: dragging a layer onto a group reparents (`updateLayer({ group_id })`); dragging between siblings sets `group_id` to that level's parent. Group reparent isn't wired — toast says use the menu.
- TypeScript build passes (`tsc --noEmit` clean).

Props:
```ts
{
  tree: MapTreeNode[];
  mapId: string;
  onRefresh: () => void;
  onGrantPermissions?: (groupId: string, groupName: string) => void;
  onLayerClick?: (node: MapLayerNode) => void;
}
```

---

## Step 25 — ExpressionBuilder component (DONE)

**File:** `web/src/components/maps/ExpressionBuilder.tsx` (new)

Nested AND/OR DSL builder for the same JSON shape `compile_expression()` accepts on the backend.

- Each `Group` renders as a `<Card>` with op selector (`AND`/`OR`), "Condition" / "Group" buttons, and a delete button (root group is undeletable).
- Each `Condition` renders inline: field selector → op selector → value input. The op list adapts to field type (string / number / boolean) and changing the field resets op/value to type-appropriate defaults.
- Special inputs: boolean → `<Switch>`; number → `<InputNumber>`; `in`/`not_in` → `<Select mode="tags">` with comma + Enter token separators; `between` → two `<InputNumber>`s for `lo`/`hi`; `is_null` / `is_not_null` → no value input.
- Toolbar: **Save as…** → `layers.expressions.create` (validation errors from the backend's `compile_expression()` surface as a toast); **Load saved** → modal listing `layers.expressions.list`, click a row to load via `layers.expressions.get`; **Clear** → resets to `null`.
- Pure path-based mutators (`replaceAt`, `appendAt`) — value flows are controlled via `value`/`onChange`, no internal expression state.

Props:
```ts
{
  layerId: string;
  schema: { fields?: { name: string; type?: "string"|"number"|"boolean"|"date" }[] } | null;
  value: Group | null;
  onChange: (next: Group | null) => void;
}
```

`tsc --noEmit` passes.

---

## How to run the migrations

```powershell
cd geo-platform\api

# Meta branch — runs 007, 008, 009, 010 in sequence
venv\Scripts\alembic -x db=meta upgrade meta@head

# Features branch — runs 002f
venv\Scripts\alembic -x db=features upgrade features@head
```
