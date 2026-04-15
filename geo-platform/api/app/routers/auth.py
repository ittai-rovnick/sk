from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.models.users import User
from app.schemas.users import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one()
    return user
