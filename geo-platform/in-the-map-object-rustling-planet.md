# Geo-Platform: Maps, Layer Groups & GIS Features — Implementation Plan

## Context

The geo-platform serves ArcGIS Pro, Esri Portal, and Argo (offline field app). The current system has `GeoDatabase > GroupLayer > Layer` with a flat permission ACL. This plan implements 9 new capabilities:

1. **Map objects with layer groups** — hierarchical, ordered layer organization inside maps
2. **Layer bounding box** — auto-maintained extent after every feature mutation
3. **Advanced feature queries** — spatial predicates + attribute filters (parameterized, injection-safe)
4. **Export formats** — GeoJSON, Shapefile, GeoPackage
5. **CRS / reprojection** — `?srid=` on features + export endpoints
6. **Attribute statistics** — per-field stats endpoint with in-process TTL cache
7. **Geometry simplification** — `?zoom=` param applies `ST_SimplifyPreserveTopology`
8. **Fixed version history** — full snapshots (not diffs), race-condition-free counter
9. **Identify layers by polygon** — draw a polygon on the map, get back which layers have features inside it (cross-layer spatial discovery)

**Key findings from codebase exploration:**
- `layers.srid` (INT) and `layers.bbox` (Geometry POLYGON 4326) **already exist** — just never populated/used
- `maps` and `map_layers` tables **do not exist yet**
- No export endpoints exist (S3 export bucket and quota config already present)
- Permissions table will be replaced by `resource_permissions` (db_new_design.html migration 007)
- Features shard DB accessed via raw `text()` SQL only — no ORM there
- `refresh_layer_geometry_types()` is the canonical fire-and-forget pattern to follow exactly

---

## Critical Files

| File | Role |
|------|------|
| `api/app/routers/features.py` | Add spatial/attr filters, zoom, srid params |
| `api/app/services/layer_geometry.py` | Add `refresh_layer_bbox()` |
| `api/app/models/layers.py` | Layer model (bbox column exists, never updated) |
| `api/app/schemas/layers.py` | Add `bbox` to LayerResponse |
| `api/app/main.py` | Register new maps router |
| `web/src/pages/MapPage.tsx` | Major refactor: map selector + group tree panel |
| `web/src/types/index.ts` | Add Map, MapGroup, MapLayerEntry, LayerStats types |

---

## Migration Plan

All migrations land in `api/alembic/versions/`. Run meta branch with `-x db=meta`, features branch with `-x db=features`.

### Migration `007_maps_and_map_groups.py` (meta branch)

Creates the map object model with group support:

```sql
-- Maps: first-class containers, database-scoped
CREATE TABLE maps (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    database_id         UUID REFERENCES geo_databases(id) ON DELETE CASCADE,
    extent              GEOMETRY(Polygon, 4326),      -- union of all member layer bboxes
    -- Metadata change tracking (name/description changed)
    created_by          UUID REFERENCES users(id),
    updated_by          UUID REFERENCES users(id),
    deleted_at          TIMESTAMPTZ,
    deleted_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Structural/content change tracking (layers added/removed, features edited)
    content_version     INT NOT NULL DEFAULT 0,
    content_updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_updated_by  UUID REFERENCES users(id)
);
CREATE INDEX maps_database_id_idx ON maps(database_id);
CREATE INDEX maps_deleted_at_idx  ON maps(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX maps_extent_idx      ON maps USING GIST(extent) WHERE extent IS NOT NULL;

-- Map Groups: organizational groups WITHIN a map (not workspace-level folders)
-- These are purely for visual hierarchy — permissions are still per-layer
CREATE TABLE map_groups (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    map_id      UUID NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
    parent_id   UUID REFERENCES map_groups(id) ON DELETE CASCADE,  -- nestable
    name        TEXT NOT NULL,
    sort_order  INT NOT NULL DEFAULT 0,
    is_expanded BOOLEAN NOT NULL DEFAULT TRUE,
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_no_self_parent CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX map_groups_map_id_idx    ON map_groups(map_id);
CREATE INDEX map_groups_parent_id_idx ON map_groups(parent_id);
-- Unique name per (map, parent)
CREATE UNIQUE INDEX map_groups_unique_name_idx
    ON map_groups(map_id, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), name);

-- Map Groups: add embedded_map_id for "insert a map as a group" feature
-- When embedded_map_id IS NOT NULL, this group is a live reference to another map.
-- Its layers are resolved dynamically from the embedded map's layer tree.
-- Permissions: user must have viewer+ on the embedded map to see any layers.
ALTER TABLE map_groups ADD COLUMN embedded_map_id UUID REFERENCES maps(id) ON DELETE CASCADE;
-- Prevent a map embedding itself (deeper cycles caught at API level)
ALTER TABLE map_groups ADD CONSTRAINT chk_no_self_embed
    CHECK (embedded_map_id IS NULL OR embedded_map_id != map_id);

-- Map-Layer join: a layer can be in multiple maps, optionally inside a group.
-- filter_expression: optional DSL expression applied when this layer is viewed in this map.
CREATE TABLE map_layers (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    map_id            UUID NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
    layer_id          UUID NOT NULL REFERENCES layers(id) ON DELETE CASCADE,
    group_id          UUID REFERENCES map_groups(id) ON DELETE SET NULL,
    sort_order        INT NOT NULL DEFAULT 0,
    is_visible        BOOLEAN NOT NULL DEFAULT TRUE,
    filter_expression JSONB,    -- optional per-map-context attribute/spatial filter (DSL)
    added_by          UUID REFERENCES users(id),
    added_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (map_id, layer_id)
);
CREATE INDEX map_layers_map_id_idx   ON map_layers(map_id);
CREATE INDEX map_layers_layer_id_idx ON map_layers(layer_id);
CREATE INDEX map_layers_group_id_idx ON map_layers(group_id);

-- SQL function: returns flat rows for the full group+layer tree of a map
-- Caller assembles into nested structure in Python
CREATE OR REPLACE FUNCTION get_map_layer_tree(p_map_id UUID)
RETURNS TABLE (
    row_type       TEXT,       -- 'group' | 'layer'
    row_id         UUID,       -- group.id or map_layers.id
    parent_id      UUID,       -- group.parent_id or map_layers.group_id
    name           TEXT,
    sort_order     INT,
    is_expanded    BOOLEAN,
    layer_id       UUID,
    is_visible     BOOLEAN,
    srid           INT,
    geometry_types TEXT[],
    bbox_arr       FLOAT8[]    -- [lon_min, lat_min, lon_max, lat_max] or NULL
) AS $$
BEGIN
    -- Groups
    RETURN QUERY
    SELECT 'group'::TEXT, mg.id, mg.parent_id, mg.name, mg.sort_order, mg.is_expanded,
           NULL::UUID, NULL::BOOLEAN, NULL::INT, NULL::TEXT[], NULL::FLOAT8[]
    FROM map_groups mg WHERE mg.map_id = p_map_id;
    -- Layers
    RETURN QUERY
    SELECT 'layer'::TEXT, ml.id, ml.group_id, l.name, ml.sort_order, NULL::BOOLEAN,
           l.id, ml.is_visible, l.srid, l.geometry_types,
           CASE WHEN l.bbox IS NOT NULL THEN
               ARRAY[ST_XMin(l.bbox)::FLOAT8, ST_YMin(l.bbox)::FLOAT8,
                     ST_XMax(l.bbox)::FLOAT8, ST_YMax(l.bbox)::FLOAT8]
           ELSE NULL END
    FROM map_layers ml
    JOIN layers l ON l.id = ml.layer_id
    WHERE ml.map_id = p_map_id AND l.deleted_at IS NULL;
END;
$$ LANGUAGE plpgsql STABLE;
```

### Migration `008_resource_versions.py` (meta branch)

Fixes the version history design from db_new_design.html. The original design stored only a `changes JSONB` diff — reconstructing state at version N requires applying N patches, which is fragile. This design stores **full snapshots**.

```sql
CREATE TYPE resource_type AS ENUM ('layer', 'map');

CREATE TABLE resource_versions (
    id             BIGSERIAL PRIMARY KEY,
    resource_type  resource_type NOT NULL,
    resource_id    UUID NOT NULL,
    version        INT NOT NULL,
    snapshot       JSONB NOT NULL,      -- FULL state at this point (not a diff)
    changed_fields TEXT[] NOT NULL,     -- field names that changed from previous version
    message        TEXT,                -- optional user comment
    changed_by     UUID REFERENCES users(id),
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (resource_type, resource_id, version)
);
CREATE INDEX resource_versions_resource_idx
    ON resource_versions(resource_type, resource_id, version DESC);
CREATE INDEX resource_versions_changed_at_idx
    ON resource_versions(changed_at DESC);

-- Race-condition-free version counter — call inside same transaction as the UPDATE
CREATE OR REPLACE FUNCTION next_resource_version(
    p_resource_type resource_type,
    p_resource_id   UUID
) RETURNS INT AS $$
DECLARE v_next INT;
BEGIN
    SELECT COALESCE(MAX(version), 0) + 1 INTO v_next
    FROM resource_versions
    WHERE resource_type = p_resource_type AND resource_id = p_resource_id
    FOR UPDATE;
    RETURN v_next;
END;
$$ LANGUAGE plpgsql;
```

### Migration `009_change_tracking.py` (meta branch)

Separates feature-change timestamps from metadata-change timestamps, and adds `who changed it` attribution to layers and maps.

```sql
-- Separate "features changed" signal from "metadata changed"
-- (currently refresh_layer_geometry_types() only writes updated_at,
--  which conflates metadata + feature edits into one column)
ALTER TABLE layers ADD COLUMN features_updated_at TIMESTAMPTZ;
ALTER TABLE layers ADD COLUMN features_updated_by UUID REFERENCES users(id);
ALTER TABLE layers ADD COLUMN updated_by          UUID REFERENCES users(id);

CREATE INDEX layers_features_updated_at_idx ON layers(features_updated_at DESC NULLS LAST)
    WHERE deleted_at IS NULL;

-- Maps: structural change tracking (also added to the CREATE TABLE in migration 007)
-- content_version bumps when layers/groups are added, removed, or reordered.
-- content_updated_at / content_updated_by track who last structurally changed the map.
-- (These go in migration 007 as CREATE TABLE columns — listed here for clarity.)
```

**Note**: `maps.content_version`, `maps.content_updated_at`, `maps.content_updated_by` are added directly in migration 007's `CREATE TABLE maps` (updated above). The columns on `layers` are separate because `layers` already exists.

### Migration `010_saved_expressions.py` (meta branch)

```sql
-- Reusable named filter expressions, scoped per layer.
-- Expressions use the DSL defined in feature_filter.py.
CREATE TABLE saved_expressions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id    UUID REFERENCES layers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    expression  JSONB NOT NULL,   -- compiled DSL tree (see Expression DSL section)
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (layer_id, name)
);
CREATE INDEX saved_expressions_layer_id_idx ON saved_expressions(layer_id);
```

### Migration `002f_feature_stats_indexes.py` (features branch)

Adds per-partition partial indexes for stats queries (needed because PG16 doesn't propagate parent-table partial indexes to partitions automatically):

```sql
DO $$
BEGIN
    FOR i IN 0..31 LOOP
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS features_p%s_layer_del_idx
             ON features_p%s (layer_id, deleted_at) WHERE deleted_at IS NULL', i, i);
    END LOOP;
END $$;
```

---

## New Backend Files

### `api/app/models/maps.py`
SQLAlchemy ORM models: `Map`, `MapGroup`, `MapLayer`.

### `api/app/models/versions.py`
SQLAlchemy ORM model: `ResourceVersion` (BIGSERIAL pk, snapshot JSONB, changed_fields ARRAY).

### `api/app/schemas/maps.py`
Pydantic schemas: `MapCreate`, `MapUpdate`, `MapResponse`, `MapGroupCreate`, `MapGroupUpdate`, `MapGroupResponse`, `MapLayerAdd`, `GroupPermissionGrant`.

### `api/app/schemas/versions.py`
Pydantic schemas: `VersionListItem`, `VersionDetail`, `VersionRestoreResponse`.

### `api/app/services/map_service.py`
Business logic for maps and map groups:
```python
async def create_map(db, body, actor_id) -> Map
async def update_map(db, map_id, body, actor_id) -> Map
async def delete_map(db, map_id, actor_id) -> None
async def get_map_layer_tree(db, map_id) -> list[dict]
    # Calls SELECT * FROM get_map_layer_tree(:map_id)
    # Assembles flat rows into {type, id, name, children/layers} tree
async def create_map_group(db, map_id, body, actor_id) -> MapGroup
async def update_map_group(db, group_id, body) -> MapGroup
async def delete_map_group(db, group_id) -> None
    # Layers in deleted group move to group_id=NULL (ON DELETE SET NULL)
async def add_layer_to_map(db, map_id, layer_id, group_id, sort_order, actor_id) -> MapLayer
async def remove_layer_from_map(db, map_id, layer_id) -> None
async def expand_group_layers(db, map_id, group_id) -> list[uuid.UUID]
    # Recursively collect all layer_ids in group + subgroups
    # Used by the bulk-permission-grant helper
async def refresh_map_extent(db, map_id) -> None
    # UPDATE maps SET extent = (
    #   SELECT ST_Envelope(ST_Collect(l.bbox))
    #   FROM map_layers ml JOIN layers l ON l.id = ml.layer_id
    #   WHERE ml.map_id = :map_id AND l.bbox IS NOT NULL AND l.deleted_at IS NULL
    # ) WHERE id = :map_id
async def refresh_all_map_extents_for_layer(layer_id, meta_db) -> None
    # Fire-and-forget: find all maps containing layer, refresh each
```

### `api/app/services/version_service.py`
```python
async def record_version(db, resource_type, resource_id, snapshot, changed_fields, actor_id, message=None) -> int
    # Calls next_resource_version() within same transaction, inserts row
async def get_versions(db, resource_type, resource_id, limit=50, offset=0) -> list[dict]
async def get_version_snapshot(db, resource_type, resource_id, version) -> dict | None
async def restore_version(db, resource_type, resource_id, version, actor_id) -> dict
    # Fetches snapshot at v, applies to live row, records new version
    # with message="Restored from v{version}"
```

### `api/app/services/export_service.py`
```python
async def export_geojson(shard_db, layer_id, target_srid) -> bytes
    # SELECT ST_AsGeoJSON(ST_Transform(geom, :srid)) → FeatureCollection bytes
async def export_shapefile(shard_db, layer, target_srid) -> bytes
    # Uses pyshp (pure Python). Fetches WKB via ST_AsBinary(ST_Transform(geom, :srid)).
    # Returns zip bytes (.shp/.dbf/.prj/.shx). Field names truncated to 10 chars.
    # Must run via asyncio.to_thread() — pyshp is sync
async def export_gpkg(shard_db, layer, target_srid) -> bytes
    # Uses fiona with 'GPKG' driver. Must run via asyncio.to_thread() — fiona is sync
async def validate_srid(meta_db, srid) -> bool
    # SELECT 1 FROM spatial_ref_sys WHERE srid = :srid
```

### `api/app/services/stats_service.py`
```python
# In-process TTL cache (dict keyed by layer_id, value={data, expires_at})
_STATS_CACHE: dict[str, dict] = {}
STATS_TTL_SECONDS = 60

async def compute_layer_stats(shard_db, layer_id, json_schema) -> dict
    # Queries:
    # 1. COUNT(*) + geometry type breakdown: GROUP BY ST_GeometryType(geom)
    # 2. ST_XMin/YMin/XMax/YMax of ST_Collect(geom)
    # 3. Per-field stats (loop over json_schema["fields"]):
    #    string:  null_count, unique_count, top 10 values
    #    number:  MIN/MAX/AVG + null_count  (cast properties->>field to ::numeric)
    #    boolean: true_count, false_count, null_count
    # Returns structured dict; caller sets cache entry
```

### `api/app/services/feature_filter.py` (NEW helper)
```python
ALLOWED_OPS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"})

def build_attr_filter_clauses(filters: list[dict], schema_fields: set[str], params: dict) -> list[str]:
    """
    Returns SQL clause strings with named placeholders (:f_0, :v_0, :f_1, :v_1...).
    NEVER uses format()/f-strings to inject field names or values — all go through params dict.
    Raises ValueError if field not in schema_fields or op not in ALLOWED_OPS.
    
    Strategy: field names go as values to properties->>:f_i (parameterized JSONB access).
    """
    # eq:       properties->>:f_i = :v_i
    # ne:       properties->>:f_i <> :v_i
    # gt/gte/lt/lte: (properties->>:f_i)::numeric > :v_i
    # contains: properties->>:f_i ILIKE :v_i  (value gets wrapped in %...%)
    # in:       properties->>:f_i = ANY(ARRAY[:v_i_0, :v_i_1, ...])
```

---

## Modified Backend Files

### `api/app/services/layer_geometry.py` — Three new functions

#### Bug fixed: property-only edits produce no signal
Currently `update_feature()` (features.py:206) only calls `refresh_layer_geometry_types()` when
`body.geom is not None`. A properties-only change produces **zero** layer-level change signal.
The fix: call `refresh_layer_feature_stamp()` on **all** feature mutations unconditionally.

#### `refresh_layer_bbox()` — geometry envelope
Same fire-and-forget pattern as `refresh_layer_geometry_types()`:

```python
async def refresh_layer_bbox(
    layer_id: uuid.UUID,
    shard_db: AsyncSession,
    meta_db: AsyncSession,
) -> list[float] | None:
    try:
        row = await shard_db.execute(
            text("SELECT ST_AsText(ST_Envelope(ST_Collect(geom))) AS wkt "
                 "FROM features WHERE layer_id = CAST(:id AS uuid) AND deleted_at IS NULL"),
            {"id": str(layer_id)},
        )
        wkt = row.scalar_one_or_none()
        if wkt is None:
            await meta_db.execute(
                text("UPDATE layers SET bbox = NULL WHERE id = CAST(:id AS uuid)"),
                {"id": str(layer_id)},
            )
        else:
            await meta_db.execute(
                text("UPDATE layers SET bbox = ST_GeomFromText(:wkt, 4326) "
                     "WHERE id = CAST(:id AS uuid)"),
                {"wkt": wkt, "id": str(layer_id)},
            )
        await meta_db.commit()
        # ... return [xmin, ymin, xmax, ymax] or None
    except Exception as exc:
        logger.warning("refresh_layer_bbox failed for %s: %s", layer_id, exc)
        return None
```

#### `refresh_layer_feature_stamp()` — attribution + timestamp (NEW)
Called on **every** feature mutation — geom or properties. This is the primary change signal.

```python
async def refresh_layer_feature_stamp(
    layer_id: uuid.UUID,
    actor_id: str,          # ctx.user_id — UUID string, stored as UUID FK
    meta_db: AsyncSession,
) -> None:
    """
    Update layers.features_updated_at + features_updated_by.
    Called unconditionally on every feature create/update/delete.
    Fire-and-forget: errors logged, never propagated.
    
    Separated from refresh_layer_geometry_types() so that property-only
    changes (no geom change) still produce a layer-level change signal.
    """
    try:
        await meta_db.execute(
            text("""
                UPDATE layers
                SET features_updated_at = NOW(),
                    features_updated_by = CAST(:actor AS uuid),
                    updated_at = NOW()
                WHERE id = CAST(:id AS uuid)
            """),
            {"actor": actor_id, "id": str(layer_id)},
        )
        await meta_db.commit()
    except Exception as exc:
        logger.warning("refresh_layer_feature_stamp failed for %s: %s", layer_id, exc)
```

**Call sites in `api/app/routers/features.py`** — updated call pattern for all four mutation endpoints:

```python
# create_feature, delete_feature, bulk_delete_features:
await refresh_layer_geometry_types(layer_id, shard_db, meta_db)
await refresh_layer_bbox(layer_id, shard_db, meta_db)
await refresh_layer_feature_stamp(layer_id, ctx.user_id, meta_db)   # NEW — always

# update_feature (FIXED — was only calling on geom change):
if body.geom is not None:
    await refresh_layer_geometry_types(layer_id, shard_db, meta_db)
    await refresh_layer_bbox(layer_id, shard_db, meta_db)
# Always — even for property-only edits:
await refresh_layer_feature_stamp(layer_id, ctx.user_id, meta_db)   # NEW
```

After `refresh_layer_feature_stamp()` completes, fire-and-forget:
```python
asyncio.create_task(refresh_map_content_for_layer(layer_id, ctx.user_id, meta_db))
```

#### `refresh_map_content_for_layer()` in `map_service.py` — propagate to maps (NEW)
```python
async def refresh_map_content_for_layer(layer_id: uuid.UUID, actor_id: str, meta_db: AsyncSession) -> None:
    """
    Fire-and-forget: bump content_version + content_updated_at + content_updated_by
    on all maps that contain this layer. Also invalidates Redis mapfresh: keys.
    Uses layermaps:{layer_id} Redis set as a fast lookup before hitting the DB.
    """
    try:
        # 1. Get map_ids from Redis reverse index (populated when layer added to map)
        map_ids = await redis.smembers(f"layermaps:{layer_id}")
        if not map_ids:
            # Cold cache: query DB
            rows = await meta_db.execute(
                text("SELECT map_id FROM map_layers WHERE layer_id = CAST(:lid AS uuid)"),
                {"lid": str(layer_id)},
            )
            map_ids = {str(r[0]) for r in rows}
            if map_ids:
                await redis.sadd(f"layermaps:{layer_id}", *map_ids)
                await redis.expire(f"layermaps:{layer_id}", 3600)
        # 2. Bump all affected maps
        for mid in map_ids:
            await meta_db.execute(
                text("""
                    UPDATE maps
                    SET content_version    = content_version + 1,
                        content_updated_at = NOW(),
                        content_updated_by = CAST(:actor AS uuid)
                    WHERE id = CAST(:mid AS uuid)
                """),
                {"actor": actor_id, "mid": mid},
            )
            await cache_delete(f"mapfresh:{mid}")
        await meta_db.commit()
    except Exception as exc:
        logger.warning("refresh_map_content_for_layer failed for %s: %s", layer_id, exc)
```

### `api/app/schemas/layers.py` — Add bbox to LayerResponse

```python
bbox: list[float] | None = None  # [lon_min, lat_min, lon_max, lat_max]
```

The router must query `ST_XMin(bbox), ST_YMin(bbox), ST_XMax(bbox), ST_YMax(bbox)` as additional columns alongside the ORM object (since GeoAlchemy2 returns WKB, not a list). Use a raw text query or `hybrid_property`.

### `api/app/routers/features.py` — Advanced Queries

New query params on `list_features()`:

```python
# Spatial predicate (new)
spatial_op: Optional[str] = None          # intersects|within|contains|dwithin
filter_geojson: Optional[str] = None      # GeoJSON geometry string (validated before use)
filter_distance_m: Optional[float] = None # for dwithin only

# Attribute filter (new)
attr_filter: Optional[str] = None         # JSON: [{"field":"status","op":"eq","value":"active"}]

# Geometry simplification (new)
zoom: Optional[int] = Query(None, ge=0, le=22)

# CRS reprojection (new)
srid: Optional[int] = None                # target EPSG code; validate against spatial_ref_sys
```

**Spatial predicate SQL fragments** (all parameterized, no user values in SQL text):
```python
SPATIAL_CLAUSES = {
    "intersects": "ST_Intersects(geom, ST_GeomFromGeoJSON(:filter_geom))",
    "within":     "ST_Within(geom, ST_GeomFromGeoJSON(:filter_geom))",
    "contains":   "ST_Contains(geom, ST_GeomFromGeoJSON(:filter_geom))",
    "dwithin":    "ST_DWithin(geom::geography, ST_GeomFromGeoJSON(:filter_geom)::geography, :dist_m)",
}
```

**Geom column expression** (composable based on params present):
```sql
-- No srid, no zoom:
ST_AsGeoJSON(geom)::jsonb

-- With srid only:
ST_AsGeoJSON(ST_Transform(geom, :target_srid))::jsonb

-- With zoom only (tolerance = 360 / (256 * 2^zoom), apply when zoom < 14):
ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tolerance))::jsonb

-- Both (transform first, then simplify in target CRS):
ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Transform(geom, :target_srid), :tolerance))::jsonb
```

**Attr filter validation flow:**
1. Parse `attr_filter` JSON → return 400 on parse failure
2. Fetch layer's `json_schema.fields` → build `schema_field_names` set
3. Pass to `feature_filter.build_attr_filter_clauses()` → returns 400 on unknown field or op

### `api/app/routers/layers.py` — New Endpoints

Add at end of existing router:

```
GET /layers/{layer_id}/export
    Query: format=geojson|shapefile|gpkg, srid=<int>
    Permission: can_user_do(..., "export")  (editor+ role)
    Validates srid against spatial_ref_sys
    Returns StreamingResponse (geojson) or Response (shapefile/gpkg binary)
    Content-Disposition: attachment; filename="<layer_name>.<ext>"

GET /layers/{layer_id}/stats
    Permission: can_user_do(..., "read")
    Returns cached (60s) stats dict (in-process TTL dict in stats_service)

GET /layers/{layer_id}/versions
    Query: limit=50, offset=0
    Returns list[VersionListItem]

GET /layers/{layer_id}/versions/{version}
    Returns VersionDetail (includes full snapshot)

POST /layers/{layer_id}/versions/{version}/restore
    Permission: can_user_do(..., "write")
    Restores layer metadata to snapshot, records new version
    Returns VersionRestoreResponse
```

**Version recording in `update_layer()`:**
```python
LAYER_VERSION_FIELDS = ["name", "description", "status", "srid", "tags", "sort_order"]
# Before commit: capture old snapshot, detect changed_fields, call record_version()
# within the same transaction — no separate commit
```

### `api/app/routers/maps.py` (NEW file)

```
POST   /maps                               Create map → creator auto-gets implicit admin
GET    /maps?database_id=                  List accessible maps (filtered)
GET    /maps/{id}                          Get map
PUT    /maps/{id}                          Update metadata → triggers record_version()
DELETE /maps/{id}                          Soft delete

GET    /maps/{id}/open                     Full tree + effective roles in one call
                                           (calls get_map_layer_tree + permission check per layer)

POST   /maps/{id}/groups                   Create group {name, parent_id, sort_order}
GET    /maps/{id}/groups                   Full group tree with nested layers
PUT    /maps/{id}/groups/{gid}             Rename / reorder / reparent group
DELETE /maps/{id}/groups/{gid}             Delete group; layers move to group_id=NULL

POST   /maps/{id}/layers                   Add layer to map {layer_id, group_id?, sort_order?}
DELETE /maps/{id}/layers/{layer_id}        Remove layer from map
PUT    /maps/{id}/layers/{layer_id}        Update visibility / sort_order / group_id

POST   /maps/{id}/groups/{gid}/permissions
    # UI HELPER: expand group recursively → get all layer_ids
    # Bulk-create individual permission rows for each layer
    # Body: {ms_user_id|ms_group_id, role_id, allow}
    # Response: {granted: N, layer_ids: ["uuid1", ...]}
    # This is NOT a new permission entity — it creates standard Permission rows per layer

GET    /maps/{id}/versions
GET    /maps/{id}/versions/{v}
POST   /maps/{id}/versions/{v}/restore

GET    /maps/{id}/freshness?since=<ISO-timestamp>
    # Fast staleness check. Cached in Redis (mapfresh:{map_id}, 30s TTL).
    # Response:
    # {
    #   "map_id": "...",
    #   "content_version": 12,
    #   "content_updated_at": "2025-01-15T10:30:00Z",
    #   "content_updated_by": {id, name},        -- joined from users
    #   "any_change_since": true,
    #   "changed_layers": [
    #     {
    #       "layer_id": "...",
    #       "name": "Roads",
    #       "features_updated_at": "2025-01-15T09:00:00Z",
    #       "features_updated_by": {id, name},    -- joined from users
    #       "metadata_updated_at": "2025-01-14T12:00:00Z",
    #       "metadata_updated_by": {id, name}
    #     }
    #   ]
    # }
    # SQL:
    # SELECT l.id, l.name, l.features_updated_at, l.features_updated_by,
    #        l.updated_at, l.updated_by,
    #        u1.display_name as feat_editor, u2.display_name as meta_editor
    # FROM map_layers ml
    # JOIN layers l ON l.id = ml.layer_id
    # LEFT JOIN users u1 ON u1.id = l.features_updated_by
    # LEFT JOIN users u2 ON u2.id = l.updated_by
    # WHERE ml.map_id = :map_id
    #   AND l.deleted_at IS NULL
    #   AND (l.features_updated_at > :since OR l.updated_at > :since)
    # Uses index: layers_features_updated_at_idx
```

**ETag on `GET /maps/{id}/open`:**

```python
# In router handler:
etag = f'"{map_id}-{map.content_version}-{int(max_features_ts.timestamp())}"'
if request.headers.get("If-None-Match") == etag:
    return Response(status_code=304)
response.headers["ETag"] = etag
response.headers["Last-Modified"] = http_date(map.content_updated_at)
```

Client sends `If-None-Match: "abc-12-1705312200"` on next open → 304 No Content if nothing changed. Eliminates the full tree assembly + permission resolution on cache hit.

**`GET /maps/{id}/open` response shape:**
```json
{
  "map": {"id": "...", "name": "...", "extent": [34.0, 29.5, 36.0, 33.5]},
  "tree": [
    {
      "type": "group",
      "id": "...",
      "name": "Base Layers",
      "sort_order": 0,
      "is_expanded": true,
      "children": [
        {
          "type": "layer",
          "map_layer_id": "...",
          "layer_id": "...",
          "name": "Roads",
          "sort_order": 0,
          "is_visible": true,
          "srid": 4326,
          "geometry_types": ["LINESTRING"],
          "bbox": [34.0, 29.5, 36.0, 33.5],
          "effective_role": "editor"
        }
      ]
    },
    {
      "type": "layer",
      "map_layer_id": "...",
      "layer_id": "...",
      "group_id": null,
      "name": "Survey Points",
      ...
    }
  ]
}
```

**`POST /maps/{id}/groups/{gid}/permissions` response:**
```json
{"granted": 5, "layer_ids": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"]}
```

### `api/app/main.py`

```python
from app.routers import maps
app.include_router(maps.router)
```

---

## Requirements Changes

Add to `api/requirements.txt`:
```
pyshp==2.3.1        # pure-Python shapefile writer, zero system deps
fiona==1.9.6        # GPKG export; wraps GDAL (already present in PostGIS Docker image)
redis[asyncio]==5.0.4  # async Redis client (replaces unused redis_url config)
```

---

## Frontend Changes

### `web/src/types/index.ts`

Add:
```typescript
export interface GeoMap {
  id: string;
  name: string;
  description: string | null;
  database_id: string;
  extent: [number, number, number, number] | null;  // [lon_min, lat_min, lon_max, lat_max]
  created_at: string;
  updated_at: string;
}

export interface MapGroup {
  id: string;
  map_id: string;
  parent_id: string | null;
  name: string;
  sort_order: number;
  is_expanded: boolean;
}

export interface MapLayerEntry {
  type: 'layer';
  map_layer_id: string;
  layer_id: string;
  name: string;
  group_id: string | null;
  sort_order: number;
  is_visible: boolean;
  srid: number;
  geometry_types: string[];
  bbox: [number, number, number, number] | null;
  effective_role?: string;  // only in /open response
}

export interface MapTreeNode {
  type: 'group' | 'layer';
  id: string;
  name: string;
  sort_order: number;
  // group only:
  is_expanded?: boolean;
  children?: MapTreeNode[];
  // layer only:
  map_layer_id?: string;
  layer_id?: string;
  group_id?: string | null;
  is_visible?: boolean;
  srid?: number;
  geometry_types?: string[];
  bbox?: [number, number, number, number] | null;
  effective_role?: string;
}

export type FieldStat =
  | { type: 'string'; null_count: number; unique_count: number; top_values: {value: string; count: number}[] }
  | { type: 'number'; min: number | null; max: number | null; avg: number | null; null_count: number }
  | { type: 'boolean'; true_count: number; false_count: number; null_count: number };

export interface LayerStats {
  layer_id: string;
  total_count: number;
  geometry_type_counts: Record<string, number>;
  bbox: [number, number, number, number] | null;
  field_stats: Record<string, FieldStat>;
}
```

Update existing `Layer` interface:
```typescript
bbox: [number, number, number, number] | null;  // add this field
```

### `web/src/api/maps.ts` (NEW)

```typescript
import client from './client';
import type { GeoMap, MapGroup, MapTreeNode, MapLayerEntry } from '../types';

export const maps = {
  list: (databaseId: string) =>
    client.get<GeoMap[]>(`/maps?database_id=${databaseId}`).then(r => r.data),
  create: (data: Pick<GeoMap, 'name' | 'description' | 'database_id'>) =>
    client.post<GeoMap>('/maps', data).then(r => r.data),
  get: (id: string) => client.get<GeoMap>(`/maps/${id}`).then(r => r.data),
  update: (id: string, data: Partial<GeoMap>) =>
    client.put<GeoMap>(`/maps/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/maps/${id}`),
  open: (id: string) =>
    client.get<{map: GeoMap; tree: MapTreeNode[]}>(`/maps/${id}/open`).then(r => r.data),
  createGroup: (mapId: string, data: {name: string; parent_id?: string; sort_order?: number}) =>
    client.post<MapGroup>(`/maps/${mapId}/groups`, data).then(r => r.data),
  updateGroup: (mapId: string, groupId: string, data: Partial<MapGroup>) =>
    client.put<MapGroup>(`/maps/${mapId}/groups/${groupId}`, data).then(r => r.data),
  deleteGroup: (mapId: string, groupId: string) =>
    client.delete(`/maps/${mapId}/groups/${groupId}`),
  addLayer: (mapId: string, layerId: string, groupId?: string, sortOrder?: number) =>
    client.post(`/maps/${mapId}/layers`, {layer_id: layerId, group_id: groupId, sort_order: sortOrder}),
  removeLayer: (mapId: string, layerId: string) =>
    client.delete(`/maps/${mapId}/layers/${layerId}`),
  grantGroupPermissions: (mapId: string, groupId: string, data: object) =>
    client.post<{granted: number; layer_ids: string[]}>(`/maps/${mapId}/groups/${groupId}/permissions`, data),
};

export const layerExport = {
  url: (layerId: string, format: 'geojson' | 'shapefile' | 'gpkg', srid?: number) => {
    const token = localStorage.getItem('token');
    const base = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/layers/${layerId}/export?format=${format}`;
    return srid ? `${base}&srid=${srid}&token=${token}` : `${base}&token=${token}`;
  },
};

export const layerStats = {
  get: (layerId: string) =>
    client.get<LayerStats>(`/layers/${layerId}/stats`).then(r => r.data),
};
```

### New component: `web/src/components/maps/MapGroupTree.tsx`

A recursive Ant Design tree renderer:
- Group nodes: folder icon, expand/collapse toggle (local state overrides `is_expanded`), kebab menu with "Add sub-group", "Rename", "Delete", "Grant permissions"
- Layer nodes: colored geometry icon, layer name, visibility eye toggle, "Edit" button, "Export" dropdown (GeoJSON/Shapefile/GeoPackage)
- Drag-and-drop reordering (Ant Design `Tree` with `draggable`) → `PUT /maps/{id}/layers/{lid}` or `PUT /maps/{id}/groups/{gid}` with new sort_order/parent_id

### `web/src/pages/MapPage.tsx` — Major Refactor

Left sidebar additions:
1. After database selector: **Map selector** (`<Select>` listing maps via `GET /maps?database_id=`)
2. Replace flat layer list with **`<MapGroupTree>`** component populated from `GET /maps/{id}/open`
3. "Add Group" button at top of tree panel
4. "Manage Layers" button → opens layer picker modal (`GET /layers?database_id=` → drag to add)

**Group permission modal:** When "Grant permissions" clicked on a group:
1. Call `POST /maps/{id}/groups/{gid}/permissions` with `dry_run=true` (or just read the response)
2. Show modal: "Grant {role} to {N} layers: [Layer A, Layer B, ...]"
3. On Confirm → POST executes, show success toast

**Map extent auto-zoom:** When map is opened, if `map.extent` is non-null, call `mapInstance.fitBounds(extent)`.

### New page: `web/src/pages/MapsPage.tsx`

Simple CRUD page: list maps per database, create/rename/delete maps. Route: `/maps-admin`. Add to `Sidebar.tsx` nav.

### `web/src/pages/LayerDetailPage.tsx` — Export + Stats

Add export section:
```tsx
<Space>
  <Button onClick={() => window.open(layerExport.url(id, 'geojson'))}>Export GeoJSON</Button>
  <Button onClick={() => window.open(layerExport.url(id, 'shapefile'))}>Export Shapefile</Button>
  <Button onClick={() => window.open(layerExport.url(id, 'gpkg'))}>Export GeoPackage</Button>
</Space>
```

Add stats collapsible panel:
- Feature count + geometry type pills
- Field stats table (field name | type | key stats)

---

## Implementation Order (Dependency Graph)

```
Step 1  Migration 007 — maps (+ content_version/content_updated_at/content_updated_by),
                         map_groups (+ embedded_map_id), map_layers (+ filter_expression)
Step 2  Migration 008 — resource_versions, next_resource_version()
Step 3  Migration 009 — layers change-tracking columns (features_updated_at,
                         features_updated_by, updated_by) + index
Step 4  Migration 010 — saved_expressions table
Step 5  Migration 002f — feature stats indexes (features DB)
Step 6  requirements.txt — add pyshp, fiona, redis[asyncio]
Step 7  cache.py — Redis client module (get_redis, cache_get, cache_set, cache_delete_pattern)
Step 8  auth/local.py — wire Redis into _resolve_custom_group_ids() + last_seen debounce
Step 9  layer_geometry.py — add refresh_layer_bbox() + refresh_layer_feature_stamp()
         [BUG FIX] features.py update_feature() — call refresh_layer_feature_stamp()
         unconditionally (not just on geom change); call refresh_layer_bbox() alongside
         refresh_layer_geometry_types() at all 4 mutation sites
Step 10 schemas/layers.py — add bbox + features_updated_at + features_updated_by to LayerResponse
Step 11 feature_filter.py — compile_expression() DSL (injection-safe, recursive, depth-limited)
Step 12 features.py — add zoom, srid, spatial_op, expression/expression_id params
Step 13 models/maps.py + schemas/maps.py + models/versions.py + schemas/versions.py
Step 14 services/map_service.py — CRUD + embedded map resolution + circular-ref check
                                 + refresh_map_content_for_layer() + freshness query
                                 + layermaps:{layer_id} Redis set maintenance
Step 15 routers/maps.py + main.py — all map endpoints incl. /freshness + ETag on /open
Step 16 services/version_service.py
Step 17 routers/layers.py — version endpoints + record_version() in update_layer()
         (record changed_by = ctx.user_id; snapshot includes updated_by)
Step 18 routers/maps.py — version endpoints + record_version() in update_map()
Step 19 routers/layers.py — /expressions CRUD endpoints
Step 20 services/export_service.py
Step 21 routers/layers.py — /export endpoint
Step 22 services/stats_service.py (depends on step 5 for indexes; cached in Redis)
Step 23 routers/layers.py — /stats endpoint
Step 24 Frontend: types/index.ts additions
Step 25 Frontend: api/maps.ts + api/expressions.ts new modules
Step 26 Frontend: MapGroupTree.tsx (group + embedded-map + layer nodes; freshness indicator)
Step 27 Frontend: MapPage.tsx refactor (map selector + group tree + expression builder)
Step 28 Frontend: MapsPage.tsx + route + sidebar
Step 29 Frontend: LayerDetailPage.tsx export + stats + saved expressions + version history
```

Steps 1–5 are migrations and can be written in parallel. Step 6 (requirements) unblocks step 7 (cache). Step 9 (layer_geometry) is the critical bug fix and unblocks step 14 (map content propagation). Steps 11–12 are independent of 13–15.

---

## Verification

### Layer Bbox
1. Create a feature → `GET /layers/{id}` → `bbox` is `[lon_min, lat_min, lon_max, lat_max]`
2. Delete all features → `bbox` is `null`
3. Regression: `geometry_types` still updates correctly alongside `bbox`

### Map Layer Groups
1. Create map → POST group "Roads" → POST sub-group "Highways" → add 2 layers to "Highways"
2. `GET /maps/{id}/open` → assert tree structure: Roads > Highways > [Layer A, Layer B]
3. `POST /maps/{id}/groups/{highways_id}/permissions` → assert `granted=2`, both layers get individual permission rows

### Advanced Feature Queries
- **Injection test**: `attr_filter=[{"field":"'; DROP TABLE features; --","op":"eq","value":"x"}]` → 400 (field not in schema), no SQL executed
- **Spatial within**: Insert 3 features, query with `spatial_op=within&filter_geojson=<polygon surrounding 2>` → 2 returned
- **Attribute filter**: Insert features with `status=active/inactive`, query `op=eq value=active` → only active returned
- **Zoom simplify**: `zoom=5` → fewer vertices than `zoom=14` for same polygon layer

### Export
- `?format=geojson` → valid FeatureCollection JSON, `Content-Disposition: attachment`
- `?format=shapefile` → unzip → 4 files, parse with pyshp, assert feature count matches
- `?format=gpkg` → open with fiona → same feature count
- `?format=geojson&srid=32636` → coordinates in UTM range, not lat/lon range

### Version History
- PUT /layers/{id} → assert `resource_versions` has row, `changed_fields` matches what changed
- GET /layers/{id}/versions → sorted DESC by changed_at
- POST /layers/{id}/versions/1/restore → name reverts, new version row with `message="Restored from v1"`
- **Race condition**: two concurrent PUTs → no duplicate version numbers (FOR UPDATE in `next_resource_version`)

### Stats
- Insert 10 features with known properties → `GET /layers/{id}/stats` → assert counts, min/max/avg match
- Call twice within 60s → same response (cache hit)

### CRS Reprojection
- `GET /{layer_id}/features?srid=32636` → assert coordinates are not in [-180,180] lat/lon range
- Invalid srid `99999` → 400 with clear error message

### Change Tracking & Freshness
- **Properties-only edit (BUG FIX)**: `PUT /layers/{id}/features/{fid}` with only `properties` changed (no `geom`) → `layers.features_updated_at` updates, `layers.features_updated_by` = current user
- **Geom edit**: `PUT` with geom changed → both `features_updated_at` AND `layers.geometry_types` AND `layers.bbox` all update
- **Map propagation**: after any feature mutation, all maps containing that layer get `content_version` incremented and `content_updated_by` = current user within 1s
- **Freshness endpoint**: `GET /maps/{id}/freshness?since=<3h ago>` → `changed_layers` lists only layers edited in that window, each with `features_updated_by.name`
- **Version history attribution**: `PUT /layers/{id}` → `resource_versions` row has `changed_by` = actor UUID; `GET /layers/{id}/versions` returns list with contributor names
- **ETag**: open map → note ETag header; open again without changes → 304; edit a feature → ETag changes on next open
- **Redis reverse index**: add layer L to maps A and B → `smembers layermaps:{L}` = {A, B}; edit a feature in L → both `mapfresh:A` and `mapfresh:B` invalidated

### Embedded Maps
- Create Map A with layers L1, L2. Create Map B, embed Map A as a group in Map B.
- `GET /maps/B/open` → tree contains group node `{type:"embedded_map", embedded_map_id: A_id}` with L1, L2 nested inside, subject to user's permissions on Map A
- User with no access to Map A → embedded group shows empty / hidden
- Circular embed: try `POST /maps/A/groups {embedded_map_id: A_id}` → 400 (self-embed blocked by DB constraint)
- Chain: B embeds A, try to embed B into A → 400 (cycle detected at API level)

### Dynamic Expressions
- POST expression `{"op":"AND","conditions":[{"field":"status","op":"eq","value":"active"},{"field":"pop","op":"gt","value":1000}]}` → saved, returns expression_id
- `GET /{layer_id}/features?expression_id={eid}` → only features matching both conditions returned
- Inline: `?expression={"field":"name","op":"starts_with","value":"Road"}` → filtered results
- Map-layer filter: add layer to map with `filter_expression` set → all feature fetches for that layer in that map auto-apply the filter
- Injection attempt: expression with `"op":"raw_sql"` (unknown op) → 400
- Deeply nested expression (depth > 10) → 400

### Caching
- Cold start: `GET /layers/{id}/features` for authenticated user → check Redis `groups:{user_id}` is populated after first call
- Warm: second request within 5min → no recursive CTE query executed (confirm via DB query count)
- `last_seen_at` debounce: 10 requests in 30s → only 1 DB UPDATE for last_seen_at
- Map tree: `GET /maps/{id}/open` twice in 30s → Redis hit on second call
- Stats: `GET /layers/{id}/stats` twice in 60s → Redis hit on second call
- Cache invalidation: change group membership → Redis key `groups:{user_id}` deleted → next request re-runs CTE

---

## 9. Embedded Maps

### Concept
A map can be embedded inside another map as a special group node. When a user opens the parent map, the embedded map's full layer tree appears nested under that group — subject to the user's permissions **on the embedded map** (not the parent map).

This lets teams compose maps from reusable "sub-maps" without duplicating layer memberships or permission grants.

```
Map "National Overview"
  ├── Group "Tel Aviv Region"   ← regular group
  │    └── Layer "TLV Roads"
  └── [Embedded: Map "Jerusalem Survey"]   ← embedded map group
       ├── Group "Historic Sites"
       │    └── Layer "Ottoman Boundaries"
       └── Layer "Survey Points"
```

### DB Changes
`map_groups.embedded_map_id UUID REFERENCES maps(id)` (already added to migration 007 above).

Rules:
- `embedded_map_id` and `name` are mutually exclusive — when `embedded_map_id` is set, the group name is derived from the embedded map's name (overridable)
- Layers from embedded maps are NOT duplicated in `map_layers` — they are resolved at query time
- Max embedding depth: **5 levels** (enforced at API level in `map_service.py`)

### Permission Logic
When resolving `GET /maps/{id}/open` and a group has `embedded_map_id`:

```python
async def resolve_embedded_map_node(db, embedded_map_id, user_id, group_ids, depth=0):
    if depth > 5:
        return None   # too deep, skip silently
    # 1. Check user has viewer+ on the embedded map
    role = await get_effective_role(db, user_id, group_ids, "map", embedded_map_id)
    if role is None:
        return {"type": "embedded_map", "access": False, "children": []}
    # 2. Recursively resolve the embedded map's tree (same permission logic)
    #    Cached in Redis under maptree:{embedded_map_id}:{user_id}
    tree = await get_map_layer_tree_for_user(db, embedded_map_id, user_id, group_ids, depth+1)
    return {"type": "embedded_map", "embedded_map_id": str(embedded_map_id),
            "access": True, "children": tree}
```

Key: permission on individual layers inside the embedded map is **still per-layer** — the map access check is just a gate. A user with map access + no layer permissions sees an empty embedded map.

### Circular Reference Protection
In `map_service.create_map_group()` when `embedded_map_id` is set:
```python
async def _check_embed_cycle(db, parent_map_id, embedded_map_id, depth=0):
    if depth > 5:
        raise ValueError("Maximum embedding depth exceeded")
    if embedded_map_id == parent_map_id:
        raise ValueError("A map cannot embed itself")
    # Walk all groups of embedded_map_id that also have embedded_map_ids
    # and check none of them point back to parent_map_id
    child_embeds = await db.execute(
        text("SELECT embedded_map_id FROM map_groups WHERE map_id = :mid AND embedded_map_id IS NOT NULL"),
        {"mid": embedded_map_id}
    )
    for (child_embed_id,) in child_embeds:
        await _check_embed_cycle(db, parent_map_id, child_embed_id, depth+1)
```

### API Changes
`POST /maps/{id}/groups` body — add optional field:
```json
{"name": "Jerusalem Survey (embedded)", "embedded_map_id": "uuid-of-map-b", "sort_order": 1}
```

`GET /maps/{id}/open` tree node for embedded map:
```json
{
  "type": "embedded_map",
  "id": "map_group_uuid",
  "name": "Jerusalem Survey",
  "embedded_map_id": "uuid-of-embedded-map",
  "sort_order": 1,
  "is_expanded": true,
  "access": true,
  "children": [...]   // full resolved tree of embedded map, filtered by user permissions
}
```

### Frontend: `MapGroupTree.tsx`
Embedded map nodes render with a distinct icon (e.g., stacked-maps icon). Clicking the node name navigates to the embedded map. Children render identically to regular group children but are read-only from the parent map's perspective (can't reorder or remove layers from within the parent).

---

## 10. Dynamic Custom Expressions

### Concept
Instead of fixed query parameters (`op=eq`, etc.), users can build, save, and reuse **named filter expressions** using a structured DSL. Expressions can also be attached to a layer in a specific map context (`map_layers.filter_expression`), automatically filtering features when that map is opened.

### Expression DSL

A JSON tree with two node types:

**Leaf (condition):**
```json
{"field": "status", "op": "eq", "value": "active"}
```

**Branch (boolean combinator):**
```json
{
  "op": "AND",
  "conditions": [
    {"field": "status", "op": "eq", "value": "active"},
    {
      "op": "OR",
      "conditions": [
        {"field": "population", "op": "gt", "value": 1000},
        {"field": "area_km2", "op": "between", "lo": 10, "hi": 100}
      ]
    }
  ]
}
```

**Supported leaf ops:**

| op | SQL | Notes |
|----|-----|-------|
| `eq` | `properties->>:f = :v` | |
| `ne` | `properties->>:f <> :v` | |
| `gt` / `gte` / `lt` / `lte` | `(properties->>:f)::numeric > :v` | Casts to numeric |
| `between` | `(properties->>:f)::numeric BETWEEN :lo AND :hi` | Uses `lo`+`hi` keys |
| `contains` | `properties->>:f ILIKE :v` | Value auto-wrapped in `%…%` |
| `starts_with` | `properties->>:f ILIKE :v` | Value gets `%` suffix |
| `ends_with` | `properties->>:f ILIKE :v` | Value gets `%` prefix |
| `in` | `properties->>:f = ANY(ARRAY[:v0, :v1, ...])` | Value is array |
| `not_in` | `properties->>:f <> ALL(ARRAY[:v0, :v1, ...])` | |
| `is_null` | `properties->>:f IS NULL` | No `value` key |
| `is_not_null` | `properties->>:f IS NOT NULL` | No `value` key |

**Security rules in `compile_expression()`:**
- Field names are **never interpolated into SQL** — always accessed as `properties->>:f_N` where `:f_N` is a named parameter bound to the field name string
- All values go through named params dict
- Unknown `op` → `ValueError` → 400
- `field` not in layer's JSON schema fields → `ValueError` → 400
- Max expression depth: 10 levels (protects against stack overflow)
- Max total conditions: 50

### `api/app/services/feature_filter.py` — Updated

```python
ALLOWED_OPS = frozenset({
    "eq", "ne", "gt", "gte", "lt", "lte",
    "between", "contains", "starts_with", "ends_with",
    "in", "not_in", "is_null", "is_not_null",
})
BOOL_OPS = frozenset({"AND", "OR"})

def compile_expression(
    expr: dict,
    schema_fields: set[str],
    params: dict,
    prefix: str = "e",
    depth: int = 0,
) -> str:
    """
    Recursively compiles DSL expression tree to a parameterized SQL clause.
    Returns a string like: "(properties->>:e_f0 = :e_v0 AND (properties->>:e_f1)::numeric > :e_v1)"
    All user-controlled values and field names go through `params` dict — never formatted in.
    Raises ValueError on unknown op, unknown field, or depth > 10.
    """
    if depth > 10:
        raise ValueError("Expression too deeply nested (max 10)")
    op = expr.get("op")
    if op in BOOL_OPS:
        conditions = expr.get("conditions", [])
        if not conditions:
            raise ValueError("Boolean node must have at least one condition")
        parts = [compile_expression(c, schema_fields, params, prefix, depth+1) for c in conditions]
        joiner = " AND " if op == "AND" else " OR "
        return f"({joiner.join(parts)})"
    # Leaf node
    if op not in ALLOWED_OPS:
        raise ValueError(f"Unknown op: {op!r}")
    field = expr.get("field")
    if field not in schema_fields:
        raise ValueError(f"Unknown field: {field!r}")
    idx = len(params)
    f_key = f"{prefix}_f{idx}"
    v_key = f"{prefix}_v{idx}"
    params[f_key] = field
    # ... build clause per op, always using params[v_key] for values
```

### Saved Expressions API

```
POST   /layers/{id}/expressions          Create named expression
GET    /layers/{id}/expressions          List (id, name, description, created_at)
GET    /layers/{id}/expressions/{eid}    Get full expression JSON
PUT    /layers/{id}/expressions/{eid}    Update (validates DSL before saving)
DELETE /layers/{id}/expressions/{eid}   Delete (cascades from layer delete via FK)
```

All require viewer+ on the layer to read, editor+ to write.

### Feature Query Integration

Two new params on `GET /{layer_id}/features`:
```python
expression_id: Optional[uuid.UUID] = None   # use a saved expression by ID
expression:    Optional[str] = None          # inline expression JSON string
```

Precedence: `expression_id` > `expression` > `attr_filter` (original param, kept for backwards compatibility).

Resolution:
```python
if expression_id:
    # 1. Fetch from Redis cache (key: expr:{expression_id}, TTL 5min)
    # 2. Fallback: SELECT expression FROM saved_expressions WHERE id = :eid AND layer_id = :lid
    expr_dict = await get_saved_expression(db, expression_id, layer_id)
elif expression:
    expr_dict = json.loads(expression)   # validated before use
else:
    expr_dict = None   # fall through to attr_filter

if expr_dict:
    clause = compile_expression(expr_dict, schema_field_names, params)
    extra_filters.append(f"AND ({clause})")
```

### Map-Layer Filter Expression

When adding a layer to a map (`POST /maps/{id}/layers`), optionally include:
```json
{"layer_id": "...", "group_id": "...", "filter_expression": {"field": "status", "op": "eq", "value": "published"}}
```

This filter is stored in `map_layers.filter_expression` and automatically applied whenever features from that layer are fetched in the context of this map. The `GET /maps/{id}/open` response includes `filter_expression` per layer entry so the frontend knows the layer is filtered.

Frontend expression builder component (`web/src/components/maps/ExpressionBuilder.tsx`):
- Nested AND/OR group builder (Ant Design `Space` + dynamic form)
- Field selector (dropdown of layer schema fields)
- Op selector (changes based on field type — number fields show gt/lt, string fields show contains, etc.)
- Value input (type-aware: number spinner, text input, multi-select for `in`)
- "Save as..." button → calls POST /layers/{id}/expressions
- "Load saved" button → lists saved expressions for the layer

---

## 11. Caching Strategy

### Current State
Redis is **configured** (`redis_url` in `config.py`) but **never used**. The most expensive uncached operation is `_resolve_custom_group_ids()` in `auth/local.py` — a recursive CTE that runs on **every authenticated request**. Additionally, `validate_token()` writes `last_seen_at` to the DB on every request.

### New File: `api/app/cache.py`

```python
import redis.asyncio as aioredis
import json
from app.config import settings

_redis: aioredis.Redis | None = None

async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis

async def cache_get(key: str) -> dict | list | str | None:
    r = await get_redis()
    val = await r.get(key)
    return json.loads(val) if val is not None else None

async def cache_set(key: str, value, ttl: int) -> None:
    r = await get_redis()
    await r.set(key, json.dumps(value, default=str), ex=ttl)

async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)

async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    keys = await r.keys(pattern)
    if keys:
        await r.delete(*keys)
```

### Cache Registry

| Key pattern | TTL | What's cached | Invalidate when |
|-------------|-----|----------------|-----------------|
| `groups:{user_id}` | 5 min | Result of `_resolve_custom_group_ids()` — list of group ID strings | Group membership changes (`/groups` router add/remove member) |
| `lastseen:{user_id}` | 60 s | Sentinel — presence means we already wrote `last_seen_at` recently | Expires naturally |
| `role:{user_id}:{rtype}:{rid}` | 60 s | Effective role level int or null for a user+resource pair | Permission granted/revoked for that resource |
| `maptree:{map_id}` | 30 s | Flat rows from `get_map_layer_tree()` before Python assembly | Any `map_layers` or `map_groups` change for that map |
| `stats:{layer_id}` | 60 s | Full stats dict from `compute_layer_stats()` | Feature mutation (invalidate on create/update/delete) |
| `expr:{expression_id}` | 5 min | Saved expression JSONB | Expression updated or deleted |
| `valid_srids` | Permanent (in-process frozenset) | All valid EPSG codes from `spatial_ref_sys` | Loaded once at startup |

### Integration Points

**`auth/local.py` — Group membership caching (biggest win):**
```python
async def _resolve_custom_group_ids(db: AsyncSession, user_id) -> list[str]:
    cached = await cache_get(f"groups:{user_id}")
    if cached is not None:
        return cached          # skip the recursive CTE entirely
    # ... existing recursive CTE query ...
    result_list = [row[0] for row in result.all()]
    await cache_set(f"groups:{user_id}", result_list, ttl=300)
    return result_list
```

**`auth/local.py` — `last_seen_at` write debounce:**
```python
# In validate_token(), before the UPDATE:
debounce_key = f"lastseen:{str(user.id)}"
if await cache_get(debounce_key) is None:
    await db.execute(update(User).where(User.id == user.id)
                     .values(last_seen_at=datetime.now(timezone.utc)))
    await db.commit()
    await cache_set(debounce_key, 1, ttl=60)
```

**`services/map_service.py` — Map tree caching:**
```python
async def get_map_layer_tree(db, map_id):
    cached = await cache_get(f"maptree:{map_id}")
    if cached is not None:
        return _assemble_tree(cached)   # assemble from cached flat rows
    rows = await db.execute(text("SELECT * FROM get_map_layer_tree(:mid)"), {"mid": str(map_id)})
    flat = [dict(r) for r in rows.mappings()]
    await cache_set(f"maptree:{map_id}", flat, ttl=30)
    return _assemble_tree(flat)

# Invalidate after any map_layers or map_groups mutation:
await cache_delete(f"maptree:{map_id}")
```

**`services/stats_service.py` — Stats caching (upgrade from in-process dict to Redis):**
```python
async def get_layer_stats(shard_db, meta_db, layer_id, json_schema) -> dict:
    cached = await cache_get(f"stats:{layer_id}")
    if cached is not None:
        return cached
    stats = await compute_layer_stats(shard_db, layer_id, json_schema)
    await cache_set(f"stats:{layer_id}", stats, ttl=60)
    return stats

# Invalidate in features.py after every mutation:
await cache_delete(f"stats:{layer_id}")
```

**SRID validation — In-process frozenset (loaded on startup):**
```python
# In api/app/main.py lifespan:
_valid_srids: frozenset[int] = frozenset()

@asynccontextmanager
async def lifespan(app):
    # ... existing MinIO bucket creation ...
    async with MetaSessionLocal() as db:
        rows = await db.execute(text("SELECT srid FROM spatial_ref_sys"))
        app.state.valid_srids = frozenset(r[0] for r in rows)
    yield

# In routers, replace the DB lookup with:
def validate_srid(srid: int, request: Request) -> bool:
    return srid in request.app.state.valid_srids
```

### Groups Router — Cache Invalidation
In `api/app/routers/groups.py`, after any member add/remove/group-move operation:
```python
# Invalidate group cache for all affected users
user_ids = [affected_user_id]   # or batch if bulk operation
for uid in user_ids:
    await cache_delete(f"groups:{uid}")
```

### Cache Miss Budget
With caching in place, a typical authenticated feature fetch goes from:
- **Before**: 1 JWT decode + 1 user SELECT + 1 `last_seen` UPDATE + 1 recursive CTE + 1 permission check = **5 DB round-trips**
- **After**: 1 JWT decode + 1 user SELECT + Redis GET (groups, cached) + Redis GET (role, cached) = **1 DB round-trip + 2 Redis ops**

On cache hit, Redis latency is ~0.2ms vs ~2–5ms per DB query on pgbouncer.

---

## 12. Identify Layers by Polygon (Spatial Layer Discovery)

### Concept

The user draws a polygon on the map. The system returns **all accessible layers** (with their folder/group hierarchy) annotated with how many features each layer has inside the polygon. The user then picks which layers to load onto the map — clicking "Load" fetches that layer's features filtered to the polygon area.

This is different from a simple filter: it shows ALL layers (including those with 0 features in the area) so the user has the full picture and can decide what to load. Layers with features inside the polygon are highlighted; layers with 0 are shown dimmed.

### Response Shape

```json
{
  "tree": [
    {
      "type": "group",
      "id": "group-layer-uuid",
      "name": "Base Layers",
      "features_in_area": 42,
      "children": [
        {
          "type": "layer",
          "layer_id": "...",
          "name": "Roads",
          "feature_count_in_area": 42,
          "geometry_types": ["LINESTRING"],
          "bbox": [34.0, 29.5, 36.0, 33.5]
        },
        {
          "type": "layer",
          "layer_id": "...",
          "name": "Topography",
          "feature_count_in_area": 0,
          "geometry_types": ["POLYGON"],
          "bbox": null
        }
      ]
    },
    {
      "type": "layer",
      "layer_id": "...",
      "name": "Survey Points",
      "feature_count_in_area": 8,
      "geometry_types": ["POINT"],
      "bbox": [34.1, 30.0, 35.0, 31.0]
    }
  ]
}
```

Hierarchy source: the **existing `group_layer_id` folder system** on the Layer model (the group-layers that already exist in the DB). Layers with no group appear at root level. This works today without any map infrastructure.

When map groups (Step 13) are implemented, an optional `map_id` param can be added to use the map's group tree instead — same endpoint, different hierarchy source.

### What Does NOT Exist Today

- No `POST /layers/identify` endpoint
- No cross-layer spatial query anywhere in the codebase
- `layer_service.py` is empty (marked Phase 4 placeholder)
- No "identify by area" UI mode in MapPage

What DOES exist and is reused:
- `TerraDrawPolygonMode` already wired in MapPage (reuse, no new drawing code)
- `can_user_do()` permission check — same pattern, applied per layer
- `shard_sessions[layer.shard_id]` pattern for feature DB access
- `ST_Intersects` already used in `list_features()` bbox filter
- After user loads a layer: `GET /layers/{id}/features?spatial_op=intersects&filter_geojson=...` (being added in Step 12) — reused to fetch only features inside the polygon

### Backend: `POST /layers/identify`

**New Pydantic schemas** (add to `api/app/schemas/layers.py`):

```python
class LayerIdentifyRequest(BaseModel):
    database_id: uuid.UUID
    geometry: dict            # GeoJSON geometry object

class LayerIdentifyLayerNode(BaseModel):
    type: Literal["layer"] = "layer"
    layer_id: uuid.UUID
    name: str
    feature_count_in_area: int      # 0 if no features in polygon
    geometry_types: list[str]
    bbox: list[float] | None        # [lon_min, lat_min, lon_max, lat_max] of whole layer

class LayerIdentifyGroupNode(BaseModel):
    type: Literal["group"] = "group"
    id: uuid.UUID
    name: str
    features_in_area: int           # sum of children's feature_count_in_area
    children: list[LayerIdentifyLayerNode]

class LayerIdentifyResponse(BaseModel):
    tree: list[LayerIdentifyGroupNode | LayerIdentifyLayerNode]
```

**New endpoint** (add BEFORE any `/{layer_id}` routes in `api/app/routers/layers.py`):

```python
GEOJSON_GEOMETRY_TYPES = frozenset({
    "Point","MultiPoint","LineString","MultiLineString",
    "Polygon","MultiPolygon","GeometryCollection"
})

@router.post("/identify", response_model=LayerIdentifyResponse)
async def identify_layers_by_polygon(
    body: LayerIdentifyRequest,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    # 1. Validate GeoJSON geometry type
    if body.geometry.get("type") not in GEOJSON_GEOMETRY_TYPES:
        raise HTTPException(status_code=400, detail="Invalid GeoJSON geometry type")

    # 2. Load all non-deleted layers for this database (+ their group_layer info)
    result = await meta_db.execute(
        select(Layer).where(
            Layer.database_id == body.database_id,
            Layer.deleted_at.is_(None)
        ).order_by(Layer.sort_order, Layer.name)
    )
    all_layers = result.scalars().all()

    # 3. Filter to layers the user can read
    accessible = []
    for layer in all_layers:
        if await can_user_do(meta_db, ctx, str(layer.id), "read"):
            accessible.append(layer)

    if not accessible:
        return LayerIdentifyResponse(tree=[])

    # 4. Single shard query — COUNT grouped by layer_id, ALL accessible layers
    #    (returns only layers with count > 0; others get count=0 in step 5)
    counts: dict[str, int] = {}
    from collections import defaultdict
    by_shard: dict[int, list] = defaultdict(list)
    for layer in accessible:
        by_shard[layer.shard_id].append(layer)

    for shard_id, shard_layers in by_shard.items():
        shard_ids = [str(l.id) for l in shard_layers]
        try:
            async with shard_sessions[shard_id]() as shard_db:
                rows = await shard_db.execute(
                    text("""
                        SELECT layer_id::text, COUNT(*) AS cnt
                        FROM features
                        WHERE layer_id = ANY(CAST(:ids AS uuid[]))
                          AND deleted_at IS NULL
                          AND ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
                        GROUP BY layer_id
                    """),
                    {"ids": shard_ids, "geom": json.dumps(body.geometry)},
                )
                for row in rows.mappings():
                    counts[row["layer_id"]] = row["cnt"]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid geometry — PostGIS could not parse it")

    # 5. Build tree using existing group_layer_id hierarchy
    #    group_layer_id is the existing folder system on Layer; NULL = root
    groups_seen: dict[str, list] = defaultdict(list)
    root_layers: list = []
    group_layer_ids_needed: set[uuid.UUID] = set()

    for layer in accessible:
        node = LayerIdentifyLayerNode(
            layer_id=layer.id,
            name=layer.name,
            feature_count_in_area=counts.get(str(layer.id), 0),
            geometry_types=layer.geometry_types or [],
            bbox=_bbox_to_list(layer.bbox),
        )
        if layer.group_layer_id:
            groups_seen[str(layer.group_layer_id)].append(node)
            group_layer_ids_needed.add(layer.group_layer_id)
        else:
            root_layers.append(node)

    # 6. Fetch group names for the groups that appear
    tree: list = []
    if group_layer_ids_needed:
        from app.models.layers import GroupLayer   # existing model
        gresult = await meta_db.execute(
            select(GroupLayer).where(GroupLayer.id.in_(group_layer_ids_needed))
        )
        for gl in gresult.scalars().all():
            children = groups_seen[str(gl.id)]
            tree.append(LayerIdentifyGroupNode(
                id=gl.id,
                name=gl.name,
                features_in_area=sum(c.feature_count_in_area for c in children),
                children=children,
            ))

    tree.extend(root_layers)
    return LayerIdentifyResponse(tree=tree)
```

**Routing note:** `POST /layers/identify` MUST appear before any `/{layer_id}` routes. FastAPI matches routes in order and `"identify"` would be parsed as a UUID path param otherwise (failing with 422). Place it immediately after `create_layer`.

### Frontend: MapPage.tsx — Identify Mode

**New state:**
```tsx
const [identifyMode, setIdentifyMode] = useState(false);
const [identifyGeometry, setIdentifyGeometry] = useState<object | null>(null);
const [identifyTree, setIdentifyTree] = useState<IdentifyTreeNode[] | null>(null);
const [identifyLoading, setIdentifyLoading] = useState(false);
const [loadedIdentifyLayers, setLoadedIdentifyLayers] = useState<Set<string>>(new Set());
```

**Toolbar button:** "Identify" button (magnifying glass + area icon) in the map toolbar. Click:
1. `identifyMode = true`
2. Clears previous identify state
3. Switches terra-draw to polygon mode

**Search flow:** After user finishes drawing the polygon, a "Search Layers" button appears (enabled once a polygon exists in the terra-draw snapshot):
```tsx
const handleIdentifySearch = async () => {
    const snapshot = draw.getSnapshot();
    const poly = snapshot.find(f => f.geometry.type === 'Polygon');
    if (!poly) return;
    setIdentifyGeometry(poly.geometry);
    setIdentifyLoading(true);
    try {
        const res = await layersApi.identify(selectedDatabaseId, poly.geometry);
        setIdentifyTree(res.tree);
    } finally {
        setIdentifyLoading(false);
    }
};
```

**Results panel** (replaces normal layer list while in identify mode):
- Header: "Area Search" + total count ("42 features in {N} layers") + "×" to exit mode
- Renders `identifyTree` as a collapsible tree (Ant Design `Tree` or simple custom):
  - Group nodes: folder icon + group name + `features_in_area` badge (gray if 0, blue if > 0)
  - Layer nodes: geometry icon + layer name + `feature_count_in_area` badge (gray if 0, colored if > 0) + **"Load" button**
- Layer nodes with `feature_count_in_area === 0` shown dimmed (opacity: 0.5) but still visible
- "Load" button on a layer node:
  1. Adds layer to `loadedIdentifyLayers` set (button changes to "Loaded ✓")
  2. Fetches features filtered to the polygon: `GET /layers/{id}/features?spatial_op=intersects&filter_geojson={encodeURIComponent(JSON.stringify(identifyGeometry))}`
  3. Adds those features to the map as a new visible layer (same display path as normal layer load)
- "Load All with Data" button at the top: loads every layer with `feature_count_in_area > 0` in one click

**New TypeScript types** in `web/src/types/index.ts`:
```typescript
export interface IdentifyLayerNode {
    type: 'layer';
    layer_id: string;
    name: string;
    feature_count_in_area: number;
    geometry_types: string[];
    bbox: [number, number, number, number] | null;
}

export interface IdentifyGroupNode {
    type: 'group';
    id: string;
    name: string;
    features_in_area: number;
    children: IdentifyLayerNode[];
}

export type IdentifyTreeNode = IdentifyGroupNode | IdentifyLayerNode;

export interface LayerIdentifyResponse {
    tree: IdentifyTreeNode[];
}
```

**New API function** in `web/src/api/layers.ts`:
```typescript
export const identify = (databaseId: string, geometry: object): Promise<LayerIdentifyResponse> =>
    client.post<LayerIdentifyResponse>('/layers/identify', {
        database_id: databaseId,
        geometry,
    }).then(r => r.data);
```

### Implementation Steps (append to existing order)

```
Step 30  schemas/layers.py — add LayerIdentifyRequest, LayerIdentifyLayerNode,
                             LayerIdentifyGroupNode, LayerIdentifyResponse
Step 31  routers/layers.py — add POST /layers/identify (before /{layer_id} routes)
Step 32  Frontend: types/index.ts — add IdentifyLayerNode, IdentifyGroupNode,
                                    IdentifyTreeNode, LayerIdentifyResponse
Step 33  Frontend: api/layers.ts — add identify() function
Step 34  Frontend: MapPage.tsx — identify mode: toolbar button + polygon draw +
                                 results tree panel + Load button per layer
```

Steps 30–31 are fully independent of the map/version work — only need shard sessions (exist today) and `can_user_do` (exists today). Can be implemented in any order relative to steps 1–29.

### Verification

- Create 3 layers in a database: Layer A (10 features inside polygon area), Layer B (0 features), Layer C (5 features). `POST /layers/identify` with polygon → `tree` contains all 3 layers. Layer A has `feature_count_in_area=10`, Layer B has `feature_count_in_area=0`, Layer C has `feature_count_in_area=5`. Layers grouped correctly by `group_layer_id`.
- Layer user cannot read → absent from tree entirely.
- Invalid GeoJSON type (e.g. `"type": "Rectangle"`) → 400 before any DB query.
- Invalid geometry that PostGIS rejects → 400 with clear message.
- Click "Load" on Layer A → features loaded on map filtered to polygon area via `spatial_op=intersects`.
- Click "Load All with Data" → Layer A + Layer C loaded; Layer B skipped.
- "×" button → exits identify mode, clears polygon drawing and results panel.
