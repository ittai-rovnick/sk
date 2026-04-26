# What Still Needs to Be Implemented

Steps are ordered by dependency. Follow the order — later steps depend on earlier ones.

---

## ~~Steps 1–28~~ ✅ ALL DONE (see 01_done.md)

---

# Phase 29–34 — Production Gaps

These are the four meaningful gaps identified after completing the 28-step plan, plus two operational items.  
Priority order: tiles first (scalability), then tests (correctness), then async export (reliability), then SSE (UX).

---

## Phase 29 — MVT Tile Endpoint ⬅ START HERE

**Why:** GeoJSON over HTTP doesn't scale past ~5k features. Without tiles the map becomes unusable on any real dataset. `ST_AsMVT` + `ST_TileEnvelope` is built into PostGIS 3.4 already.

### Backend

**File:** `api/app/routers/tiles.py` (new)

```
GET /layers/{layer_id}/tiles/{z}/{x}/{y}
```

- Permission: `can_user_do(..., "read")`
- Response: `Response(content=mvt_bytes, media_type="application/x-protobuf")`
- Cache-Control: `public, max-age=30` (tiles are expensive to generate; short TTL is fine)
- Redis cache key: `tile:{layer_id}:{z}:{x}:{y}` TTL 30s — invalidate on `cache_delete(f"tile:{layer_id}:*")` after any feature mutation (use `cache_delete_pattern`)

**SQL (run on the correct shard for the layer):**
```sql
SELECT ST_AsMVT(q, 'features', 4096, 'geom')
FROM (
    SELECT
        id,
        properties,
        ST_AsTile(geom, :z, :x, :y, 4096) AS geom
    FROM features
    WHERE layer_id = CAST(:layer_id AS uuid)
      AND deleted_at IS NULL
      AND ST_Intersects(
            geom,
            ST_TileEnvelope(:z, :x, :y)
          )
) q
```

Actually use this pattern (more correct):
```sql
WITH bounds AS (
    SELECT ST_TileEnvelope(:z, :x, :y) AS geom
),
mvtgeom AS (
    SELECT
        f.id,
        f.properties,
        ST_AsMVTGeom(
            ST_Transform(f.geom, 3857),
            bounds.geom,
            4096, 64, true
        ) AS geom
    FROM features f, bounds
    WHERE f.layer_id = CAST(:layer_id AS uuid)
      AND f.deleted_at IS NULL
      AND ST_Intersects(f.geom, ST_Transform(bounds.geom, 4326))
)
SELECT ST_AsMVT(mvtgeom, 'features', 4096, 'geom') FROM mvtgeom
```

Return empty bytes (not 404) when tile has no features — MapLibre expects 200 with empty body or 204.

**File:** `api/app/main.py` — add `from app.routers import tiles` + `app.include_router(tiles.router)`

Also: add `cache_delete_pattern(f"tile:{layer_id}:*")` to `_invalidate_after_mutation()` in `features.py`.  
Add `cache_delete_pattern` function to `cache.py` using `redis.scan_iter` or `KEYS` (scan_iter is safer in production).

### Frontend

**File:** `web/src/pages/MapPage.tsx`

When loading a layer onto the map, switch the MapLibre source from `geojson` to `vector`:

```typescript
// Instead of fetching all features as GeoJSON:
map.addSource(`layer-${layerId}`, {
  type: 'vector',
  tiles: [`/layers/${layerId}/tiles/{z}/{x}/{y}`],
  minzoom: 0,
  maxzoom: 22,
});
map.addLayer({
  id: `layer-fill-${layerId}`,
  type: 'fill',   // or 'line' / 'circle' based on geometry_types
  source: `layer-${layerId}`,
  'source-layer': 'features',
  paint: { 'fill-color': color, 'fill-opacity': 0.5 },
});
```

Keep the existing GeoJSON path as a fallback for editing mode (terra-draw needs GeoJSON features in memory anyway). Switch to tile source for view-only display.

**Add auth header to tile requests:**  
MapLibre doesn't support custom headers on tile sources natively. Use a `transformRequest` hook on the MapLibre `Map` instance:

```typescript
transformRequest: (url, resourceType) => {
  if (resourceType === 'Tile' && url.includes('/layers/')) {
    return {
      url,
      headers: { Authorization: `Bearer ${token}` },
    };
  }
},
```

---

## Phase 30 — Missing Tests

**Why:** Sync is the most complex code in the system (conflict detection, snapshot/delta/push) and has zero test coverage. `test_databases` and `test_groups` cover high-usage paths that are also untested.

### Files to create

**`api/app/tests/test_databases.py`**
- `test_create_database` — POST /databases → 201, fields correct
- `test_list_databases` — GET /databases → returns created db
- `test_update_database` — PUT /databases/{id} → name updated
- `test_delete_database` — DELETE /databases/{id} → 204, then GET → 404

**`api/app/tests/test_groups.py`**
- `test_create_group` — POST /groups → 201
- `test_add_member` — POST /groups/{id}/members → 200; GET /groups/{id}/members returns user
- `test_remove_member` — DELETE /groups/{id}/members/{uid} → 204
- `test_group_tree` — GET /groups/tree → nested structure correct
- `test_redis_invalidation` — after add/remove member, Redis key `groups:{user_id}` must be gone

**`api/app/tests/test_sync.py`**
- `test_snapshot` — POST /sync/snapshot → returns all active features for a layer
- `test_delta` — POST features, call GET /sync/delta?since=T → only new features returned
- `test_push_no_conflict` — push a feature update where server version matches → 200, feature updated
- `test_push_conflict` — push a feature update where server version is ahead → 409, SyncConflict row created
- `test_resolve_conflict_server_wins` — POST /sync/conflicts/{id}/resolve with `resolution=server` → conflict closed, client change discarded
- `test_resolve_conflict_client_wins` — `resolution=client` → conflict closed, client change applied

**`api/app/tests/test_maps.py`**
- `test_create_map` — POST /maps → 201
- `test_open_map` — GET /maps/{id}/open → tree structure correct
- `test_add_layer_to_map` — POST /maps/{id}/layers → layer appears in open tree
- `test_content_version_bumps` — after feature mutation on a layer in a map, content_version increments
- `test_freshness` — GET /maps/{id}/freshness?since=T → changed_layers includes the mutated layer
- `test_tile_endpoint` — GET /layers/{id}/tiles/0/0/0 → 200 with bytes response

All tests follow the pattern in `test_features.py`: use `pytest-asyncio`, separate test databases (`geo_meta_test`, `geo_features_test`), and a shared `client` fixture from `conftest.py`.

---

## Phase 31 — Async Export (Background Jobs)

**Why:** Large-layer exports block the HTTP request. GeoPackage of 500k features will exceed any reasonable HTTP timeout. The fix is a job queue pattern: POST returns a job ID, worker runs export to MinIO, client polls for completion.

### Backend

**Migration 011 — export_jobs table** (`api/alembic/versions/011_export_jobs.py`, meta branch)

```sql
CREATE TYPE export_status AS ENUM ('pending', 'running', 'done', 'failed');

CREATE TABLE export_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer_id    UUID NOT NULL REFERENCES layers(id),
    format      TEXT NOT NULL,   -- geojson | shapefile | gpkg
    srid        INT NOT NULL DEFAULT 4326,
    status      export_status NOT NULL DEFAULT 'pending',
    storage_key TEXT,            -- MinIO key, set when done
    error       TEXT,            -- set when failed
    requested_by UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX export_jobs_layer_idx ON export_jobs(layer_id, created_at DESC);
```

**File:** `api/app/routers/layers.py` — replace synchronous export with async:

```
POST /layers/{id}/export          { format, srid? }  → { job_id, status: "pending" }
GET  /layers/{id}/export/{job_id}                    → { status, download_url? }
```

When `status == "done"`, `download_url` is a MinIO presigned URL (TTL 15 min).

**File:** `api/app/services/export_worker.py` (new)

```python
async def run_export_job(job_id: uuid.UUID) -> None:
    # 1. Mark job status = 'running', started_at = NOW()
    # 2. Fetch layer + shard session
    # 3. Call export_service.export_*(shard_db, layer, srid) → bytes
    # 4. Upload to MinIO: key = f"exports/{layer_id}/{job_id}.{ext}"
    # 5. Mark status = 'done', storage_key = key, finished_at = NOW()
    # On exception: mark status = 'failed', error = str(exc)
```

Call via `asyncio.create_task(run_export_job(job_id))` from the POST endpoint (fire-and-forget, same pattern as audit_service).

**Note:** `asyncio.create_task` is sufficient for dev. For production with process restarts mid-job, replace with ARQ or Celery. For now the task approach is fine.

---

## Phase 32 — Server-Sent Events for Map Freshness

**Why:** The web client currently has to poll `GET /maps/{id}/freshness` to know when layers change. SSE turns this into a push — the browser gets notified within seconds of a feature mutation, with zero polling overhead.

### Backend

**File:** `api/app/routers/maps.py` — add one endpoint:

```
GET /maps/{id}/events
```

```python
from fastapi.responses import StreamingResponse
import asyncio, json

@router.get("/{map_id}/events")
async def map_events(
    map_id: uuid.UUID,
    ctx: RequestContext = Depends(get_current_user),
    redis = Depends(get_redis),
):
    # Permission: can_user_do read on any layer in the map
    channel = f"map_events:{map_id}"

    async def event_stream():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data'].decode()}\n\n"
        finally:
            await pubsub.unsubscribe(channel)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

**File:** `api/app/services/map_service.py` — in `refresh_map_content_for_layer()`, after bumping `content_version`:

```python
await redis.publish(f"map_events:{map_id}", json.dumps({
    "type": "layer_changed",
    "layer_id": str(layer_id),
    "content_version": new_version,
}))
```

Use Redis Pub/Sub (already available). No new dependencies.

### Frontend

**File:** `web/src/pages/MapPage.tsx` — replace the polling freshness check with an EventSource:

```typescript
useEffect(() => {
  if (!mapId) return;
  const token = localStorage.getItem('token');
  const es = new EventSource(`/maps/${mapId}/events?token=${token}`);
  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'layer_changed') {
      // Invalidate the tile source for that layer so MapLibre refetches
      const src = map.getSource(`layer-${msg.layer_id}`);
      if (src) (src as VectorTileSource).setTiles([...]);
    }
  };
  return () => es.close();
}, [mapId]);
```

**Note:** EventSource doesn't support custom headers. Pass the token as a query param (`?token=`) and validate it in the SSE endpoint as an alternative to the `Authorization` header.

---

## Phase 33 — Fill Alembic Downgrade Functions

**Why:** All `downgrade()` functions are probably `pass`. If a migration needs to be rolled back in staging, you'll have to write the SQL under pressure. Better to write it now while the schema is fresh.

**Files:** `api/alembic/versions/007_*.py` through `011_*.py`

Each `downgrade()` should drop the tables/columns/types/indexes created in `upgrade()` in reverse order (dependencies last). Example for 007:

```python
def downgrade() -> None:
    op.drop_table('map_layers')
    op.drop_table('map_groups')
    op.drop_table('maps')
    op.execute("DROP FUNCTION IF EXISTS get_map_layer_tree(uuid)")
```

---

## Phase 34 — Secrets + Docker Hardening

**Why:** The `.env` file has plain-text passwords and is gitignored but shared manually. Before any deployment beyond localhost, this needs fixing.

### Items

1. **`.env.example`** — create a committed template with placeholder values (no real secrets). Add a comment at the top of each real secret noting where to find the real value.

2. **`docker-compose.yml` resource limits** — add `mem_limit` and `cpus` to each service to prevent one container starving the host.

3. **`docker-compose.yml` named volumes** — verify `geo_meta_data` and `geo_features_data` volumes are declared so data survives `docker compose down`. (They probably are but worth confirming.)

4. **MinIO CORS config** — if tile requests go browser → MinIO directly (via presigned URLs), MinIO needs CORS configured for `localhost:5173`. Add a startup script or note in the README.

5. **Production checklist note** — add a section to `docs/03_gotchas_and_fixes.md` listing what must change before production: `DEV_MODE=false`, real MS Entra credentials, `API_SECRET_KEY` rotated, HTTPS termination in front of FastAPI, MinIO behind auth proxy.

---

## Order of execution

| Phase | Effort | Impact | Do first? |
|-------|--------|--------|-----------|
| 29 — MVT tiles | ~1 day | Unblocks real data at scale | **Yes** |
| 30 — Tests | ~1 day | Correctness confidence | Yes |
| 31 — Async export | ~half day | Reliability for large layers | After 30 |
| 32 — SSE freshness | ~half day | UX for collaboration | After 31 |
| 33 — Downgrade fns | ~1 hour | Ops safety | Any time |
| 34 — Secrets/Docker | ~1 hour | Deploy readiness | Any time |
