import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.rasters import RasterCatalog

router = APIRouter(prefix="/rasters", tags=["rasters"])


class RasterCreate(BaseModel):
    database_id: Optional[uuid.UUID] = None
    group_layer_id: Optional[uuid.UUID] = None
    name: str
    s3_key: str
    format: str = "COG"
    srid: int = 4326
    resolution_m: Optional[float] = None
    band_count: Optional[int] = None
    tags: List[str] = []


class RasterUpdate(BaseModel):
    name: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    resolution_m: Optional[float] = None
    band_count: Optional[int] = None
    group_layer_id: Optional[uuid.UUID] = None


class RasterResponse(BaseModel):
    id: uuid.UUID
    database_id: Optional[uuid.UUID]
    group_layer_id: Optional[uuid.UUID]
    name: str
    s3_key: str
    format: str
    srid: int
    resolution_m: Optional[float]
    band_count: Optional[int]
    tags: List[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=List[RasterResponse])
async def list_rasters(
    database_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    q = select(RasterCatalog).order_by(RasterCatalog.name)
    if database_id:
        q = q.where(RasterCatalog.database_id == database_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=RasterResponse, status_code=status.HTTP_201_CREATED)
async def create_raster(
    body: RasterCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    obj = RasterCatalog(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{raster_id}", response_model=RasterResponse)
async def get_raster(
    raster_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(RasterCatalog).where(RasterCatalog.id == raster_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Raster not found")
    return obj


@router.put("/{raster_id}", response_model=RasterResponse)
async def update_raster(
    raster_id: uuid.UUID,
    body: RasterUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(RasterCatalog).where(RasterCatalog.id == raster_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Raster not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{raster_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_raster(
    raster_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    result = await db.execute(select(RasterCatalog).where(RasterCatalog.id == raster_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Raster not found")
    await db.delete(obj)
    await db.commit()
