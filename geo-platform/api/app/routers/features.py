import asyncio
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.cache import cache_delete, cache_get, cache_set
from app.models.layers import Layer, LayerSchema
from app.models.expressions import SavedExpression
from app.schemas.features import FeatureCreate, FeatureUpdate, FeatureResponse, BboxQuery, BulkDeleteRequest
from app.schemas.layers import ALLOWED_GEOMETRY_TYPES
from app.services.feature_filter import compile_expression
from app.services.layer_geometry import (
    refresh_layer_geometry_types,
    refresh_layer_bbox,
    refresh_layer_feature_stamp,
)
from app.services.map_service import refresh_map_content_for_layer
from app.db.session import shard_sessions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/layers", tags=["features"])

SPATIAL_CLAUSES = {
    "intersects": "ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "within":     "ST_Within(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "contains":   "ST_Contains(geom, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326))",
    "dwithin":    "ST_DWithin(geom::geography, ST_SetSRID(ST_GeomFromGeoJSON(:filter_geom), 4326)::geography, :dist_m)",
}


async def _get_layer(db: AsyncSession, layer_id: uuid.UUID) -> Layer:
    result = await db.execute(
        select(Layer).where(Layer.id == layer_id, Layer.deleted_at.is_(None))
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Layer not found")
    return obj


def _row_to_feature(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "layer_id": row.layer_id,
        "geom": row.geom if isinstance(row.geom, dict) else json.loads(row.geom),
        "properties": row.properties,
        "version": row.version,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _invalidate_after_mutation(layer_id: uuid.UUID, ctx: RequestContext, meta_db: AsyncSession) -> None:
    """Stamp layer + bust stats cache + propagate to maps. Fire-and-forget."""
    await refresh_layer_feature_stamp(layer_id, ctx.user_id, meta_db)
    try:
        await cache_delete(f"stats:{layer_id}")
    except Exception as exc:
        logger.warning("cache_delete stats:%s failed: %s", layer_id, exc)
    asyncio.create_task(refresh_map_content_for_layer(layer_id, ctx.user_id))


async def _resolve_expression(
    expression_id: Optional[uuid.UUID],
    expression_str: Optional[str],
    meta_db: AsyncSession,
    layer_id: uuid.UUID,
) -> Optional[dict]:
    """Returns the parsed expression dict or None. Raises HTTPException on parse error."""
    if expression_id is not None:
        cache_key = f"expr:{expression_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached
        result = await meta_db.execute(
            select(SavedExpression).where(
                SavedExpression.id == expression_id,
                SavedExpression.layer_id == layer_id,
            )
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise HTTPException(status_code=404, detail="Saved expression not found")
        await cache_set(cache_key, obj.expression, ttl=300)
        return obj.expression
    if expression_str:
        try:
            return json.loads(expression_str)
        except (json.JSONDecodeError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid expression JSON: {e}")
    return None


def _build_geom_select(zoom: Optional[int], target_srid: Optional[int]) -> tuple[str, dict]:
    """Build the geometry SELECT expression and any tolerance/srid params."""
    extra: dict[str, Any] = {}
    if zoom is not None and zoom < 14:
        extra["tolerance"] = 360.0 / (256 * (2 ** zoom))
        if target_srid is not None:
            extra["target_srid"] = target_srid
            return (
                "ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Transform(geom, :target_srid), :tolerance))::jsonb AS geom",
                extra,
            )
        return (
            "ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tolerance))::jsonb AS geom",
            extra,
        )
    if target_srid is not None:
        extra["target_srid"] = target_srid
        return ("ST_AsGeoJSON(ST_Transform(geom, :target_srid))::jsonb AS geom", extra)
    return ("ST_AsGeoJSON(geom)::jsonb AS geom", extra)


@router.get("/{layer_id}/features")
async def list_features(
    layer_id: uuid.UUID,
    request: Request,
    limit: int = 1000,
    offset: int = 0,
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    geometry_type: Optional[str] = None,
    spatial_op: Optional[str] = None,
    filter_geojson: Optional[str] = None,
    filter_distance_m: Optional[float] = None,
    expression_id: Optional[uuid.UUID] = None,
    expression: Optional[str] = None,
    zoom: Optional[int] = Query(None, ge=0, le=22),
    srid: Optional[int] = None,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")

    # Validate target SRID
    if srid is not None:
        valid_srids = getattr(request.app.state, "valid_srids", None)
        if valid_srids is not None and srid not in valid_srids:
            raise HTTPException(status_code=400, detail=f"Unknown SRID: {srid}")

    extra_filters = ""
    params: dict[str, Any] = {
        "layer_id": str(layer_id),
        "limit": limit,
        "offset": offset,
    }

    # Bbox filter (legacy)
    if all(v is not None for v in [min_lon, min_lat, max_lon, max_lat]):
        extra_filters += " AND ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        params.update({"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat})

    # Geometry-type filter
    if geometry_type is not None:
        gt = geometry_type.upper()
        if gt not in ALLOWED_GEOMETRY_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown geometry_type: {geometry_type}")
        extra_filters += " AND UPPER(REPLACE(ST_GeometryType(geom), 'ST_', '')) = :geom_type"
        params["geom_type"] = gt

    # Spatial predicate filter
    if spatial_op is not None:
        if spatial_op not in SPATIAL_CLAUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown spatial_op: {spatial_op}. Allowed: {sorted(SPATIAL_CLAUSES)}",
            )
        if not filter_geojson:
            raise HTTPException(status_code=400, detail="spatial_op requires filter_geojson")
        try:
            json.loads(filter_geojson)  # validate parseable
        except (json.JSONDecodeError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid filter_geojson: {e}")
        if spatial_op == "dwithin" and filter_distance_m is None:
            raise HTTPException(status_code=400, detail="dwithin requires filter_distance_m")
        extra_filters += f" AND {SPATIAL_CLAUSES[spatial_op]}"
        params["filter_geom"] = filter_geojson
        if spatial_op == "dwithin":
            params["dist_m"] = filter_distance_m

    # Attribute expression filter
    expr_dict = await _resolve_expression(expression_id, expression, meta_db, layer_id)
    if expr_dict is not None:
        # Load schema fields
        schema_result = await meta_db.execute(
            select(LayerSchema).where(LayerSchema.layer_id == layer_id)
        )
        schema_obj = schema_result.scalar_one_or_none()
        schema_fields_list = (schema_obj.json_schema or {}).get("fields", []) if schema_obj else []
        schema_field_names = {f["name"] for f in schema_fields_list if isinstance(f, dict) and "name" in f}
        try:
            clause = compile_expression(expr_dict, schema_field_names, params)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        extra_filters += f" AND {clause}"

    # Geometry SELECT expression (with optional zoom + srid)
    geom_select, geom_params = _build_geom_select(zoom, srid)
    params.update(geom_params)

    sql = text(f"""
        SELECT id, layer_id, {geom_select},
               properties, version, created_by, updated_by, created_at, updated_at
        FROM features
        WHERE layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
        {extra_filters}
        ORDER BY id
        LIMIT :limit OFFSET :offset
    """)

    async with shard_sessions[layer.shard_id]() as shard_db:
        result = await shard_db.execute(sql, params)
        rows = result.mappings().all()

    return [_row_to_feature(r) for r in rows]


@router.post("/{layer_id}/features", status_code=status.HTTP_201_CREATED)
async def create_feature(
    layer_id: uuid.UUID,
    body: FeatureCreate,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    if layer.is_locked:
        raise HTTPException(status_code=409, detail="Layer is locked")

    sql = text("""
        INSERT INTO features (layer_id, geom, properties, version, created_by, updated_by, created_at, updated_at)
        VALUES (
            CAST(:layer_id AS uuid),
            ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:geom)), 4326),
            :properties,
            1,
            :actor,
            :actor,
            NOW(),
            NOW()
        )
        RETURNING id, layer_id, ST_AsGeoJSON(geom)::jsonb AS geom,
                  properties, version, created_by, updated_by, created_at, updated_at
    """)

    async with shard_sessions[layer.shard_id]() as shard_db:
        result = await shard_db.execute(sql, {
            "layer_id": str(layer_id),
            "geom": json.dumps(body.geom),
            "properties": json.dumps(body.properties),
            "actor": ctx.ms_object_id,
        })
        await shard_db.commit()
        row = result.mappings().one()
        await refresh_layer_geometry_types(layer_id, shard_db, meta_db)
        await refresh_layer_bbox(layer_id, shard_db, meta_db)
    await _invalidate_after_mutation(layer_id, ctx, meta_db)

    return _row_to_feature(row)


@router.get("/{layer_id}/features/{feature_id}")
async def get_feature(
    layer_id: uuid.UUID,
    feature_id: int,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")

    sql = text("""
        SELECT id, layer_id, ST_AsGeoJSON(geom)::jsonb AS geom,
               properties, version, created_by, updated_by, created_at, updated_at
        FROM features
        WHERE id = :id AND layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
    """)

    async with shard_sessions[layer.shard_id]() as shard_db:
        result = await shard_db.execute(sql, {"id": feature_id, "layer_id": str(layer_id)})
        row = result.mappings().one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Feature not found")
    return _row_to_feature(row)


@router.put("/{layer_id}/features/{feature_id}")
async def update_feature(
    layer_id: uuid.UUID,
    feature_id: int,
    body: FeatureUpdate,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    if layer.is_locked:
        raise HTTPException(status_code=409, detail="Layer is locked")

    set_clauses = ["version = version + 1", "updated_by = :actor", "updated_at = NOW()"]
    params: dict[str, Any] = {
        "id": feature_id,
        "layer_id": str(layer_id),
        "expected_version": body.version,
        "actor": ctx.ms_object_id,
    }

    if body.geom is not None:
        set_clauses.append("geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:geom)), 4326)")
        params["geom"] = json.dumps(body.geom)
    if body.properties is not None:
        set_clauses.append("properties = :properties")
        params["properties"] = json.dumps(body.properties)

    sql = text(f"""
        UPDATE features
        SET {', '.join(set_clauses)}
        WHERE id = :id AND layer_id = CAST(:layer_id AS uuid) AND version = :expected_version AND deleted_at IS NULL
        RETURNING id, layer_id, ST_AsGeoJSON(geom)::jsonb AS geom,
                  properties, version, created_by, updated_by, created_at, updated_at
    """)

    async with shard_sessions[layer.shard_id]() as shard_db:
        result = await shard_db.execute(sql, params)
        await shard_db.commit()
        row = result.mappings().one_or_none()
        if row and body.geom is not None:
            await refresh_layer_geometry_types(layer_id, shard_db, meta_db)
            await refresh_layer_bbox(layer_id, shard_db, meta_db)

    if not row:
        raise HTTPException(status_code=409, detail="Version conflict or feature not found")

    # Always stamp — even for property-only edits (BUG FIX: was inside the geom block)
    await _invalidate_after_mutation(layer_id, ctx, meta_db)

    return _row_to_feature(row)


@router.delete("/{layer_id}/features/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(
    layer_id: uuid.UUID,
    feature_id: int,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "delete"):
        raise HTTPException(status_code=403, detail="Delete permission required")
    if layer.is_locked:
        raise HTTPException(status_code=409, detail="Layer is locked")

    sql = text("""
        UPDATE features
        SET deleted_at = NOW(), deleted_by = :actor
        WHERE id = :id AND layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
    """)

    async with shard_sessions[layer.shard_id]() as shard_db:
        result = await shard_db.execute(sql, {
            "id": feature_id,
            "layer_id": str(layer_id),
            "actor": ctx.ms_object_id,
        })
        await shard_db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Feature not found")
        await refresh_layer_geometry_types(layer_id, shard_db, meta_db)
        await refresh_layer_bbox(layer_id, shard_db, meta_db)
    await _invalidate_after_mutation(layer_id, ctx, meta_db)


@router.post("/{layer_id}/features/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_features(
    layer_id: uuid.UUID,
    body: BulkDeleteRequest,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "delete"):
        raise HTTPException(status_code=403, detail="Delete permission required")
    if layer.is_locked:
        raise HTTPException(status_code=409, detail="Layer is locked")
    if not body.feature_ids:
        return {"deleted": 0}

    sql = text("""
        UPDATE features
        SET deleted_at = NOW(), deleted_by = :actor
        WHERE layer_id = CAST(:layer_id AS uuid)
          AND id = ANY(CAST(:ids AS bigint[]))
          AND deleted_at IS NULL
    """)

    async with shard_sessions[layer.shard_id]() as shard_db:
        result = await shard_db.execute(sql, {
            "layer_id": str(layer_id),
            "ids": body.feature_ids,
            "actor": ctx.ms_object_id,
        })
        await shard_db.commit()
        await refresh_layer_geometry_types(layer_id, shard_db, meta_db)
        await refresh_layer_bbox(layer_id, shard_db, meta_db)
    await _invalidate_after_mutation(layer_id, ctx, meta_db)

    return {"deleted": result.rowcount}
