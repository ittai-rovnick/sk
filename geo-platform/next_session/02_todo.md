# What Still Needs to Be Implemented

Steps are ordered by dependency. Follow the order — later steps depend on earlier ones.

The full design spec (schema tables, API shapes, permission model, caching, DSL) is at `geo-platform/db_new_design.html` — open in a browser, it has a navigation sidebar.

---

## ~~Step 12 — Advanced Feature Query Params~~ ✅ DONE (see 01_done.md)
## ~~Step 13 — Map Pydantic Schemas~~ ✅ DONE
## ~~Step 14 — Map Service~~ ✅ DONE
## ~~Step 15 — Version Service~~ ✅ DONE
## ~~Step 16 — Maps Router + main.py wiring~~ ✅ DONE (uses /maps/{id}/versions for map version endpoints, satisfies original Step 18 too)
## ~~Step 17 — Layer identify + expression CRUD + version endpoints + groups cache invalidation~~ ✅ DONE
## ~~Step 18 — Export Service (geojson/shapefile/gpkg)~~ ✅ DONE — needs `pip install -r requirements.txt` to pull shapely
## ~~Step 19 — Export endpoint~~ ✅ DONE
## ~~Step 20 — Stats Service~~ ✅ DONE
## ~~Step 21 — Stats endpoint~~ ✅ DONE
## ~~Step 22 — Frontend TypeScript types~~ ✅ DONE
## ~~Step 23 — Frontend API modules (maps + identify + versions + expressions)~~ ✅ DONE
## ~~Step 24 — MapGroupTree component~~ ✅ DONE  (group reparent via DnD is intentionally not wired — toast directs users to the menu)
## ~~Step 25 — ExpressionBuilder component~~ ✅ DONE

---

## Step 12 — Advanced Feature Query Params  (reference, completed)

**File:** `api/app/routers/features.py`
**Function:** `list_features()`

Add these new query parameters:

```python
# Spatial filter
spatial_op: Optional[str] = None           # intersects | within | contains | dwithin
filter_geojson: Optional[str] = None       # GeoJSON geometry string
filter_distance_m: Optional[float] = None  # for dwithin only

# Attribute filter
expression_id: Optional[uuid.UUID] = None  # load saved expression by ID
expression: Optional[str] = None           # inline expression JSON string

# Geometry processing
zoom: Optional[int] = Query(None, ge=0, le=22)   # simplification level
srid: Optional[int] = None                         # target EPSG for reprojection
```

**Spatial clause map** (no user values in SQL strings):
```python
SPATIAL_CLAUSES = {
    "intersects": "ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "within":     "ST_Within(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "contains":   "ST_Contains(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "dwithin":    "ST_DWithin(geom::geography, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326)::geography, :dist_m)",
}
```

**Geom column** — compose based on params:
```sql
-- base:
ST_AsGeoJSON(geom)::jsonb
-- with srid:
ST_AsGeoJSON(ST_Transform(geom, :target_srid))::jsonb
-- with zoom (apply when zoom < 14, tolerance = 360 / (256 * 2^zoom)):
ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tolerance))::jsonb
-- both:
ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Transform(geom, :target_srid), :tolerance))::jsonb
```

**Expression resolution:**
1. If `expression_id` → fetch from Redis `expr:{expression_id}` (TTL 300s), fallback to DB
2. Elif `expression` → `json.loads(expression)` (400 on parse failure)
3. Call `compile_expression(expr_dict, schema_field_names, params)` from `feature_filter.py`
4. Schema fields come from `layer.json_schema["fields"]` (existing column on layers table)

**SRID validation:** Check against `request.app.state.valid_srids` frozenset (loaded at startup in step 23). Return 400 if invalid.

Also: **invalidate stats cache** after every mutation — add `await cache_delete(f"stats:{layer_id}")` alongside the existing `refresh_layer_geometry_types` calls.

---

## Step 13 (remaining) — Map Pydantic Schemas

**File:** `api/app/schemas/maps.py` (new file)

```python
class MapCreate(BaseModel):
    database_id: uuid.UUID
    name: str
    description: str | None = None

class MapUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

class MapResponse(BaseModel):
    id: uuid.UUID
    database_id: uuid.UUID
    name: str
    description: str | None
    extent: list[float] | None  # [lon_min, lat_min, lon_max, lat_max]
    content_version: int
    content_updated_at: datetime
    content_updated_by: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class MapGroupCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None
    embedded_map_id: uuid.UUID | None = None
    sort_order: int = 0

class MapGroupUpdate(BaseModel):
    name: str | None = None
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None
    is_expanded: bool | None = None

class MapGroupResponse(BaseModel):
    id: uuid.UUID
    map_id: uuid.UUID
    parent_id: uuid.UUID | None
    embedded_map_id: uuid.UUID | None
    name: str
    sort_order: int
    is_expanded: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class MapLayerAdd(BaseModel):
    layer_id: uuid.UUID
    group_id: uuid.UUID | None = None
    sort_order: int = 0
    filter_expression: dict | None = None

class MapLayerUpdate(BaseModel):
    group_id: uuid.UUID | None = None
    sort_order: int | None = None
    is_visible: bool | None = None
    filter_expression: dict | None = None

class MapLayerResponse(BaseModel):
    id: uuid.UUID
    map_id: uuid.UUID
    layer_id: uuid.UUID
    group_id: uuid.UUID | None
    sort_order: int
    is_visible: bool
    filter_expression: dict | None
    added_at: datetime
    model_config = {"from_attributes": True}

# Full tree node types for /open response
class MapLayerNode(BaseModel):
    type: Literal["layer"] = "layer"
    map_layer_id: uuid.UUID
    layer_id: uuid.UUID
    name: str
    group_id: uuid.UUID | None
    sort_order: int
    is_visible: bool
    srid: int
    geometry_types: list[str]
    bbox: list[float] | None
    filter_expression: dict | None
    effective_role: str | None = None

class MapGroupNode(BaseModel):
    type: Literal["group"] = "group"
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    is_expanded: bool
    embedded_map_id: uuid.UUID | None
    children: list["MapGroupNode | MapLayerNode"] = []

class MapOpenResponse(BaseModel):
    map: MapResponse
    tree: list[MapGroupNode | MapLayerNode]

class MapFreshnessResponse(BaseModel):
    map_id: uuid.UUID
    content_version: int
    content_updated_at: datetime
    any_change_since: bool
    changed_layers: list[dict]  # see map_service.get_map_freshness()

class GroupPermissionGrantRequest(BaseModel):
    ms_user_id: str | None = None
    ms_group_id: str | None = None
    role_id: uuid.UUID
    allow: bool = True

class GroupPermissionGrantResponse(BaseModel):
    granted: int
    layer_ids: list[uuid.UUID]
```

---

## Step 14 — Map Service

**File:** `api/app/services/map_service.py` (new file)

Key functions to implement:

```python
async def create_map(db, body: MapCreate, actor_id: str) -> Map
async def update_map(db, map_id, body: MapUpdate, actor_id: str) -> Map
async def delete_map(db, map_id, actor_id: str) -> None  # soft delete: deleted_at = now()
async def get_map(db, map_id) -> Map | None

async def get_map_layer_tree(db, map_id) -> list[dict]:
    # 1. Check Redis: cache_get(f"maptree:{map_id}") → if hit, assemble + return
    # 2. Call: SELECT * FROM get_map_layer_tree(:mid) — returns flat rows
    # 3. cache_set(f"maptree:{map_id}", flat_rows, ttl=30)
    # 4. Assemble into nested tree (groups contain children, layers at root)
    # Invalidate maptree:{map_id} after any map_layers or map_groups change

async def create_map_group(db, map_id, body: MapGroupCreate, actor_id: str) -> MapGroup:
    # If body.embedded_map_id: call _check_embed_cycle() first
    # Insert into map_groups
    # Invalidate maptree:{map_id}

async def update_map_group(db, group_id, body: MapGroupUpdate) -> MapGroup
async def delete_map_group(db, group_id) -> None  # layers move to NULL via ON DELETE SET NULL

async def add_layer_to_map(db, map_id, body: MapLayerAdd, actor_id: str) -> MapLayer:
    # Insert into map_layers
    # cache_sadd(f"layermaps:{body.layer_id}", str(map_id), ttl=3600)
    # Invalidate maptree:{map_id}
    # Bump map content_version

async def remove_layer_from_map(db, map_id, layer_id) -> None:
    # Delete from map_layers
    # Remove from Redis set: cache_srem(f"layermaps:{layer_id}", str(map_id))
    # Invalidate maptree:{map_id}

async def update_map_layer(db, map_id, layer_id, body: MapLayerUpdate) -> MapLayer

async def refresh_map_extent(db, map_id) -> None:
    # UPDATE maps SET extent = (
    #   SELECT ST_Envelope(ST_Collect(l.bbox))
    #   FROM map_layers ml JOIN layers l ON l.id = ml.layer_id
    #   WHERE ml.map_id = :map_id AND l.bbox IS NOT NULL AND l.deleted_at IS NULL
    # ) WHERE id = :map_id

async def refresh_map_content_for_layer(layer_id: uuid.UUID, actor_id: str, meta_db) -> None:
    # Fire-and-forget: called from features.py after feature mutations
    # 1. Get map_ids from Redis: cache_smembers(f"layermaps:{layer_id}")
    # 2. If empty: query DB: SELECT map_id FROM map_layers WHERE layer_id = :lid
    #    Populate Redis set: cache_sadd(f"layermaps:{layer_id}", *map_ids, ttl=3600)
    # 3. For each map_id:
    #    UPDATE maps SET content_version=content_version+1, content_updated_at=NOW(),
    #                    content_updated_by=:actor WHERE id=:mid
    #    await cache_delete(f"mapfresh:{mid}")

async def get_map_freshness(db, map_id, since: datetime) -> dict:
    # Check Redis: cache_get(f"mapfresh:{map_id}:{since.isoformat()}")
    # If miss: run SQL query joining map_layers → layers → users (see plan doc)
    # Returns dict matching MapFreshnessResponse

async def expand_group_layers(db, map_id, group_id) -> list[uuid.UUID]:
    # Recursively collect all layer_ids in group + subgroups
    # Used by bulk permission grant endpoint

async def _check_embed_cycle(db, parent_map_id, embedded_map_id, depth=0) -> None:
    # Raises ValueError if cycle detected (self-embed or chain)
    # Max depth: 5
```

**Important:** Call `refresh_map_content_for_layer()` from `features.py` after every feature mutation as `asyncio.create_task(...)` (fire-and-forget).

---

## Step 15 — Maps Router + Register in main.py

**File:** `api/app/routers/maps.py` (new file)

```
POST   /maps                               Create map
GET    /maps?database_id=<uuid>            List maps for a database (exclude deleted)
GET    /maps/{id}                          Get map
PUT    /maps/{id}                          Update metadata
DELETE /maps/{id}                          Soft delete

GET    /maps/{id}/open                     Full tree + effective roles per layer
                                           ETag: "{map_id}-{content_version}-{max_features_ts}"
                                           Returns 304 if If-None-Match matches

GET    /maps/{id}/freshness?since=<ISO>    Changed layers since timestamp (Redis-cached 30s)

POST   /maps/{id}/groups                   Create group
GET    /maps/{id}/groups                   List groups
PUT    /maps/{id}/groups/{gid}             Update group
DELETE /maps/{id}/groups/{gid}             Delete group (layers move to root)

POST   /maps/{id}/layers                   Add layer to map
DELETE /maps/{id}/layers/{layer_id}        Remove layer from map
PUT    /maps/{id}/layers/{layer_id}        Update visibility/sort/group/filter

POST   /maps/{id}/groups/{gid}/permissions
    # Expand group → get all layer_ids → bulk-create Permission rows per layer
    # Returns: {"granted": N, "layer_ids": [...]}

GET    /maps/{id}/versions                 List versions (VersionListItem)
GET    /maps/{id}/versions/{v}             Get version detail (VersionDetail)
POST   /maps/{id}/versions/{v}/restore     Restore map to version v
```

**File:** `api/app/main.py`
- Add `from app.routers import maps` and `app.include_router(maps.router)`
- Add `valid_srids` frozenset loading in lifespan (see Step 23)

**Permissions:** Check `can_user_do()` before every endpoint. Maps use the same `can_user_do` function — pass `"map"` as the resource type string.

---

## Step 16 — Version Service

**File:** `api/app/services/version_service.py` (new file)

```python
async def record_version(
    db, resource_type: str, resource_id: uuid.UUID,
    snapshot: dict, changed_fields: list[str],
    actor_id: str, message: str | None = None
) -> int:
    # 1. Call next_resource_version() SQL function IN THE SAME TRANSACTION
    #    SELECT next_resource_version(:rtype::resource_type, :rid::uuid)
    # 2. INSERT INTO resource_versions (resource_type, resource_id, version, snapshot,
    #                                   changed_fields, message, changed_by)
    # Returns the version number assigned

async def get_versions(
    db, resource_type: str, resource_id: uuid.UUID,
    limit: int = 50, offset: int = 0
) -> list[dict]:
    # SELECT * FROM resource_versions WHERE resource_type=... AND resource_id=...
    # ORDER BY version DESC LIMIT :limit OFFSET :offset

async def get_version(
    db, resource_type: str, resource_id: uuid.UUID, version: int
) -> dict | None:
    # SELECT * FROM resource_versions WHERE ... AND version=:version

async def restore_version(
    db, resource_type: str, resource_id: uuid.UUID,
    version: int, actor_id: str
) -> dict:
    # 1. Fetch snapshot at :version → 404 if not found
    # 2. Apply snapshot fields to live row (UPDATE layers or maps)
    # 3. Record new version with message="Restored from v{version}"
    # 4. Return {"version": new_version, "message": "Restored from v{version}"}
```

**Important:** `record_version()` must be called inside the same DB transaction as the UPDATE it's recording. Commit once, after both the UPDATE and the INSERT into resource_versions.

---

## Step 17 — Layer Version Endpoints + record_version in update_layer

**File:** `api/app/routers/layers.py`

Add at end of router:

```
GET    /layers/{id}/versions               → list[VersionListItem]
GET    /layers/{id}/versions/{v}           → VersionDetail (includes full snapshot)
POST   /layers/{id}/versions/{v}/restore   → VersionRestoreResponse
```

Also in the existing `update_layer()` endpoint:
```python
LAYER_VERSION_FIELDS = ["name", "description", "status", "srid", "tags", "sort_order"]
# Before commit:
# 1. Capture old snapshot (dict of current layer fields)
# 2. Detect changed_fields by comparing old vs new values
# 3. Call record_version(db, "layer", layer.id, old_snapshot, changed_fields, ctx.user_id)
# 4. Then commit (both the UPDATE and the version INSERT in one transaction)
```

---

## Step 18 — Map Version Endpoints + record_version in update_map

**File:** `api/app/routers/maps.py`

Add version endpoints (same pattern as step 17) and wire `record_version()` into `update_map()`.

---

## Step 19 — Layer Expression CRUD Endpoints

**File:** `api/app/routers/layers.py`

Add before `/{layer_id}` routes (to avoid route conflict):
```
POST   /layers/{id}/expressions            Create expression (validate DSL before saving)
GET    /layers/{id}/expressions            List (ExpressionListItem)
GET    /layers/{id}/expressions/{eid}      Get full expression
PUT    /layers/{id}/expressions/{eid}      Update (re-validate DSL)
DELETE /layers/{id}/expressions/{eid}      Delete
```

On create/update: call `compile_expression(body.expression, schema_fields, {})` — if it raises `ValueError`, return 400. Store expression only if validation passes.

On delete: also call `cache_delete(f"expr:{eid}")`.

---

## Step 20 — Export Service

**File:** `api/app/services/export_service.py` (new file)

```python
async def export_geojson(shard_db, layer_id: uuid.UUID, target_srid: int | None) -> bytes:
    # SELECT id, ST_AsGeoJSON(ST_Transform(geom, :srid)) as geom, properties
    # FROM features WHERE layer_id=:lid AND deleted_at IS NULL
    # Build FeatureCollection, return json.dumps(...).encode()

async def export_shapefile(shard_db, layer, target_srid: int | None) -> bytes:
    # Uses pyshp (import shapefile). MUST run via asyncio.to_thread() — pyshp is sync.
    # Fetches WKB: ST_AsBinary(ST_Transform(geom, :srid))
    # Field names truncated to 10 chars (Shapefile limit)
    # Returns zip bytes (.shp/.dbf/.prj/.shx in memory using io.BytesIO)

async def export_gpkg(shard_db, layer, target_srid: int | None) -> bytes:
    # Uses fiona with 'GPKG' driver. MUST run via asyncio.to_thread() — fiona is sync.
    # Returns bytes of the .gpkg file

async def validate_srid(request, srid: int) -> bool:
    # return srid in request.app.state.valid_srids
```

---

## Step 21 — Export Endpoint

**File:** `api/app/routers/layers.py`

```
GET /layers/{id}/export?format=geojson|shapefile|gpkg&srid=<int>
```

- Permission: `can_user_do(..., "export")`
- Validate `format` ∈ `{geojson, shapefile, gpkg}`
- If `srid` provided: validate with `request.app.state.valid_srids` → 400 if invalid
- Default srid: 4326
- Returns `StreamingResponse` (geojson) or `Response` (binary)
- `Content-Disposition: attachment; filename="<layer_name>.<ext>"`

---

## Step 22 — Stats Service

**File:** `api/app/services/stats_service.py` (new file)

```python
async def get_layer_stats(shard_db, layer_id: uuid.UUID, json_schema: dict) -> dict:
    # Check Redis: cache_get(f"stats:{layer_id}") → return if hit
    # Compute:
    #   1. Total count + geometry type breakdown (GROUP BY ST_GeometryType(geom))
    #   2. Spatial envelope: ST_XMin/YMin/XMax/YMax of ST_Collect(geom)
    #   3. Per-field stats (loop over json_schema["fields"]):
    #      string:  null_count, unique_count, top 10 values
    #      number:  MIN/MAX/AVG + null_count (cast properties->>field to ::numeric)
    #      boolean: true_count, false_count, null_count
    # cache_set(f"stats:{layer_id}", stats, ttl=60)
    # return stats
```

**Cache invalidation:** In `features.py`, after every feature mutation, add:
```python
await cache_delete(f"stats:{layer_id}")
```
(Add this alongside the existing `refresh_layer_geometry_types` calls.)

---

## Step 23 — Stats Endpoint + valid_srids at Startup

**File:** `api/app/routers/layers.py`
```
GET /layers/{id}/stats
```
Permission: `can_user_do(..., "read")`. Returns `get_layer_stats(shard_db, layer_id, layer.json_schema)`.

**File:** `api/app/main.py` — in `lifespan()`:
```python
async with MetaSessionLocal() as db:
    rows = await db.execute(text("SELECT srid FROM spatial_ref_sys"))
    app.state.valid_srids = frozenset(r[0] for r in rows)
```

---

## Step 24 — Frontend: TypeScript Types

**File:** `web/src/types/index.ts`

Add these interfaces (do not remove existing ones):

```typescript
// Update existing Layer interface — add:
bbox: [number, number, number, number] | null;
features_updated_at: string | null;
features_updated_by: string | null;

// New interfaces:
export interface GeoMap {
  id: string;
  database_id: string;
  name: string;
  description: string | null;
  extent: [number, number, number, number] | null;
  content_version: number;
  content_updated_at: string;
  content_updated_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface MapGroup {
  id: string;
  map_id: string;
  parent_id: string | null;
  embedded_map_id: string | null;
  name: string;
  sort_order: number;
  is_expanded: boolean;
  created_at: string;
}

export interface MapLayerNode {
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
  filter_expression: object | null;
  effective_role?: string;
}

export interface MapGroupNode {
  type: 'group';
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  is_expanded: boolean;
  embedded_map_id: string | null;
  children: (MapGroupNode | MapLayerNode)[];
}

export type MapTreeNode = MapGroupNode | MapLayerNode;

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

---

## Step 25 — Frontend: API Modules

**File:** `web/src/api/maps.ts` (new file)

```typescript
import client from './client';
import type { GeoMap, MapGroup, MapLayerNode, MapGroupNode, MapTreeNode } from '../types';

export const mapsApi = {
  list: (databaseId: string) =>
    client.get<GeoMap[]>(`/maps?database_id=${databaseId}`).then(r => r.data),
  create: (data: { name: string; description?: string; database_id: string }) =>
    client.post<GeoMap>('/maps', data).then(r => r.data),
  get: (id: string) => client.get<GeoMap>(`/maps/${id}`).then(r => r.data),
  update: (id: string, data: Partial<GeoMap>) =>
    client.put<GeoMap>(`/maps/${id}`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/maps/${id}`),
  open: (id: string) =>
    client.get<{ map: GeoMap; tree: MapTreeNode[] }>(`/maps/${id}/open`).then(r => r.data),
  freshness: (id: string, since: string) =>
    client.get(`/maps/${id}/freshness?since=${since}`).then(r => r.data),
  createGroup: (mapId: string, data: object) =>
    client.post<MapGroup>(`/maps/${mapId}/groups`, data).then(r => r.data),
  updateGroup: (mapId: string, groupId: string, data: object) =>
    client.put<MapGroup>(`/maps/${mapId}/groups/${groupId}`, data).then(r => r.data),
  deleteGroup: (mapId: string, groupId: string) =>
    client.delete(`/maps/${mapId}/groups/${groupId}`),
  addLayer: (mapId: string, data: object) =>
    client.post(`/maps/${mapId}/layers`, data).then(r => r.data),
  removeLayer: (mapId: string, layerId: string) =>
    client.delete(`/maps/${mapId}/layers/${layerId}`),
  updateLayer: (mapId: string, layerId: string, data: object) =>
    client.put(`/maps/${mapId}/layers/${layerId}`, data).then(r => r.data),
  grantGroupPermissions: (mapId: string, groupId: string, data: object) =>
    client.post(`/maps/${mapId}/groups/${groupId}/permissions`, data).then(r => r.data),
};

export const layerExportUrl = (layerId: string, format: 'geojson' | 'shapefile' | 'gpkg', srid?: number) => {
  const token = localStorage.getItem('token');
  const base = `/layers/${layerId}/export?format=${format}`;
  return srid ? `${base}&srid=${srid}&token=${token}` : `${base}&token=${token}`;
};

export const layerStatsApi = {
  get: (layerId: string) =>
    client.get<LayerStats>(`/layers/${layerId}/stats`).then(r => r.data),
};
```

**File:** `web/src/api/layers.ts` — add identify function:
```typescript
export const identify = (databaseId: string, geometry: object) =>
  client.post<LayerIdentifyResponse>('/layers/identify', {
    database_id: databaseId,
    geometry,
  }).then(r => r.data);
```

---

## Step 26 — Frontend: MapGroupTree Component

**File:** `web/src/components/maps/MapGroupTree.tsx` (new file)

Recursive Ant Design tree renderer:
- Group nodes: folder icon, expand/collapse toggle, kebab menu ("Add sub-group", "Rename", "Delete", "Grant permissions")
- Layer nodes: geometry icon, layer name, visibility eye toggle (calls `PUT /maps/{id}/layers/{lid}` with `{is_visible: bool}`), "Export" dropdown (GeoJSON/Shapefile/GeoPackage via `layerExportUrl`)
- Accepts props: `tree: MapTreeNode[]`, `mapId: string`, `onRefresh: () => void`
- On drag-and-drop reorder: call `PUT /maps/{id}/layers/{lid}` or `PUT /maps/{id}/groups/{gid}` with new `sort_order`/`parent_id`

---

## Step 27 — Frontend: ExpressionBuilder Component

**File:** `web/src/components/maps/ExpressionBuilder.tsx` (new file)

Nested AND/OR group builder:
- Field selector (dropdown of layer schema fields)
- Op selector (changes based on field type)
- Value input (type-aware: number spinner for numeric, text for string, multi-select for `in`)
- "Save as..." button → calls `POST /layers/{id}/expressions`
- "Load saved" button → lists saved expressions, applies on select
- Accepts props: `layerId: string`, `schema: object`, `value: object | null`, `onChange: (expr: object) => void`

---

## Step 28 — Frontend: MapPage Refactor

**File:** `web/src/pages/MapPage.tsx`

Major changes:
1. Add **map selector** `<Select>` below database selector, populated from `mapsApi.list(databaseId)`
2. Replace flat layer list with **`<MapGroupTree>`** component, populated from `mapsApi.open(mapId)`
3. Add **"Add Group"** button at top of tree panel
4. Add **"Manage Layers"** button → opens layer picker modal
5. **Identify mode:**
   - Add toolbar button "Identify" (magnifying glass icon)
   - On click: switch terra-draw to polygon mode, show "Search Layers" button
   - On "Search Layers": call `identify(databaseId, polygonGeometry)` from `api/layers.ts`
   - Show results panel with group/layer tree, each layer showing `feature_count_in_area` badge
   - "Load" button per layer: fetch `GET /layers/{id}/features?spatial_op=intersects&filter_geojson=...` and add to map
   - "Load All with Data" button: loads all layers with `feature_count_in_area > 0`
   - Layers with 0 features shown at 50% opacity (still visible, can be loaded)
   - "×" button exits identify mode

**Map extent auto-zoom:** When `mapsApi.open()` returns and `map.extent` is not null:
```typescript
mapInstance.fitBounds([[extent[0], extent[1]], [extent[2], extent[3]]]);
```

---

## Step 29 — Frontend: MapsPage

**File:** `web/src/pages/MapsPage.tsx` (new file)

Simple CRUD page: list maps per selected database, create/rename/delete maps.

**File:** `web/src/App.tsx` — add route: `<Route path="/maps-admin" element={<MapsPage />} />`

**File:** `web/src/components/Sidebar.tsx` — add nav item "Maps" linking to `/maps-admin`

---

## Step 30 — Frontend: LayerDetailPage Additions

**File:** `web/src/pages/LayerDetailPage.tsx`

Add three new sections:

1. **Export buttons:**
```tsx
<Button onClick={() => window.open(layerExportUrl(id, 'geojson'))}>Export GeoJSON</Button>
<Button onClick={() => window.open(layerExportUrl(id, 'shapefile'))}>Export Shapefile</Button>
<Button onClick={() => window.open(layerExportUrl(id, 'gpkg'))}>Export GeoPackage</Button>
```

2. **Stats panel** (collapsible `<Collapse>`):
   - Feature count + geometry type pills
   - Field stats table: field name | type | key stats

3. **Version history tab:**
   - List versions from `GET /layers/{id}/versions`
   - Click version → show snapshot diff
   - "Restore" button → `POST /layers/{id}/versions/{v}/restore`

---

## Step 31 — Identify Endpoint (Backend)

**File:** `api/app/routers/layers.py`

Add `POST /layers/identify` BEFORE any `/{layer_id}` routes (critical — FastAPI matches in order, "identify" would be parsed as a UUID otherwise).

```python
@router.post("/identify", response_model=LayerIdentifyResponse)
async def identify_layers_by_polygon(
    body: LayerIdentifyRequest,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    # 1. Validate body.geometry["type"] ∈ GEOJSON_GEOMETRY_TYPES → 400 if not
    # 2. Load all non-deleted layers for body.database_id, ordered by sort_order, name
    # 3. Filter to layers ctx can read (can_user_do per layer)
    # 4. Group layers by shard_id
    # 5. For each shard: single query:
    #    SELECT layer_id::text, COUNT(*) FROM features
    #    WHERE layer_id = ANY(CAST(:ids AS uuid[]))
    #      AND deleted_at IS NULL
    #      AND ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
    #    GROUP BY layer_id
    # 6. Build tree using group_layer_id hierarchy (existing folder system on Layer)
    #    Layers with group_layer_id → under that group; null → at root
    # 7. Fetch group names for groups that appear
    # 8. Return LayerIdentifyResponse(tree=[...])
```

All layers appear in the response regardless of feature count. `feature_count_in_area=0` if no features in the polygon.

---

## Also needed: Cache Invalidation in Groups Router

**File:** `api/app/routers/groups.py`

When a member is added or removed from a custom group, the `groups:{user_id}` Redis cache entry for that user must be deleted. Add to the relevant endpoints:
```python
await cache_delete(f"groups:{affected_user_id}")
```

---

## Also needed: Call refresh_map_content_for_layer from Features Router

**File:** `api/app/routers/features.py`

After `refresh_layer_feature_stamp()` at each mutation endpoint:
```python
import asyncio
from app.services.map_service import refresh_map_content_for_layer
asyncio.create_task(refresh_map_content_for_layer(layer_id, ctx.user_id, meta_db))
```

This propagates feature changes to maps' `content_version` counters.
