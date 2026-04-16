import uuid
import json
from datetime import datetime, timezone
from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.models.layers import Layer
from app.schemas.features import FeatureCreate, FeatureUpdate, FeatureResponse, BboxQuery
from app.db.session import shard_sessions

router = APIRouter(prefix="/layers", tags=["features"])


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


@router.get("/{layer_id}/features")
async def list_features(
    layer_id: uuid.UUID,
    limit: int = 1000,
    offset: int = 0,
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")

    bbox_filter = ""
    params: dict[str, Any] = {
        "layer_id": str(layer_id),
        "limit": limit,
        "offset": offset,
    }
    if all(v is not None for v in [min_lon, min_lat, max_lon, max_lat]):
        bbox_filter = "AND ST_Intersects(geom, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
        params.update({"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat})

    sql = text(f"""
        SELECT id, layer_id, ST_AsGeoJSON(geom)::jsonb AS geom,
               properties, version, created_by, updated_by, created_at, updated_at
        FROM features
        WHERE layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
        {bbox_filter}
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

    if not row:
        raise HTTPException(status_code=409, detail="Version conflict or feature not found")
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
