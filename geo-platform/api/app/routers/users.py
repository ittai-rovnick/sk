import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.users import User
from app.schemas.users import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    q = select(User).order_by(User.email)
    if is_active is not None:
        q = q.where(User.is_active == is_active)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(ctx.user_id)))
    return result.scalar_one()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin and str(user_id) != ctx.user_id:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(User).where(User.id == user_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    return obj


@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(User).where(User.id == user_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    obj.is_active = False
    obj.deactivated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(User).where(User.id == user_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    obj.is_active = True
    obj.deactivated_at = None
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{user_id}/make-superadmin", response_model=UserResponse)
async def make_superadmin(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(User).where(User.id == user_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="User not found")
    obj.is_superadmin = True
    await db.commit()
    await db.refresh(obj)
    return obj
