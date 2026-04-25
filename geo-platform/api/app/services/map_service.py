"""Business logic for maps, map groups, map layers, freshness, and map content versioning.

All cross-service calls (e.g. propagating feature changes to maps) follow the
fire-and-forget pattern — exceptions are logged, never re-raised.
"""
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import (
    cache_delete, cache_get, cache_set,
    cache_sadd, cache_smembers, get_redis,
)
from app.db.session import MetaSessionLocal
from app.models.layers import Layer
from app.models.maps import Map, MapGroup, MapLayer
from app.schemas.maps import (
    MapCreate, MapUpdate,
    MapGroupCreate, MapGroupUpdate,
    MapLayerAdd, MapLayerUpdate,
)

logger = logging.getLogger(__name__)

MAX_EMBED_DEPTH = 5


# ── Map CRUD ───────────────────────────────────────────────────────────────────

async def get_map(db: AsyncSession, map_id: uuid.UUID) -> Map | None:
    result = await db.execute(
        select(Map).where(Map.id == map_id, Map.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_maps(db: AsyncSession, database_id: uuid.UUID) -> list[Map]:
    result = await db.execute(
        select(Map)
        .where(Map.database_id == database_id, Map.deleted_at.is_(None))
        .order_by(Map.name)
    )
    return list(result.scalars().all())


async def create_map(db: AsyncSession, body: MapCreate, actor_id: str) -> Map:
    obj = Map(
        name=body.name,
        description=body.description,
        database_id=body.database_id,
        created_by=uuid.UUID(actor_id),
        updated_by=uuid.UUID(actor_id),
        content_updated_by=uuid.UUID(actor_id),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def update_map(
    db: AsyncSession, map_id: uuid.UUID, body: MapUpdate, actor_id: str
) -> Map | None:
    obj = await get_map(db, map_id)
    if not obj:
        return None
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    obj.updated_by = uuid.UUID(actor_id)
    obj.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(obj)
    return obj


async def delete_map(db: AsyncSession, map_id: uuid.UUID, actor_id: str) -> bool:
    obj = await get_map(db, map_id)
    if not obj:
        return False
    obj.deleted_at = datetime.utcnow()
    obj.deleted_by = uuid.UUID(actor_id)
    await db.commit()
    await _invalidate_map_caches(map_id)
    return True


def map_to_response_dict(obj: Map, extent: list[float] | None = None) -> dict:
    return {
        "id": obj.id,
        "database_id": obj.database_id,
        "name": obj.name,
        "description": obj.description,
        "extent": extent,
        "content_version": obj.content_version,
        "content_updated_at": obj.content_updated_at,
        "content_updated_by": obj.content_updated_by,
        "created_by": obj.created_by,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


async def get_map_extent(db: AsyncSession, map_id: uuid.UUID) -> list[float] | None:
    """Read map.extent envelope as [xmin, ymin, xmax, ymax] or None."""
    row = await db.execute(
        text(
            "SELECT ST_XMin(extent)::float8, ST_YMin(extent)::float8, "
            "ST_XMax(extent)::float8, ST_YMax(extent)::float8 "
            "FROM maps WHERE id = :mid AND extent IS NOT NULL"
        ),
        {"mid": str(map_id)},
    )
    r = row.one_or_none()
    return list(r) if r else None


# ── Map Group CRUD ─────────────────────────────────────────────────────────────

async def _check_embed_cycle(
    db: AsyncSession,
    parent_map_id: uuid.UUID,
    embedded_map_id: uuid.UUID,
    depth: int = 0,
) -> None:
    """Walks the embed graph from embedded_map_id; raises ValueError if it leads back to parent_map_id."""
    if depth > MAX_EMBED_DEPTH:
        raise ValueError(f"Embed chain too deep (max {MAX_EMBED_DEPTH})")
    if embedded_map_id == parent_map_id:
        raise ValueError("Embed cycle detected")
    result = await db.execute(
        select(MapGroup.embedded_map_id).where(
            MapGroup.map_id == embedded_map_id,
            MapGroup.embedded_map_id.isnot(None),
        )
    )
    for (next_embed,) in result.all():
        await _check_embed_cycle(db, parent_map_id, next_embed, depth + 1)


async def create_map_group(
    db: AsyncSession, map_id: uuid.UUID, body: MapGroupCreate, actor_id: str
) -> MapGroup:
    if body.embedded_map_id:
        await _check_embed_cycle(db, map_id, body.embedded_map_id)
    obj = MapGroup(
        map_id=map_id,
        name=body.name,
        parent_id=body.parent_id,
        embedded_map_id=body.embedded_map_id,
        sort_order=body.sort_order,
        created_by=uuid.UUID(actor_id),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    await cache_delete(f"maptree:{map_id}")
    return obj


async def update_map_group(
    db: AsyncSession, map_id: uuid.UUID, group_id: uuid.UUID, body: MapGroupUpdate
) -> MapGroup | None:
    result = await db.execute(
        select(MapGroup).where(MapGroup.id == group_id, MapGroup.map_id == map_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    await cache_delete(f"maptree:{map_id}")
    return obj


async def delete_map_group(
    db: AsyncSession, map_id: uuid.UUID, group_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(MapGroup).where(MapGroup.id == group_id, MapGroup.map_id == map_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.commit()
    await cache_delete(f"maptree:{map_id}")
    return True


# ── Map Layer add/remove/update ────────────────────────────────────────────────

async def add_layer_to_map(
    db: AsyncSession, map_id: uuid.UUID, body: MapLayerAdd, actor_id: str
) -> MapLayer:
    obj = MapLayer(
        map_id=map_id,
        layer_id=body.layer_id,
        group_id=body.group_id,
        sort_order=body.sort_order,
        filter_expression=body.filter_expression,
        added_by=uuid.UUID(actor_id),
    )
    db.add(obj)
    # bump content_version
    await db.execute(
        text(
            "UPDATE maps SET content_version = content_version + 1, "
            "content_updated_at = NOW(), content_updated_by = CAST(:actor AS uuid) "
            "WHERE id = CAST(:mid AS uuid)"
        ),
        {"actor": actor_id, "mid": str(map_id)},
    )
    await db.commit()
    await db.refresh(obj)
    await cache_sadd(f"layermaps:{body.layer_id}", str(map_id), ttl=3600)
    await cache_delete(f"maptree:{map_id}")
    await _invalidate_map_caches(map_id)
    return obj


async def remove_layer_from_map(
    db: AsyncSession, map_id: uuid.UUID, layer_id: uuid.UUID, actor_id: str
) -> bool:
    result = await db.execute(
        select(MapLayer).where(
            MapLayer.map_id == map_id, MapLayer.layer_id == layer_id
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await db.delete(obj)
    await db.execute(
        text(
            "UPDATE maps SET content_version = content_version + 1, "
            "content_updated_at = NOW(), content_updated_by = CAST(:actor AS uuid) "
            "WHERE id = CAST(:mid AS uuid)"
        ),
        {"actor": actor_id, "mid": str(map_id)},
    )
    await db.commit()
    # Remove from Redis set
    try:
        r = await get_redis()
        await r.srem(f"layermaps:{layer_id}", str(map_id))
    except Exception as exc:
        logger.warning("srem layermaps:%s failed: %s", layer_id, exc)
    await cache_delete(f"maptree:{map_id}")
    await _invalidate_map_caches(map_id)
    return True


async def update_map_layer(
    db: AsyncSession,
    map_id: uuid.UUID,
    layer_id: uuid.UUID,
    body: MapLayerUpdate,
) -> MapLayer | None:
    result = await db.execute(
        select(MapLayer).where(
            MapLayer.map_id == map_id, MapLayer.layer_id == layer_id
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return None
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    await cache_delete(f"maptree:{map_id}")
    return obj


# ── Map layer tree (cached) ────────────────────────────────────────────────────

async def get_map_layer_tree(db: AsyncSession, map_id: uuid.UUID) -> list[dict]:
    """Returns the flat row list from get_map_layer_tree() SQL function. Cached 30s."""
    cache_key = f"maptree:{map_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    result = await db.execute(
        text("SELECT * FROM get_map_layer_tree(CAST(:mid AS uuid))"),
        {"mid": str(map_id)},
    )
    rows = [dict(r) for r in result.mappings().all()]
    # serialize UUIDs / datetimes as strings via cache_set's default=str
    await cache_set(cache_key, rows, ttl=30)
    return rows


def assemble_tree(flat_rows: list[dict]) -> list[dict]:
    """Build a nested tree from the flat rows.

    Groups have row_type='group'; layers have row_type='layer'.
    For groups: parent_id = parent group_id (null = root).
    For layers: parent_id = group_id (null = root).
    """
    group_nodes: dict[str, dict] = {}
    layer_nodes: list[dict] = []

    for r in flat_rows:
        if r["row_type"] == "group":
            gid = str(r["row_id"])
            group_nodes[gid] = {
                "type": "group",
                "id": r["row_id"],
                "name": r["name"],
                "parent_id": r["parent_id"],
                "sort_order": r["sort_order"],
                "is_expanded": r["is_expanded"] if r["is_expanded"] is not None else True,
                "embedded_map_id": r["embedded_map_id"],
                "children": [],
            }
        else:  # layer
            layer_nodes.append({
                "type": "layer",
                "map_layer_id": r["row_id"],
                "layer_id": r["layer_id"],
                "name": r["name"],
                "group_id": r["parent_id"],
                "sort_order": r["sort_order"],
                "is_visible": r["is_visible"] if r["is_visible"] is not None else True,
                "srid": r["srid"] or 4326,
                "geometry_types": r["geometry_types"] or [],
                "bbox": list(r["bbox_arr"]) if r["bbox_arr"] else None,
                "filter_expression": None,  # not in flat function; filled by caller from map_layers if needed
                "effective_role": None,
            })

    roots: list[dict] = []
    # Place groups in their parent groups, or at root
    for gid, node in group_nodes.items():
        parent_id = node["parent_id"]
        if parent_id and str(parent_id) in group_nodes:
            group_nodes[str(parent_id)]["children"].append(node)
        else:
            roots.append(node)

    # Place layers in their groups, or at root
    for ln in layer_nodes:
        gid = ln["group_id"]
        if gid and str(gid) in group_nodes:
            group_nodes[str(gid)]["children"].append(ln)
        else:
            roots.append(ln)

    # Sort children by sort_order
    def _sort_recursive(nodes: list[dict]) -> None:
        nodes.sort(key=lambda n: (n.get("sort_order") or 0, n.get("name") or ""))
        for n in nodes:
            if n["type"] == "group":
                _sort_recursive(n["children"])

    _sort_recursive(roots)
    return roots


# ── Refresh map extent ─────────────────────────────────────────────────────────

async def refresh_map_extent(db: AsyncSession, map_id: uuid.UUID) -> None:
    """Recompute maps.extent from union of layer bboxes."""
    try:
        await db.execute(
            text("""
                UPDATE maps SET extent = sub.env
                FROM (
                    SELECT ST_Envelope(ST_Collect(l.bbox)) AS env
                    FROM map_layers ml
                    JOIN layers l ON l.id = ml.layer_id
                    WHERE ml.map_id = CAST(:mid AS uuid)
                      AND l.bbox IS NOT NULL
                      AND l.deleted_at IS NULL
                ) sub
                WHERE id = CAST(:mid AS uuid)
            """),
            {"mid": str(map_id)},
        )
        await db.commit()
    except Exception as exc:
        logger.warning("refresh_map_extent failed for map %s: %s", map_id, exc)


# ── Cross-service: feature mutation → bump map content_version ─────────────────

async def refresh_map_content_for_layer(
    layer_id: uuid.UUID, actor_id: str
) -> None:
    """Fire-and-forget: bump content_version on every map containing this layer.

    Resolves map_ids via Redis set (cache miss → DB query, then populate set).
    Opens its own DB session so the calling request's session can be closed.
    """
    try:
        member_strs = await cache_smembers(f"layermaps:{layer_id}")
        map_ids: list[str] = list(member_strs) if member_strs else []

        if not map_ids:
            async with MetaSessionLocal() as db:
                result = await db.execute(
                    text(
                        "SELECT map_id::text FROM map_layers "
                        "WHERE layer_id = CAST(:lid AS uuid)"
                    ),
                    {"lid": str(layer_id)},
                )
                map_ids = [r[0] for r in result.all()]
            if map_ids:
                await cache_sadd(f"layermaps:{layer_id}", *map_ids, ttl=3600)

        if not map_ids:
            return

        async with MetaSessionLocal() as db:
            for mid in map_ids:
                try:
                    await db.execute(
                        text(
                            "UPDATE maps SET content_version = content_version + 1, "
                            "content_updated_at = NOW(), "
                            "content_updated_by = CAST(:actor AS uuid) "
                            "WHERE id = CAST(:mid AS uuid)"
                        ),
                        {"actor": actor_id, "mid": mid},
                    )
                except Exception as exc:
                    logger.warning("bump content_version map=%s failed: %s", mid, exc)
            await db.commit()

        for mid in map_ids:
            try:
                await cache_delete(f"mapfresh:{mid}")
            except Exception as exc:
                logger.warning("cache_delete mapfresh:%s failed: %s", mid, exc)
    except Exception as exc:
        logger.warning("refresh_map_content_for_layer failed for layer %s: %s", layer_id, exc)


# ── Freshness ──────────────────────────────────────────────────────────────────

async def get_map_freshness(
    db: AsyncSession, map_id: uuid.UUID, since: datetime
) -> dict:
    """Returns {map_id, content_version, content_updated_at, any_change_since, changed_layers[]}.

    Cached 30s under mapfresh:{map_id}:{since-iso}.
    """
    cache_key = f"mapfresh:{map_id}:{since.isoformat()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    map_obj = await get_map(db, map_id)
    if not map_obj:
        raise ValueError("Map not found")

    result = await db.execute(
        text("""
            SELECT l.id, l.name, l.features_updated_at, l.features_updated_by
            FROM map_layers ml
            JOIN layers l ON l.id = ml.layer_id
            WHERE ml.map_id = CAST(:mid AS uuid)
              AND l.deleted_at IS NULL
              AND l.features_updated_at IS NOT NULL
              AND l.features_updated_at > :since
            ORDER BY l.features_updated_at DESC
        """),
        {"mid": str(map_id), "since": since},
    )
    changed = [
        {
            "layer_id": r[0],
            "name": r[1],
            "features_updated_at": r[2],
            "features_updated_by": r[3],
        }
        for r in result.all()
    ]
    response = {
        "map_id": map_id,
        "content_version": map_obj.content_version,
        "content_updated_at": map_obj.content_updated_at,
        "any_change_since": bool(changed) or map_obj.content_updated_at > since,
        "changed_layers": changed,
    }
    await cache_set(cache_key, response, ttl=30)
    return response


# ── Group → layer expansion (for bulk perm grant) ──────────────────────────────

async def expand_group_layers(
    db: AsyncSession, map_id: uuid.UUID, group_id: uuid.UUID
) -> list[uuid.UUID]:
    """Recursively collect layer_ids in this group + all sub-groups."""
    result = await db.execute(
        text("""
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM map_groups WHERE id = CAST(:gid AS uuid) AND map_id = CAST(:mid AS uuid)
                UNION ALL
                SELECT mg.id FROM map_groups mg
                JOIN subtree s ON mg.parent_id = s.id
                WHERE mg.map_id = CAST(:mid AS uuid)
            )
            SELECT DISTINCT ml.layer_id
            FROM map_layers ml
            JOIN subtree s ON ml.group_id = s.id
            WHERE ml.map_id = CAST(:mid AS uuid)
        """),
        {"gid": str(group_id), "mid": str(map_id)},
    )
    return [r[0] for r in result.all()]


# ── Internal: bust map-related caches ──────────────────────────────────────────

async def _invalidate_map_caches(map_id: uuid.UUID) -> None:
    """Delete maptree + mapfresh wildcard for this map (best-effort)."""
    try:
        await cache_delete(f"maptree:{map_id}")
        # Wildcard delete for mapfresh (different `since` values)
        r = await get_redis()
        async for key in r.scan_iter(match=f"mapfresh:{map_id}*"):
            await r.delete(key)
    except Exception as exc:
        logger.warning("_invalidate_map_caches failed for %s: %s", map_id, exc)
