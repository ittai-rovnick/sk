from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.services import layer_service

router = APIRouter(prefix="/databases", tags=["databases"])

# TODO: implement in Phase 4
