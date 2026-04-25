"""Map endpoints: CRUD + /open tree + /freshness + groups + layer membership + versions."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.cache import cache_delete
from app.models.layers import Layer
from app.models.maps import Map, MapGroup, MapLayer
from app.models.permissions import Permission
from app.schemas.layers import (
    VersionListItem, VersionDetail, VersionRestoreResponse,
)
from app.schemas.maps import (
    MapCreate, MapUpdate, MapResponse,
    MapGroupCreate, MapGroupUpdate, MapGroupResponse,
    MapLayerAdd, MapLayerUpdate, MapLayerResponse,
    MapOpenResponse, MapFreshnessResponse,
    GroupPermissionGrantRequest, GroupPermissionGrantResponse,
)
from app.services import map_service, version_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maps", tags=["maps"])


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_map_or_404(db: AsyncSession, map_id: uuid.UUID) -> Map:
    obj = await map_service.get_map(db, map_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Map not found")
    return obj


async def _check_map_perm(db: AsyncSession, ctx: RequestContext, map_id: uuid.UUID, op: str) -> None:
    if not await can_user_do(db, ctx, str(map_id), op):
        raise HTTPException(status_code=403, detail=f"{op.title()} permission required")


# ── Map CRUD ───────────────────────────────────────────────────────────────────

@router.post("", response_model=MapResponse, status_code=status.HTTP_201_CREATED)
async def create_map_endpoint(
    body: MapCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    obj = await map_service.create_map(db, body, ctx.user_id)
    return MapResponse(**map_service.map_to_response_dict(obj, extent=None))


@router.get("", response_model=List[MapResponse])
async def list_maps_endpoint(
    database_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    maps = await map_service.list_maps(db, database_id)
    out = []
    for m in maps:
        ext = await map_service.get_map_extent(db, m.id)
        out.append(MapResponse(**map_service.map_to_response_dict(m, extent=ext)))
    return out


@router.get("/{map_id}", response_model=MapResponse)
async def get_map_endpoint(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    obj = await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "read")
    ext = await map_service.get_map_extent(db, map_id)
    return MapResponse(**map_service.map_to_response_dict(obj, extent=ext))


@router.put("/{map_id}", response_model=MapResponse)
async def update_map_endpoint(
    map_id: uuid.UUID,
    body: MapUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    obj = await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "write")

    # Snapshot for version recording
    before = {f: getattr(obj, f) for f in version_service.MAP_VERSION_FIELDS}
    updates = body.model_dump(exclude_unset=True)
    changed = [f for f, v in updates.items() if v != before.get(f)]
    for f, v in updates.items():
        setattr(obj, f, v)
    obj.updated_by = uuid.UUID(ctx.user_id)
    obj.updated_at = datetime.now(timezone.utc)

    if changed:
        await version_service.record_version(
            db, "map", map_id, before, changed, ctx.user_id
        )
    await db.commit()
    await db.refresh(obj)
    ext = await map_service.get_map_extent(db, map_id)
    return MapResponse(**map_service.map_to_response_dict(obj, extent=ext))


@router.delete("/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map_endpoint(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _check_map_perm(db, ctx, map_id, "delete")
    ok = await map_service.delete_map(db, map_id, ctx.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Map not found")


# ── /open with ETag ────────────────────────────────────────────────────────────

@router.get("/{map_id}/open", response_model=MapOpenResponse)
async def open_map(
    map_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
):
    obj = await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "read")

    # max(features_updated_at) across layers in this map for ETag freshness
    ts_row = await db.execute(
        text("""
            SELECT COALESCE(MAX(l.features_updated_at), m.content_updated_at) AS ts
            FROM maps m
            LEFT JOIN map_layers ml ON ml.map_id = m.id
            LEFT JOIN layers l ON l.id = ml.layer_id AND l.deleted_at IS NULL
            WHERE m.id = CAST(:mid AS uuid)
            GROUP BY m.id, m.content_updated_at
        """),
        {"mid": str(map_id)},
    )
    ts_val: datetime | None = ts_row.scalar_one_or_none()
    ts_int = int(ts_val.timestamp()) if ts_val else 0
    etag = f'"{map_id}-{obj.content_version}-{ts_int}"'

    if if_none_match == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        response.headers["ETag"] = etag
        return Response(status_code=304, headers={"ETag": etag})

    flat = await map_service.get_map_layer_tree(db, map_id)
    tree = map_service.assemble_tree(flat)
    response.headers["ETag"] = etag
    ext = await map_service.get_map_extent(db, map_id)
    return MapOpenResponse(
        map=MapResponse(**map_service.map_to_response_dict(obj, extent=ext)),
        tree=tree,
    )


# ── /freshness ─────────────────────────────────────────────────────────────────

@router.get("/{map_id}/freshness", response_model=MapFreshnessResponse)
async def map_freshness(
    map_id: uuid.UUID,
    since: datetime,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "read")
    try:
        result = await map_service.get_map_freshness(db, map_id, since)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    return MapFreshnessResponse(**result)


# ── Map Groups ─────────────────────────────────────────────────────────────────

@router.get("/{map_id}/groups", response_model=List[MapGroupResponse])
async def list_map_groups(
    map_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "read")
    result = await db.execute(
        select(MapGroup).where(MapGroup.map_id == map_id).order_by(MapGroup.sort_order)
    )
    return list(result.scalars().all())


@router.post("/{map_id}/groups", response_model=MapGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_map_group_endpoint(
    map_id: uuid.UUID,
    body: MapGroupCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "write")
    try:
        return await map_service.create_map_group(db, map_id, body, ctx.user_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.put("/{map_id}/groups/{group_id}", response_model=MapGroupResponse)
async def update_map_group_endpoint(
    map_id: uuid.UUID,
    group_id: uuid.UUID,
    body: MapGroupUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _check_map_perm(db, ctx, map_id, "write")
    obj = await map_service.update_map_group(db, map_id, group_id, body)
    if not obj:
        raise HTTPException(status_code=404, detail="Group not found")
    return obj


@router.delete("/{map_id}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map_group_endpoint(
    map_id: uuid.UUID,
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _check_map_perm(db, ctx, map_id, "write")
    ok = await map_service.delete_map_group(db, map_id, group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found")


# ── Map Layers (membership) ────────────────────────────────────────────────────

@router.post("/{map_id}/layers", response_model=MapLayerResponse, status_code=status.HTTP_201_CREATED)
async def add_layer_endpoint(
    map_id: uuid.UUID,
    body: MapLayerAdd,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "write")
    return await map_service.add_layer_to_map(db, map_id, body, ctx.user_id)


@router.delete("/{map_id}/layers/{layer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_layer_endpoint(
    map_id: uuid.UUID,
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _check_map_perm(db, ctx, map_id, "write")
    ok = await map_service.remove_layer_from_map(db, map_id, layer_id, ctx.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Map layer not found")


@router.put("/{map_id}/layers/{layer_id}", response_model=MapLayerResponse)
async def update_map_layer_endpoint(
    map_id: uuid.UUID,
    layer_id: uuid.UUID,
    body: MapLayerUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _check_map_perm(db, ctx, map_id, "write")
    obj = await map_service.update_map_layer(db, map_id, layer_id, body)
    if not obj:
        raise HTTPException(status_code=404, detail="Map layer not found")
    return obj


# ── Bulk group permission grant ────────────────────────────────────────────────

@router.post(
    "/{map_id}/groups/{group_id}/permissions",
    response_model=GroupPermissionGrantResponse,
)
async def grant_group_permissions(
    map_id: uuid.UUID,
    group_id: uuid.UUID,
    body: GroupPermissionGrantRequest,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not (body.ms_user_id or body.ms_group_id):
        raise HTTPException(status_code=400, detail="ms_user_id or ms_group_id required")
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "manage_perms")

    layer_ids = await map_service.expand_group_layers(db, map_id, group_id)
    granted = 0
    for lid in layer_ids:
        perm = Permission(
            ms_user_id=body.ms_user_id,
            ms_group_id=body.ms_group_id,
            layer_id=lid,
            role_id=body.role_id,
            allow=body.allow,
            granted_by=uuid.UUID(ctx.user_id),
        )
        db.add(perm)
        granted += 1
    await db.commit()
    return GroupPermissionGrantResponse(granted=granted, layer_ids=layer_ids)


# ── Version endpoints ──────────────────────────────────────────────────────────

@router.get("/{map_id}/versions", response_model=List[VersionListItem])
async def list_map_versions(
    map_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "read")
    rows = await version_service.get_versions(db, "map", map_id, limit, offset)
    return [VersionListItem(**r) for r in rows]


@router.get("/{map_id}/versions/{version}", response_model=VersionDetail)
async def get_map_version(
    map_id: uuid.UUID,
    version: int,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "read")
    row = await version_service.get_version(db, "map", map_id, version)
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionDetail(**row)


@router.post("/{map_id}/versions/{version}/restore", response_model=VersionRestoreResponse)
async def restore_map_version(
    map_id: uuid.UUID,
    version: int,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_map_or_404(db, map_id)
    await _check_map_perm(db, ctx, map_id, "write")
    try:
        result = await version_service.restore_version(db, "map", map_id, version, ctx.user_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    await cache_delete(f"maptree:{map_id}")
    return VersionRestoreResponse(**result)
