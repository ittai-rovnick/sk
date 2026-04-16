from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.local import create_token
from app.models.users import User
from app.schemas.users import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str  # email address


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_meta_db),
):
    """Log in with a username (email). Returns a bearer token for subsequent requests."""
    result = await db.execute(
        select(User).where(User.email == body.username, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    token = create_token(user)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def get_me(
    db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one()
    return user
