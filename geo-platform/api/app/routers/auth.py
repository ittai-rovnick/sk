import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.local import create_token
from app.models.users import User
from app.schemas.users import UserResponse
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_meta_db),
):
    """Log in with a username. Returns a bearer token."""
    result = await db.execute(
        select(User).where(User.email == body.username, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    token = create_token(user)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))


@router.get("/auto-login", response_model=LoginResponse)
async def auto_login(db: AsyncSession = Depends(get_meta_db)):
    """Read %USERNAME% from the OS and log in automatically.
    In DEV_MODE, creates the user as superadmin on first login if they don't exist yet.
    """
    os_user = (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip()
    if not os_user:
        raise HTTPException(status_code=404, detail="Could not detect OS user")

    result = await db.execute(
        select(User).where(User.email.ilike(os_user), User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        if not settings.dev_mode:
            raise HTTPException(status_code=404, detail=f"No user '{os_user}' — ask an admin to create your account")
        # DEV_MODE: auto-create on first login
        user = User(
            email=os_user,
            display_name=os_user,
            is_superadmin=True,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

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
