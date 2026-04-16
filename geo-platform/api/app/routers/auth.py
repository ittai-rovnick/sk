import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
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


@router.get("/auto-login", response_model=LoginResponse)
async def auto_login(db: AsyncSession = Depends(get_meta_db)):
    """Detect the current OS user and return a token without requiring manual input.
    Matches the Windows/Linux username against the email prefix (e.g. 'ittai' → 'ittai@...').
    Returns 404 if no matching active user is found.
    """
    os_user = (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip().lower()
    if not os_user:
        raise HTTPException(status_code=404, detail="Could not detect OS user")

    result = await db.execute(
        select(User).where(
            User.is_active == True,
            or_(
                User.email.ilike(f"{os_user}@%"),   # email prefix match
                User.email.ilike(f"{os_user}"),      # exact match
            ),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"No user found for OS user '{os_user}'")

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
