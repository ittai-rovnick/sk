import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.cache import cache_delete
from app.db.session import shard_sessions
from app.models.layers import Layer, LayerOwner, LayerSchema, GroupLayer
from app.models.expressions import SavedExpression
from app.schemas.layers import (
    LayerCreate, LayerUpdate, LayerResponse,
    LockRequest, LayerSchemaUpdate,
    LayerIdentifyRequest, LayerIdentifyResponse,
    LayerIdentifyLayerNode, LayerIdentifyGroupNode,
    GEOJSON_GEOMETRY_TYPES,
    VersionListItem, VersionDetail, VersionRestoreResponse,
    ExpressionCreate, ExpressionUpdate, ExpressionResponse, ExpressionListItem,
)
from app.services.feature_filter import compile_expression
from app.services.storage_service import upload_lyrx
from app.services import version_service, export_service, stats_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/layers", tags=["layers"])


async def _get_layer(db: AsyncSession, layer_id: uuid.UUID) -> Layer:
    result = await db.execute(
        select(Layer).where(Layer.id == layer_id, Layer.deleted_at.is_(None))
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Layer not found")
    return obj


def _layer_bbox(layer: Layer) -> list[float] | None:
    # The Layer ORM doesn't surface bbox as a list — read separately when needed
    return None


# ────────────────────────────────────────────────────────────────────────────────
# IDENTIFY — must be registered BEFORE /{layer_id} routes
# ────────────────────────────────────────────────────────────────────────────────

@router.post("/identify", response_model=LayerIdentifyResponse)
async def identify_layers_by_polygon(
    body: LayerIdentifyRequest,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    """Returns the group/layer tree of the database with feature_count_in_area per layer.

    A polygon (or any GeoJSON geometry) is intersected against features in each
    accessible layer. Layers the user cannot read are entirely absent.
    """
    geom_type = body.geometry.get("type")
    if geom_type not in GEOJSON_GEOMETRY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported geometry type: {geom_type}",
        )

    # Load all layers in the database
    result = await meta_db.execute(
        select(Layer)
        .where(Layer.database_id == body.database_id, Layer.deleted_at.is_(None))
        .order_by(Layer.sort_order, Layer.name)
    )
    all_layers = list(result.scalars().all())

    # Filter to readable
    readable: list[Layer] = []
    for layer in all_layers:
        if await can_user_do(meta_db, ctx, str(layer.id), "read"):
            readable.append(layer)
    if not readable:
        return LayerIdentifyResponse(tree=[])

    # Group by shard, run a single COUNT(*) GROUP BY layer_id per shard
    by_shard: dict[int, list[Layer]] = defaultdict(list)
    for layer in readable:
        by_shard[layer.shard_id].append(layer)

    counts: dict[uuid.UUID, int] = {}
    geom_json = json.dumps(body.geometry)
    for shard_id, layers in by_shard.items():
        ids = [str(layer.id) for layer in layers]
        async with shard_sessions[shard_id]() as shard_db:
            res = await shard_db.execute(
                text("""
                    SELECT layer_id, COUNT(*)::int AS cnt
                    FROM features
                    WHERE layer_id = ANY(CAST(:ids AS uuid[]))
                      AND deleted_at IS NULL
                      AND ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
                    GROUP BY layer_id
                """),
                {"ids": ids, "geom": geom_json},
            )
            for row in res.all():
                counts[row[0]] = int(row[1])

    # Read bboxes for layers (convert WKT envelope → [x,y,x,y])
    bboxes: dict[uuid.UUID, list[float] | None] = {}
    for layer in readable:
        bbox_row = await meta_db.execute(
            text(
                "SELECT ST_XMin(bbox)::float8, ST_YMin(bbox)::float8, "
                "ST_XMax(bbox)::float8, ST_YMax(bbox)::float8 "
                "FROM layers WHERE id = CAST(:id AS uuid) AND bbox IS NOT NULL"
            ),
            {"id": str(layer.id)},
        )
        ext = bbox_row.one_or_none()
        bboxes[layer.id] = list(ext) if ext else None

    # Build group → layers map
    group_ids = {layer.group_layer_id for layer in readable if layer.group_layer_id is not None}
    group_objs: dict[uuid.UUID, GroupLayer] = {}
    if group_ids:
        gres = await meta_db.execute(
            select(GroupLayer).where(GroupLayer.id.in_(group_ids))
        )
        group_objs = {g.id: g for g in gres.scalars().all()}

    grouped: dict[uuid.UUID | None, list[LayerIdentifyLayerNode]] = defaultdict(list)
    for layer in readable:
        node = LayerIdentifyLayerNode(
            layer_id=layer.id,
            name=layer.name,
            feature_count_in_area=counts.get(layer.id, 0),
            geometry_types=layer.geometry_types or [],
            bbox=bboxes.get(layer.id),
        )
        grouped[layer.group_layer_id].append(node)

    tree: list = []
    # Root-level layers (no group)
    for node in grouped.get(None, []):
        tree.append(node)
    # Grouped layers
    for gid, nodes in grouped.items():
        if gid is None:
            continue
        g = group_objs.get(gid)
        if not g:
            # Group missing (shouldn't happen) — fall back to root
            tree.extend(nodes)
            continue
        total = sum(n.feature_count_in_area for n in nodes)
        tree.append(LayerIdentifyGroupNode(
            id=g.id,
            name=g.name,
            features_in_area=total,
            children=nodes,
        ))

    return LayerIdentifyResponse(tree=tree)


# ────────────────────────────────────────────────────────────────────────────────
# Layer CRUD
# ────────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[LayerResponse])
async def list_layers(
    database_id: Optional[uuid.UUID] = None,
    group_layer_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    q = select(Layer).where(Layer.deleted_at.is_(None))
    if database_id:
        q = q.where(Layer.database_id == database_id)
    if group_layer_id:
        q = q.where(Layer.group_layer_id == group_layer_id)
    q = q.order_by(Layer.sort_order, Layer.name)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=LayerResponse, status_code=status.HTTP_201_CREATED)
async def create_layer(
    body: LayerCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    obj = Layer(**body.model_dump())
    db.add(obj)
    await db.flush()
    owner = LayerOwner(
        layer_id=obj.id,
        user_id=uuid.UUID(ctx.user_id),
        is_primary=True,
        assigned_by=uuid.UUID(ctx.user_id),
    )
    db.add(owner)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{layer_id}", response_model=LayerResponse)
async def get_layer(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    return await _get_layer(db, layer_id)


@router.put("/{layer_id}", response_model=LayerResponse)
async def update_layer(
    layer_id: uuid.UUID,
    body: LayerUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    obj = await _get_layer(db, layer_id)

    # Capture pre-update snapshot for version history
    before = {f: getattr(obj, f) for f in version_service.LAYER_VERSION_FIELDS}

    updates = body.model_dump(exclude_none=True)
    changed = [f for f, v in updates.items() if f in before and v != before[f]]
    for field, value in updates.items():
        setattr(obj, field, value)
    obj.updated_at = datetime.now(timezone.utc)
    obj.updated_by = uuid.UUID(ctx.user_id)

    if changed:
        await version_service.record_version(
            db, "layer", layer_id, before, changed, ctx.user_id
        )
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{layer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_layer(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "delete"):
        raise HTTPException(status_code=403, detail="Delete permission required")
    obj = await _get_layer(db, layer_id)
    obj.deleted_at = datetime.now(timezone.utc)
    obj.deleted_by = uuid.UUID(ctx.user_id)
    await db.commit()


@router.post("/{layer_id}/lock", response_model=LayerResponse)
async def lock_layer(
    layer_id: uuid.UUID,
    body: LockRequest,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    obj = await _get_layer(db, layer_id)
    if obj.is_locked:
        raise HTTPException(status_code=409, detail="Layer is already locked")
    obj.is_locked = True
    obj.locked_by = uuid.UUID(ctx.user_id)
    obj.locked_at = datetime.now(timezone.utc)
    obj.lock_reason = body.reason
    obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{layer_id}/lock", response_model=LayerResponse)
async def unlock_layer(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    obj = await _get_layer(db, layer_id)
    if not ctx.is_superadmin and str(obj.locked_by) != ctx.user_id:
        raise HTTPException(status_code=403, detail="Only the lock owner or superadmin can unlock")
    obj.is_locked = False
    obj.locked_by = None
    obj.locked_at = None
    obj.lock_reason = None
    obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{layer_id}/schema")
async def get_layer_schema(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    result = await db.execute(
        select(LayerSchema).where(LayerSchema.layer_id == layer_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return {"layer_id": layer_id, "json_schema": {}, "schema_version": 0}
    return {
        "layer_id": obj.layer_id,
        "json_schema": obj.json_schema,
        "schema_version": obj.schema_version,
        "updated_at": obj.updated_at,
    }


@router.put("/{layer_id}/schema")
async def update_layer_schema(
    layer_id: uuid.UUID,
    body: LayerSchemaUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    await _get_layer(db, layer_id)
    result = await db.execute(
        select(LayerSchema).where(LayerSchema.layer_id == layer_id)
    )
    obj = result.scalar_one_or_none()
    if obj:
        obj.json_schema = body.json_schema
        obj.schema_version += 1
        obj.updated_by = uuid.UUID(ctx.user_id)
        obj.updated_at = datetime.now(timezone.utc)
    else:
        obj = LayerSchema(
            layer_id=layer_id,
            json_schema=body.json_schema,
            schema_version=1,
            updated_by=uuid.UUID(ctx.user_id),
        )
        db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"layer_id": obj.layer_id, "json_schema": obj.json_schema, "schema_version": obj.schema_version}


@router.get("/{layer_id}/stats")
async def get_layer_stats_endpoint(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")
    layer = await _get_layer(db, layer_id)
    schema_res = await db.execute(
        select(LayerSchema).where(LayerSchema.layer_id == layer_id)
    )
    schema_obj = schema_res.scalar_one_or_none()
    json_schema = schema_obj.json_schema if schema_obj else None
    async with shard_sessions[layer.shard_id]() as shard_db:
        return await stats_service.get_layer_stats(shard_db, layer_id, json_schema)


FORMAT_MEDIA = {
    "geojson":   ("application/geo+json", "geojson"),
    "shapefile": ("application/zip",      "zip"),
    "gpkg":      ("application/geopackage+sqlite3", "gpkg"),
}


@router.get("/{layer_id}/export")
async def export_layer(
    layer_id: uuid.UUID,
    request: Request,
    format: str = "geojson",
    srid: int | None = None,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if format not in FORMAT_MEDIA:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Allowed: {sorted(FORMAT_MEDIA)}",
        )
    if not await can_user_do(db, ctx, str(layer_id), "export"):
        raise HTTPException(status_code=403, detail="Export permission required")
    layer = await _get_layer(db, layer_id)

    target_srid = srid if srid is not None else 4326
    if srid is not None and not export_service.validate_srid(request.app.state, srid):
        raise HTTPException(status_code=400, detail=f"Unknown SRID: {srid}")

    async with shard_sessions[layer.shard_id]() as shard_db:
        if format == "geojson":
            payload = await export_service.export_geojson(shard_db, layer, target_srid)
        elif format == "shapefile":
            payload = await export_service.export_shapefile(shard_db, db, layer, target_srid)
        else:
            payload = await export_service.export_gpkg(shard_db, db, layer, target_srid)

    media_type, ext = FORMAT_MEDIA[format]
    safe_name = (layer.name or "layer").replace('"', "").replace("/", "_").replace("\\", "_")
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.{ext}"'},
    )


@router.post("/{layer_id}/lyrx")
async def upload_layer_lyrx(
    layer_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "manage_style"):
        raise HTTPException(status_code=403, detail="Manage style permission required")
    obj = await _get_layer(db, layer_id)
    file_bytes = await file.read()
    key = await upload_lyrx(str(layer_id), file_bytes, file.filename or "style.lyrx")
    obj.lyrx_s3_key = key
    obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"key": key}


# ────────────────────────────────────────────────────────────────────────────────
# Saved Expressions (DSL filter library)
# ────────────────────────────────────────────────────────────────────────────────

async def _get_layer_schema_fields(db: AsyncSession, layer_id: uuid.UUID) -> set[str]:
    res = await db.execute(
        select(LayerSchema).where(LayerSchema.layer_id == layer_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        return set()
    fields = (obj.json_schema or {}).get("fields", [])
    return {f["name"] for f in fields if isinstance(f, dict) and "name" in f}


@router.post("/{layer_id}/expressions", response_model=ExpressionResponse, status_code=status.HTTP_201_CREATED)
async def create_expression(
    layer_id: uuid.UUID,
    body: ExpressionCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    schema_fields = await _get_layer_schema_fields(db, layer_id)
    try:
        compile_expression(body.expression, schema_fields, {})
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    obj = SavedExpression(
        layer_id=layer_id,
        name=body.name,
        description=body.description,
        expression=body.expression,
        created_by=uuid.UUID(ctx.user_id),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{layer_id}/expressions", response_model=List[ExpressionListItem])
async def list_expressions(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")
    res = await db.execute(
        select(SavedExpression)
        .where(SavedExpression.layer_id == layer_id)
        .order_by(SavedExpression.name)
    )
    return list(res.scalars().all())


@router.get("/{layer_id}/expressions/{expression_id}", response_model=ExpressionResponse)
async def get_expression(
    layer_id: uuid.UUID,
    expression_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")
    res = await db.execute(
        select(SavedExpression).where(
            SavedExpression.id == expression_id,
            SavedExpression.layer_id == layer_id,
        )
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Expression not found")
    return obj


@router.put("/{layer_id}/expressions/{expression_id}", response_model=ExpressionResponse)
async def update_expression(
    layer_id: uuid.UUID,
    expression_id: uuid.UUID,
    body: ExpressionUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    res = await db.execute(
        select(SavedExpression).where(
            SavedExpression.id == expression_id,
            SavedExpression.layer_id == layer_id,
        )
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Expression not found")

    if body.expression is not None:
        schema_fields = await _get_layer_schema_fields(db, layer_id)
        try:
            compile_expression(body.expression, schema_fields, {})
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    await cache_delete(f"expr:{expression_id}")
    return obj


@router.delete("/{layer_id}/expressions/{expression_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expression(
    layer_id: uuid.UUID,
    expression_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    res = await db.execute(
        select(SavedExpression).where(
            SavedExpression.id == expression_id,
            SavedExpression.layer_id == layer_id,
        )
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Expression not found")
    await db.delete(obj)
    await db.commit()
    await cache_delete(f"expr:{expression_id}")


# ────────────────────────────────────────────────────────────────────────────────
# Layer version history
# ────────────────────────────────────────────────────────────────────────────────

@router.get("/{layer_id}/versions", response_model=List[VersionListItem])
async def list_layer_versions(
    layer_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")
    rows = await version_service.get_versions(db, "layer", layer_id, limit, offset)
    return [VersionListItem(**r) for r in rows]


@router.get("/{layer_id}/versions/{version}", response_model=VersionDetail)
async def get_layer_version(
    layer_id: uuid.UUID,
    version: int,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")
    row = await version_service.get_version(db, "layer", layer_id, version)
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionDetail(**row)


@router.post("/{layer_id}/versions/{version}/restore", response_model=VersionRestoreResponse)
async def restore_layer_version(
    layer_id: uuid.UUID,
    version: int,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    if not await can_user_do(db, ctx, str(layer_id), "write"):
        raise HTTPException(status_code=403, detail="Write permission required")
    try:
        result = await version_service.restore_version(db, "layer", layer_id, version, ctx.user_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    return VersionRestoreResponse(**result)
