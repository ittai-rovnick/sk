import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.groups import MsGroup

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupResponse(BaseModel):
    id: uuid.UUID
    ms_group_id: str
    display_name: Optional[str]
    description: Optional[str]
    synced_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=List[GroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(MsGroup).order_by(MsGroup.display_name))
    return result.scalars().all()


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(MsGroup).where(MsGroup.id == group_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Group not found")
    return obj
