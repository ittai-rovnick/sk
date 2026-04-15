import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.databases import GeoDatabase

router = APIRouter(prefix="/databases", tags=["databases"])


class DatabaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    default_srid: int = 4326
    tags: List[str] = []


class DatabaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_srid: Optional[int] = None
    tags: Optional[List[str]] = None


class DatabaseResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    default_srid: int
    tags: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=List[DatabaseResponse])
async def list_databases(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(GeoDatabase).order_by(GeoDatabase.name))
    return result.scalars().all()


@router.post("", response_model=DatabaseResponse, status_code=status.HTTP_201_CREATED)
async def create_database(
    body: DatabaseCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    obj = GeoDatabase(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{database_id}", response_model=DatabaseResponse)
async def get_database(
    database_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(GeoDatabase).where(GeoDatabase.id == database_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Database not found")
    return obj


@router.put("/{database_id}", response_model=DatabaseResponse)
async def update_database(
    database_id: uuid.UUID,
    body: DatabaseUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(GeoDatabase).where(GeoDatabase.id == database_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Database not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{database_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_database(
    database_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(GeoDatabase).where(GeoDatabase.id == database_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Database not found")
    await db.delete(obj)
    await db.commit()
