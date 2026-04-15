import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.models.layers import Layer, LayerOwner, LayerSchema
from app.schemas.layers import (
    LayerCreate, LayerUpdate, LayerResponse,
    LockRequest, LayerSchemaUpdate,
)
from app.services.storage_service import upload_lyrx

router = APIRouter(prefix="/layers", tags=["layers"])


async def _get_layer(db: AsyncSession, layer_id: uuid.UUID) -> Layer:
    result = await db.execute(
        select(Layer).where(Layer.id == layer_id, Layer.deleted_at.is_(None))
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Layer not found")
    return obj


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
    # Make creator a primary owner
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
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    obj.updated_at = datetime.now(timezone.utc)
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
    # Only the locker or a superadmin can unlock
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
