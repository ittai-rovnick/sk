import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.models.layers import Layer
from app.models.symbology import LayerStyle
from app.schemas.symbology import StyleCreate, StyleUpdate, StyleResponse
from app.services.storage_service import upload_lyrx, get_signed_url
from app.config import settings

router = APIRouter(tags=["symbology"])


async def _get_layer(db: AsyncSession, layer_id: uuid.UUID) -> Layer:
    result = await db.execute(
        select(Layer).where(Layer.id == layer_id, Layer.deleted_at.is_(None))
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Layer not found")
    return obj


async def _get_style(db: AsyncSession, layer_id: uuid.UUID, style_id: uuid.UUID) -> LayerStyle:
    result = await db.execute(
        select(LayerStyle).where(
            LayerStyle.id == style_id,
            LayerStyle.layer_id == layer_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Style not found")
    return obj


@router.get("/layers/{layer_id}/styles", response_model=List[StyleResponse])
async def list_styles(
    layer_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    result = await db.execute(
        select(LayerStyle).where(LayerStyle.layer_id == layer_id).order_by(LayerStyle.created_at)
    )
    return result.scalars().all()


@router.post("/layers/{layer_id}/styles", response_model=StyleResponse, status_code=status.HTTP_201_CREATED)
async def create_style(
    layer_id: uuid.UUID,
    body: StyleCreate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "manage_style"):
        raise HTTPException(status_code=403, detail="Manage style permission required")
    await _get_layer(db, layer_id)

    # If this style is default, clear other defaults first
    if body.is_default:
        existing = await db.execute(
            select(LayerStyle).where(LayerStyle.layer_id == layer_id, LayerStyle.is_default == True)
        )
        for s in existing.scalars().all():
            s.is_default = False

    obj = LayerStyle(
        **body.model_dump(),
        layer_id=layer_id,
        created_by=uuid.UUID(ctx.user_id),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/layers/{layer_id}/styles/{style_id}", response_model=StyleResponse)
async def get_style(
    layer_id: uuid.UUID,
    style_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    return await _get_style(db, layer_id, style_id)


@router.put("/layers/{layer_id}/styles/{style_id}", response_model=StyleResponse)
async def update_style(
    layer_id: uuid.UUID,
    style_id: uuid.UUID,
    body: StyleUpdate,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "manage_style"):
        raise HTTPException(status_code=403, detail="Manage style permission required")
    obj = await _get_style(db, layer_id, style_id)

    if body.is_default:
        existing = await db.execute(
            select(LayerStyle).where(LayerStyle.layer_id == layer_id, LayerStyle.is_default == True)
        )
        for s in existing.scalars().all():
            s.is_default = False

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/layers/{layer_id}/styles/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_style(
    layer_id: uuid.UUID,
    style_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "manage_style"):
        raise HTTPException(status_code=403, detail="Manage style permission required")
    obj = await _get_style(db, layer_id, style_id)
    await db.delete(obj)
    await db.commit()


@router.post("/layers/{layer_id}/styles/{style_id}/lyrx")
async def upload_style_lyrx(
    layer_id: uuid.UUID,
    style_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    if not await can_user_do(db, ctx, str(layer_id), "manage_style"):
        raise HTTPException(status_code=403, detail="Manage style permission required")
    obj = await _get_style(db, layer_id, style_id)
    file_bytes = await file.read()
    key = await upload_lyrx(str(layer_id), file_bytes, file.filename or f"{style_id}.lyrx")
    obj.lyrx_s3_key = key
    await db.commit()
    return {"key": key}


@router.get("/layers/{layer_id}/styles/{style_id}/lyrx")
async def get_style_lyrx_url(
    layer_id: uuid.UUID,
    style_id: uuid.UUID,
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(db, layer_id)
    obj = await _get_style(db, layer_id, style_id)
    if not obj.lyrx_s3_key:
        raise HTTPException(status_code=404, detail="No lyrx file uploaded for this style")
    url = await get_signed_url(settings.storage_bucket_styles, obj.lyrx_s3_key)
    return {"url": url}
