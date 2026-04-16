from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.config import settings
from app.auth.models import RequestContext
from app.models.users import User
from app.models.groups import CustomGroupMember, CustomGroupMsLink, MsGroup

TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "is_superadmin": user.is_superadmin,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=TOKEN_ALGORITHM)


async def validate_token(token: str, db: AsyncSession) -> RequestContext | None:
    try:
        payload = jwt.decode(token, settings.api_secret_key, algorithms=[TOKEN_ALGORITHM])
        user_id: str = payload["sub"]
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        return None

    # Update last seen
    await db.execute(
        update(User).where(User.id == user.id).values(last_seen_at=datetime.now(timezone.utc))
    )
    await db.commit()

    custom_group_ids = await _resolve_custom_group_ids(db, user.id)

    return RequestContext(
        ms_object_id=str(user.id),
        ms_group_ids=custom_group_ids,
        user_id=str(user.id),
        is_superadmin=user.is_superadmin,
    )


async def _resolve_custom_group_ids(db: AsyncSession, user_id) -> list[str]:
    """Return ms_group_id strings for all custom groups this user belongs to directly."""
    rows = await db.execute(
        select(MsGroup.ms_group_id)
        .join(CustomGroupMember, CustomGroupMember.group_id == MsGroup.id)
        .where(CustomGroupMember.user_id == user_id)
    )
    return [row[0] for row in rows.all()]
