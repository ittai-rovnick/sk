import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.layers import GroupLayer
from app.schemas.layers import GroupLayerCreate, GroupLayerUpdate, GroupLayerResponse

router = APIRouter(prefix="/group-layers", tags=["group-layers"])


@router.get("", response_model=List[GroupLayerResponse])
async def list_group_layers(
    database_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    q = select(GroupLayer).where(GroupLayer.deleted_at.is_(None))
    if database_id:
        q = q.where(GroupLayer.database_id == database_id)
    q = q.order_by(GroupLayer.sort_order, GroupLayer.name)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=GroupLayerResponse, status_code=status.HTTP_201_CREATED)
async def create_group_layer(
    body: GroupLayerCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    obj = GroupLayer(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{group_layer_id}", response_model=GroupLayerResponse)
async def get_group_layer(
    group_layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(
        select(GroupLayer).where(
            GroupLayer.id == group_layer_id,
            GroupLayer.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group layer not found")
    return obj


@router.put("/{group_layer_id}", response_model=GroupLayerResponse)
async def update_group_layer(
    group_layer_id: uuid.UUID,
    body: GroupLayerUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(
        select(GroupLayer).where(
            GroupLayer.id == group_layer_id,
            GroupLayer.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group layer not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{group_layer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_layer(
    group_layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(
        select(GroupLayer).where(
            GroupLayer.id == group_layer_id,
            GroupLayer.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group layer not found")
    obj.deleted_at = datetime.now(timezone.utc)
    obj.deleted_by = uuid.UUID(ctx.user_id)
    await db.commit()
