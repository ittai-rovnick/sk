from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from app.config import settings
from app.auth.models import RequestContext
from app.models.users import User
from app.models.groups import CustomGroupMember, CustomGroupMsLink, MsGroup
from app.cache import cache_get, cache_set

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

    # Debounce last_seen_at writes to at most once per 60 seconds per user
    debounce_key = f"lastseen:{str(user.id)}"
    if await cache_get(debounce_key) is None:
        await db.execute(
            update(User).where(User.id == user.id).values(last_seen_at=datetime.now(timezone.utc))
        )
        await db.commit()
        await cache_set(debounce_key, 1, ttl=60)

    custom_group_ids = await _resolve_custom_group_ids(db, user.id)

    return RequestContext(
        ms_object_id=str(user.id),
        ms_group_ids=custom_group_ids,
        user_id=str(user.id),
        is_superadmin=user.is_superadmin,
    )


async def _resolve_custom_group_ids(db: AsyncSession, user_id) -> list[str]:
    """Return ms_group_id strings for all custom groups this user belongs to,
    including every ancestor of each directly-joined group.

    Inheritance is child→parent: if the user is a member of group G and G has
    parent P, the user effectively belongs to P (and P's parent, etc.).
    Depth is capped at 16 to protect against runaway recursion if a cycle ever
    slipped past the CHECK constraint and cycle-prevention logic.

    Result is cached in Redis for 5 minutes (key: groups:{user_id}).
    """
    cache_key = f"groups:{str(user_id)}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        text("""
        WITH RECURSIVE direct AS (
            SELECT group_id AS id FROM custom_group_members WHERE user_id = :uid
        ),
        ancestors(id, depth) AS (
            SELECT id, 0 FROM direct
            UNION
            SELECT g.parent_group_id, a.depth + 1
            FROM ms_groups g
            JOIN ancestors a ON g.id = a.id
            WHERE g.parent_group_id IS NOT NULL AND a.depth < 16
        )
        SELECT DISTINCT g.ms_group_id
        FROM ms_groups g
        JOIN ancestors a ON g.id = a.id
        """),
        {"uid": user_id},
    )
    group_ids = [row[0] for row in result.all()]
    await cache_set(cache_key, group_ids, ttl=300)
    return group_ids
