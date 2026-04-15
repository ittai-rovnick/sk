import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.permissions import Permission, Role
from app.schemas.permissions import PermissionGrant, PermissionResponse

router = APIRouter(tags=["permissions"])


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    can_read: bool
    can_write: bool
    can_delete: bool
    can_export: bool
    can_manage_style: bool
    can_manage_perms: bool
    can_publish: bool
    is_system_role: bool

    model_config = {"from_attributes": True}


@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(Role).order_by(Role.name))
    return result.scalars().all()


@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    layer_id: Optional[uuid.UUID] = None,
    database_id: Optional[uuid.UUID] = None,
    group_layer_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    q = select(Permission)
    if layer_id:
        q = q.where(Permission.layer_id == layer_id)
    if database_id:
        q = q.where(Permission.database_id == database_id)
    if group_layer_id:
        q = q.where(Permission.group_layer_id == group_layer_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/permissions", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
async def grant_permission(
    body: PermissionGrant,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    # Require manage_perms on the target resource or superadmin
    if not ctx.is_superadmin:
        target_layer_id = str(body.layer_id) if body.layer_id else None
        if target_layer_id:
            from app.auth.permissions import can_user_do
            if not await can_user_do(db, ctx, target_layer_id, "manage_perms"):
                raise HTTPException(status_code=403, detail="Manage permissions required")
        else:
            raise HTTPException(status_code=403, detail="Superadmin required for database/group-layer permissions")

    obj = Permission(
        **body.model_dump(),
        granted_by=uuid.UUID(ctx.user_id),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_permission(
    permission_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(Permission).where(Permission.id == permission_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Permission not found")

    if not ctx.is_superadmin:
        if obj.layer_id:
            from app.auth.permissions import can_user_do
            if not await can_user_do(db, ctx, str(obj.layer_id), "manage_perms"):
                raise HTTPException(status_code=403, detail="Manage permissions required")
        else:
            raise HTTPException(status_code=403, detail="Superadmin required")

    await db.delete(obj)
    await db.commit()
